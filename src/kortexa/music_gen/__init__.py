"""Music generation server package."""

__all__ = ["app"]


def __getattr__(name: str):
    """Lazily expose the FastAPI app without importing server dependencies."""
    if name == "app":
        from .server import app

        return app
    raise AttributeError(name)
