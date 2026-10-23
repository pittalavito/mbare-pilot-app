from __future__ import annotations


class AppError(Exception):
    """Base application error: expected failures the UI shows to the user."""


class NotFoundError(AppError):
    """A requested resource does not exist."""


class ConflictError(AppError):
    """The request conflicts with the current state (e.g. a duplicate)."""


class ValidationError(AppError):
    """The input is invalid."""


class UpstreamError(AppError):
    """A dependency failed (LLM provider, network, ...)."""
