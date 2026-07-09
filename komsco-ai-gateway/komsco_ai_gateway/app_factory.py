from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from fastapi import FastAPI


def create_app(
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]] | None = None,
) -> FastAPI:
    return FastAPI(title="KOMSCO AI Gateway", version="0.1.5", lifespan=lifespan)
