# SPDX-FileCopyrightText: 2026 CERN.
# SPDX-License-Identifier: MIT

import os
import pty
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import IO

import typer
from alembic import command
from alembic.config import Config

from app.cli.evals import evals_app
from app.cli.tenants import tenants_app
from app.config import get_settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_FILE_SUFFIXES = ("", "-wal", "-shm", "-journal")

app = typer.Typer(help="Orcha CLI tools.")
services_app = typer.Typer(
    help="Manage infrastructure services (PostgreSQL + Temporal)."
)
run_app = typer.Typer(help="Run application processes.")
app.add_typer(services_app, name="services")
app.add_typer(run_app, name="run")
app.add_typer(tenants_app, name="tenants")
app.add_typer(evals_app, name="evals")


@app.command()
def migrate():
    """Apply all database migrations."""
    command.upgrade(Config(PROJECT_ROOT / "alembic.ini"), "head")
    typer.echo("Database migrations applied successfully.")


# ── services ──


@services_app.command()
def start():
    """Start infrastructure services."""
    typer.echo("Starting services...")
    result = subprocess.run(
        ["docker", "compose", "up", "-d"],
        cwd=PROJECT_ROOT,
    )
    sys.exit(result.returncode)


@services_app.command()
def stop():
    """Stop infrastructure services."""
    typer.echo("Stopping services...")
    result = subprocess.run(
        ["docker", "compose", "down"],
        cwd=PROJECT_ROOT,
    )
    sys.exit(result.returncode)


# ── run ──


@run_app.command()
def server(
    dev: bool = typer.Option(
        False, "--dev", help="Run in development mode with hot reload."
    ),
):
    """Start the FastAPI server."""
    if dev:
        typer.echo("Starting FastAPI development server...")
        cmd = ["uv", "run", "fastapi", "dev", "app/main.py"]
    else:
        typer.echo("Starting FastAPI server...")
        cmd = ["uv", "run", "fastapi", "run", "app/main.py"]
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    sys.exit(result.returncode)


@run_app.command()
def workers(task_queue: str | None = None):
    """Start the Temporal worker."""
    typer.echo("Starting Temporal worker...")
    command = ["uv", "run", "python", "-m", "app.workers"]
    if task_queue is not None:
        command.extend(["--task-queue", task_queue])
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
    )
    sys.exit(result.returncode)


def _db_files(path: Path) -> list[Path]:
    return [path.with_name(path.name + suffix) for suffix in DB_FILE_SUFFIXES]


def _delete_db_files(path: Path) -> None:
    for f in _db_files(path):
        f.unlink(missing_ok=True)


def _stream_output(stream: IO[bytes], prefix: str) -> None:
    """Relay a process's combined stdout/stderr with a `[prefix]` marker."""
    with stream:
        pending = b""
        while True:
            try:
                chunk = stream.read(4096)
            except OSError:
                # A pty raises EIO instead of reporting EOF once the child
                # closes its end.
                chunk = b""
            if not chunk:
                break
            *lines, pending = (pending + chunk).split(b"\n")
            for line in lines:
                # A pty terminates lines with CRLF.
                text = line.removesuffix(b"\r").decode(errors="replace")
                sys.stdout.write(f"[{prefix}] {text}\n")
            sys.stdout.flush()
        if pending:
            sys.stdout.write(f"[{prefix}] {pending.decode(errors='replace')}\n")
            sys.stdout.flush()


def _wait_for_temporal(
    proc: subprocess.Popen, host: str, timeout: float = 30.0
) -> None:
    hostname, _, port = host.partition(":")
    port_num = int(port) if port else 7233
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"Temporal exited with code {proc.returncode} before becoming ready."
            )
        try:
            with socket.create_connection((hostname, port_num), timeout=1):
                return
        except OSError:
            time.sleep(0.5)
    raise TimeoutError(f"Temporal did not become ready on {host} within {timeout}s.")


