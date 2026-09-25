# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT
"""Fetch the published dataset and overlay newer GitHub objects."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import zipfile
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

import requests

REPO = "zenodo/orcha-eval-dataset"
GITHUB_API = "https://api.github.com"
GITHUB_RAW = "https://raw.githubusercontent.com"
GITHUB_MEDIA = "https://media.githubusercontent.com/media"
ZENODO = "https://zenodo.org"
USER_AGENT = "orcha-evaluation-dataset-client"


class DatasetSyncError(RuntimeError):
    """Remote dataset or cache state is invalid."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _object_path(cache: Path, checksum: str) -> Path:
    return cache / "objects" / checksum[:2] / checksum


def _entries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if manifest.get("schema_version") != 1:
        raise DatasetSyncError(
            f"Unsupported manifest schema: {manifest.get('schema_version')}"
        )
    records = manifest.get("records")
    if not isinstance(records, dict):
        raise DatasetSyncError("Manifest records must be an object")

    entries = []
    paths = set()
    for record_id, record in records.items():
        for field in ("document", "metadata"):
            entry = record.get(field)
            if not isinstance(entry, dict):
                raise DatasetSyncError(f"{record_id}: missing {field} entry")
            relative = PurePosixPath(entry.get("path", ""))
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or relative.parts[:1] not in (("files",), ("metadata",))
            ):
                raise DatasetSyncError(f"{record_id}: invalid path {relative}")
            checksum = entry.get("sha256")
            size = entry.get("size")
            if not isinstance(checksum, str) or not re.fullmatch(
                r"[0-9a-f]{64}", checksum
            ):
                raise DatasetSyncError(f"{record_id}: invalid SHA-256")
            if not isinstance(size, int) or size < 0:
                raise DatasetSyncError(f"{record_id}: invalid size")
            path = relative.as_posix()
            if path in paths:
                raise DatasetSyncError(f"Duplicate manifest path: {path}")
            paths.add(path)
            entries.append({"path": path, "sha256": checksum, "size": size})
    return sorted(entries, key=lambda entry: entry["path"])


def _headers(token: str | None = None) -> dict[str, str]:
    headers = {"User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get(
    url: str,
    *,
    token: str | None = None,
    stream: bool = False,
) -> requests.Response:
    response = requests.get(
        url,
        headers=_headers(token),
        stream=stream,
        timeout=(30, 3600),
    )
    return response


def _resolve_commit(repo: str, ref: str, token: str | None) -> str:
    if re.fullmatch(r"[0-9a-f]{40}", ref):
        return ref
    response = _get(
        f"{GITHUB_API}/repos/{repo}/commits/{quote(ref, safe='')}",
        token=token,
    )
    return response.json()["sha"]


def _valid_object(path: Path, entry: dict[str, Any]) -> bool:
    # Objects are hashed before this content-addressed path is created.
    return path.is_file() and path.stat().st_size == entry["size"]


def _store_object(
    source: Any,
    cache: Path,
    entry: dict[str, Any],
) -> Path:
    destination = _object_path(cache, entry["sha256"])
    if _valid_object(destination, entry):
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as target:
        temporary = Path(target.name)
        try:
            while chunk := source.read(1 << 20):
                target.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    if size != entry["size"] or digest.hexdigest() != entry["sha256"]:
        temporary.unlink(missing_ok=True)
        raise DatasetSyncError(f"Hash or size mismatch for {entry['path']}")
    temporary.replace(destination)
    return destination


def _missing(cache: Path, entries: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        entry
        for entry in entries
        if not _valid_object(_object_path(cache, entry["sha256"]), entry)
    ]


def _seed_archive(
    archive_path: Path,
    manifest_bytes: bytes,
    cache: Path,
) -> None:
    manifest = json.loads(manifest_bytes)
    entries = _entries(manifest)
    with zipfile.ZipFile(archive_path) as archive:
        if archive.read("manifest.json") != manifest_bytes:
            raise DatasetSyncError("Archive manifest differs from Zenodo manifest")
        for entry in _missing(cache, entries):
            try:
                with archive.open(entry["path"]) as source:
                    _store_object(source, cache, entry)
            except KeyError as error:
                raise DatasetSyncError(f"Archive is missing {entry['path']}") from error


