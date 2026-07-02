from __future__ import annotations


from enum import Enum


class AppError(RuntimeError):

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        super().__init__(message)
        if cause is not None:
            self.__cause__ = cause


class ConfigError(AppError):
    pass


class ChapterParseError(AppError):
    pass


class FileOperationError(AppError):
    pass


class PlatformError(AppError):
    pass


class NetworkError(PlatformError):
    pass


class TimeoutError(PlatformError):
    pass


class BrowserError(PlatformError):
    pass


class ValidationError(AppError):
    pass


class SecurityError(AppError):
    pass


class ErrorStage(str, Enum):
    PREFLIGHT = "preflight"
    CREATOR = "creator"
    EDITOR = "editor"
    SUBMITTER = "submitter"
    VERIFIER = "verifier"
    TRACKER = "tracker"
    CHAPTER = "chapter"
    NETWORK = "network"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


__all__ = [
    "AppError",
    "ConfigError",
    "ChapterParseError",
    "FileOperationError",
    "PlatformError",
    "NetworkError",
    "TimeoutError",
    "BrowserError",
    "ValidationError",
    "SecurityError",
    "ErrorStage",
]