def _terminate_all(procs: dict[str, subprocess.Popen]) -> None:
    for proc in procs.values():
        if proc.poll() is None:
            proc.terminate()
    for proc in procs.values():
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _wait_for_exit(
    procs: dict[str, subprocess.Popen], poll_interval: float = 0.5
) -> tuple[str, int]:
    """Block until any managed process exits; return its name and exit code."""
    while True:
        for name, proc in procs.items():
            code = proc.poll()
            if code is not None:
                return name, code
        time.sleep(poll_interval)


@run_app.callback(invoke_without_command=True)
def run_stack(
    ctx: typer.Context,
    reset: bool = typer.Option(
        False, "--reset", help="Delete orcha.db and temporal.db before starting."
    ),
):
    """Run migrations, Temporal, the API, and a worker for local development."""
    if ctx.invoked_subcommand is not None:
        return

    if shutil.which("temporal") is None:
        typer.echo(
            "The 'temporal' CLI is required for `orcha run`. Install it "
            "with: curl -sSf https://temporal.download/cli.sh | sh "
            "(see https://docs.temporal.io/cli#install for other options).",
            err=True,
        )
        raise typer.Exit(1)

    settings = get_settings()
    db_path = Path(settings.db_path)
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
    temporal_db_path = PROJECT_ROOT / "temporal.db"

    # Force the in-process migration and the api/worker children (spawned
    # with cwd=PROJECT_ROOT) to resolve the same absolute sqlite path,
    # regardless of the invoking shell's cwd.
    os.environ["DB_PATH"] = str(db_path)
    # This command only serves local development, so authentication is off
    # unless the caller says otherwise.
    os.environ.setdefault("DEV_MODE", "1")
    get_settings.cache_clear()
    settings = get_settings()

    if reset:
        typer.echo("Resetting orcha.db and temporal.db...")
        _delete_db_files(db_path)
        _delete_db_files(temporal_db_path)

    typer.echo("Applying database migrations...")
    command.upgrade(Config(PROJECT_ROOT / "alembic.ini"), "head")

    procs: dict[str, subprocess.Popen] = {}

    def _spawn(name: str, cmd: list[str]) -> subprocess.Popen:
        # PYTHONUNBUFFERED so the api/worker children flush each log line
        # immediately instead of block-buffering because stdout is a pipe.
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}

        # Uvicorn and the Temporal CLI colorize their logs only when they see a
        # terminal, so hand each child one when we have a terminal ourselves.
        # Redirected output stays plain.
        on_a_terminal = sys.stdout.isatty()
        read_fd, write_fd = pty.openpty() if on_a_terminal else (-1, -1)

        proc = subprocess.Popen(
            cmd,
            cwd=PROJECT_ROOT,
            stdout=write_fd if on_a_terminal else subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
        )
        if on_a_terminal:
            os.close(write_fd)
            stream: IO[bytes] = os.fdopen(read_fd, "rb", buffering=0)
        else:
            assert proc.stdout is not None
            stream = proc.stdout

        procs[name] = proc
        threading.Thread(
            target=_stream_output, args=(stream, name), daemon=True
        ).start()
        return proc

    def _shutdown(sig, frame):
        _terminate_all(procs)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    typer.echo("Starting Temporal dev server...")
    temporal_proc = _spawn(
        "temporal",
        ["temporal", "server", "start-dev", "--db-filename", "temporal.db"],
    )

    try:
        _wait_for_temporal(temporal_proc, settings.temporal_host)
    except (TimeoutError, RuntimeError) as exc:
        typer.echo(str(exc), err=True)
        _terminate_all(procs)
        raise typer.Exit(1) from exc

    typer.echo("Starting API and worker...")
    _spawn("api", ["uv", "run", "fastapi", "dev", "app/main.py"])
    _spawn("worker", ["uv", "run", "python", "-m", "app.workers"])

    # If any managed process exits on its own, tear down the rest and fail.
    name, code = _wait_for_exit(procs)
    typer.echo(f"[{name}] exited with code {code}; stopping the rest.", err=True)
    _terminate_all(procs)
    raise typer.Exit(1)


if __name__ == "__main__":
    app()
