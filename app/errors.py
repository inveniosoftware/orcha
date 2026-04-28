"""Exception classes."""


class WorkflowEventError(Exception):
    """Exception raised when generating SSE events is failed."""

    def __init__(self, error_code: str):
        """Initialize exception."""
        self.error_code = error_code
