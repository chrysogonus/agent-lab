"""Refusals every route module shapes the same way."""

from fastapi.exceptions import RequestValidationError


def field_error(loc: tuple[str | int, ...], msg: str) -> RequestValidationError:
    """A 422 in FastAPI's own shape, so every rejection names its field the same way."""
    return RequestValidationError([{"loc": loc, "msg": msg, "type": "value_error"}])
