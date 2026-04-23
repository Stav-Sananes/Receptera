"""Module entrypoint: ``python -m receptra`` starts uvicorn."""

from __future__ import annotations

import uvicorn


def main() -> None:
    """Run uvicorn on 0.0.0.0:8080."""
    uvicorn.run(
        "receptra.main:app",
        # Binding all interfaces is intended inside the Docker container.
        host="0.0.0.0",
        port=8080,
        log_level="info",
    )


if __name__ == "__main__":
    main()
