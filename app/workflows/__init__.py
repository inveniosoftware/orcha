"""Workflow definitions — importing submodules triggers self-registration."""

# Import workflow modules so their register_workflow() calls execute.
# To add a new workflow type, add an import here.
import app.workflows.extract_metadata_workflow  # noqa: F401
