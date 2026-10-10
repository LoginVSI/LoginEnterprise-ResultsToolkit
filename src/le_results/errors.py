class ToolkitError(Exception):
    """Safe customer-facing diagnostic. Never contains server bodies or credentials."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status
