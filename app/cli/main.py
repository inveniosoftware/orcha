import signal
import subprocess
import sys
from pathlib import Path

import typer
from sqlmodel import SQLModel

from app.database.models import Workflow  # noqa: F401
from app.database.session import dispose_engine, init_engine

PROJECT_ROOT = Path(__file__).resolve().parents[2]

app = typer.Typer(help="Orcha CLI tools.")
services_app = typer.Typer(
    help="Manage infrastructure services (PostgreSQL + Temporal)."
)
run_app = typer.Typer(help="Run application processes.")
app.add_typer(services_app, name="services")
app.add_typer(run_app, name="run")


@app.command()
def init_db():
    """Create all database tables from models."""
    # TODO: If more commands need the DB, consider moving engine
    # init/dispose into a Typer callback so it's shared automatically.
    engine = init_engine()
    SQLModel.metadata.create_all(engine)
    typer.echo("Database tables created successfully.")
    dispose_engine()


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
def server():
    """Start the FastAPI development server."""
    typer.echo("Starting FastAPI server...")
    result = subprocess.run(
        ["uv", "run", "fastapi", "dev", "app/main.py"],
        cwd=PROJECT_ROOT,
    )
    sys.exit(result.returncode)


@run_app.command()
def workers():
    """Start the Temporal worker."""
    typer.echo("Starting Temporal worker...")
    result = subprocess.run(
        [sys.executable, "-m", "app.workers"],
        cwd=PROJECT_ROOT,
    )
    sys.exit(result.returncode)


@run_app.callback(invoke_without_command=True)
def run_all(ctx: typer.Context):
    """Start both the FastAPI server and Temporal worker."""
    if ctx.invoked_subcommand is not None:
        return

    typer.echo("Starting server and worker...")
    procs = [
        subprocess.Popen(
            ["uv", "run", "fastapi", "dev", "app/main.py"],
            cwd=PROJECT_ROOT,
        ),
        subprocess.Popen(
            [sys.executable, "-m", "app.workers"],
            cwd=PROJECT_ROOT,
        ),
    ]

    def _shutdown(sig, frame):
        for p in procs:
            p.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    for p in procs:
        p.wait()


if __name__ == "__main__":
    app()
