"""Exceptions raised by the application-level Clip runtime.

The Flask routes translate these into HTTP status codes:
400 bad input, 409 state conflict, 502 command/transfer failure,
503 unavailable / reconnecting.
"""

from __future__ import annotations


class ClipRuntimeError(Exception):
    """Base class for Clip runtime errors surfaced to the API."""


class ClipInputError(ClipRuntimeError):
    """Bad request input (400)."""


class ClipConflictError(ClipRuntimeError):
    """State conflict, e.g. start while already recording (409)."""


class ClipCommandFailedError(ClipRuntimeError):
    """The device rejected a command (502)."""


class ClipTransferFailedError(ClipRuntimeError):
    """A session download/transfer failed (502)."""


class ClipUnavailableError(ClipRuntimeError):
    """The device is offline, reconnecting, or the runtime is not running (503)."""