def _download_archive(
    url: str,
    checksum: str,
    destination: Path,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    response = _get(url, stream=True)
    digest = hashlib.md5()
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as target:
        temporary = Path(target.name)
        try:
            for chunk in response.iter_content(1 << 20):
                target.write(chunk)
                digest.update(chunk)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    if checksum != f"md5:{digest.hexdigest()}":
        temporary.unlink(missing_ok=True)
        raise DatasetSyncError("Zenodo archive checksum mismatch")
    temporary.replace(destination)
    return destination


def _seed_zenodo(
    cache: Path,
    state: dict[str, Any],
    zenodo_base: str,
) -> None:
    record_id = state["latest_recid"]
    response = _get(f"{zenodo_base.rstrip('/')}/api/records/{record_id}/files")
    remote = {entry["key"]: entry for entry in response.json()["entries"]}
    try:
        manifest_remote = remote["manifest.json"]
        archive_remote = remote[state["archive"]]
    except KeyError as error:
        raise DatasetSyncError(f"Zenodo record is missing {error.args[0]}") from error

    published_manifest = _get(manifest_remote["links"]["content"]).content
    if _sha256_bytes(published_manifest) != state["manifest_sha256"]:
        raise DatasetSyncError("Zenodo manifest does not match .zenodo-record.json")
    entries = _entries(json.loads(published_manifest))
    if not _missing(cache, entries):
        return

    archive_path = cache / "tmp" / state["archive"]
    _download_archive(
        archive_remote["links"]["content"],
        archive_remote["checksum"],
        archive_path,
    )
    try:
        _seed_archive(archive_path, published_manifest, cache)
    finally:
        archive_path.unlink(missing_ok=True)


def _fetch_current_objects(
    cache: Path,
    manifest: dict[str, Any],
    repo: str,
    commit: str,
    token: str | None,
) -> None:
    for entry in _missing(cache, _entries(manifest)):
        path = quote(entry["path"], safe="/")
        base = GITHUB_MEDIA if entry["path"].startswith("files/") else GITHUB_RAW
        response = _get(f"{base}/{repo}/{commit}/{path}", token=token, stream=True)
        with response.raw as source:
            source.decode_content = True
            _store_object(source, cache, entry)


def _materialize(
    target: Path,
    cache: Path,
    manifest: dict[str, Any],
    provenance: dict[str, Any],
) -> Path:
    target.mkdir(parents=True, exist_ok=True)
    state_path = target / ".dataset-state.json"
    previous = {}
    if state_path.exists():
        previous = json.loads(state_path.read_text(encoding="utf-8"))

    entries = _entries(manifest)
    current_paths = {entry["path"] for entry in entries}
    previous_paths = set(previous.get("managed_paths", []))
    for stale in previous_paths - current_paths:
        stale_path = target / stale
        if stale_path.is_symlink():
            stale_path.unlink()

    for entry in entries:
        destination = target / entry["path"]
        source = _object_path(cache, entry["sha256"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_symlink() and destination.resolve() == source.resolve():
            continue
        if destination.is_symlink() and entry["path"] in previous_paths:
            destination.unlink()
        if destination.exists() or destination.is_symlink():
            raise DatasetSyncError(f"Refusing to replace unmanaged file: {destination}")
        destination.symlink_to(os.path.relpath(source, destination.parent))

    materialized = {**provenance, "managed_paths": sorted(current_paths)}
    state_path.write_text(json.dumps(materialized, indent=2) + "\n", encoding="utf-8")
    return target


def sync_dataset(
    *,
    repo: str = REPO,
    ref: str = "main",
    cache: Path | None = None,
    target: Path | None = None,
    zenodo_base: str = ZENODO,
) -> tuple[Path, dict[str, Any]]:
    """Synchronize one Git commit through the Zenodo-backed object cache."""
    cache = (
        cache
        or Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        / "orcha-eval-dataset"
    )
    target = target or cache / "dataset"
    token = os.environ.get("GITHUB_TOKEN")
    commit = _resolve_commit(repo, ref, token)

    raw_base = f"{GITHUB_RAW}/{repo}/{commit}"
    manifest_bytes = _get(f"{raw_base}/manifest.json", token=token).content
    manifest = json.loads(manifest_bytes)
    _entries(manifest)
    resp = _get(f"{raw_base}/.zenodo-record.json", token=token)
    if resp.status_code == 404:
        state = {}
        print("Zenodo dataset not found. Downloading from GitHub repo...")
    else:
        state = resp.json()
        _seed_zenodo(cache, state, zenodo_base)

    _fetch_current_objects(cache, manifest, repo, commit, token)

    provenance = {
        "dataset_git_commit": commit,
        "dataset_manifest_sha256": _sha256_bytes(manifest_bytes),
        "dataset_repo": repo,
        "dataset_version": state.get("version"),
        "zenodo_doi": state.get("latest_doi"),
        "zenodo_record_id": state.get("latest_recid"),
    }
    return _materialize(target, cache, manifest, provenance), provenance
