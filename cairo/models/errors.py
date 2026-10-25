"""Small, safe provider error taxonomy shared with the existing runtime."""


class ModelError(RuntimeError):
    """Messages are safe to show in the UI; never include upstream bodies."""

    def __init__(
        self, message: str, *, code: str = "provider_error", status: int | None = None
    ):
        super().__init__(message)
        self.code = code
        self.status = status

    def as_dict(self) -> dict:
        return {"code": self.code, "message": str(self), "http_status": self.status}
