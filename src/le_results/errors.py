class ToolkitError(Exception):
    """Safe customer-facing diagnostic. Never contains server bodies or credentials."""

    def __init__(
        self,
        message: str,
        status: int | None = None,
        *,
        code: str = "toolkit_error",
        verify_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.verify_code = verify_code

    def diagnostic(self) -> dict[str, str | int | None]:
        return {
            "code": self.code,
            "message": str(self),
            "http_status": self.status,
            "ssl_verify_code": self.verify_code,
        }
