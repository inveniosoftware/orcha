import json
import os
from typing import Any

from app.evals import dataset_sync


def test_materialize_hard_links_and_skips_incomplete_records(tmp_path, capsys):
    """Incomplete records never leave discoverable metadata behind."""
    cache = tmp_path / "cache"
    target = tmp_path / "dataset"
    document = b"pdf"
    metadata = b"{}"
    entries: dict[str, dict[str, Any]] = {
        "document": {
            "path": "files/Articles/ART_1.pdf",
            "sha256": dataset_sync._sha256_bytes(document),
            "size": len(document),
        },
        "metadata": {
            "path": "metadata/ART_1.json",
            "sha256": dataset_sync._sha256_bytes(metadata),
            "size": len(metadata),
        },
    }
    manifest = {"schema_version": 1, "records": {"ART_1": entries}}
    for entry, content in zip(entries.values(), (document, metadata), strict=True):
        source = dataset_sync._object_path(cache, entry["sha256"])
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(content)

    old_link = target / entries["document"]["path"]
    old_link.parent.mkdir(parents=True)
    old_link.symlink_to(dataset_sync._object_path(cache, entries["document"]["sha256"]))
    (target / ".dataset-state.json").write_text(
        json.dumps({"managed_paths": [entries["document"]["path"]]}),
        encoding="utf-8",
    )

    dataset_sync._materialize(target, cache, manifest, {"version": "test"})

    for entry in entries.values():
        destination = target / entry["path"]
        source = dataset_sync._object_path(cache, entry["sha256"])
        assert destination.is_symlink() is False
        assert os.path.samefile(destination, source) is True
    assert json.loads((target / ".dataset-state.json").read_text()) == {
        "version": "test",
        "managed_paths": ["files/Articles/ART_1.pdf", "metadata/ART_1.json"],
    }
    assert capsys.readouterr().err == (
        "Hard-linking files/Articles/ART_1.pdf\nHard-linking metadata/ART_1.json\n"
    )

    dataset_sync._object_path(cache, entries["document"]["sha256"]).unlink()
    dataset_sync._materialize(target, cache, manifest, {"version": "test"})

    assert (target / entries["document"]["path"]).exists() is False
    assert (target / entries["metadata"]["path"]).exists() is False
    assert json.loads((target / ".dataset-state.json").read_text()) == {
        "version": "test",
        "managed_paths": [],
    }
    assert capsys.readouterr().err == (
        "Removing stale files/Articles/ART_1.pdf\nRemoving stale metadata/ART_1.json\n"
    )
