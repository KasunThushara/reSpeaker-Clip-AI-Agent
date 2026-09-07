"""Compatibility wrapper around the pinned Clip SDK file receiver.

Firmware 0.0.8+1 can repeat an identical FILE_START notification before the
first DATA frame.  The SDK correctly rejects a second start in the general
case, but this zero-byte duplicate is harmless and otherwise prevents a valid
recording from ever downloading.  Integrity checks for sequence, size and CRC
remain owned by the SDK receiver and are unchanged.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from time import monotonic
from typing import Any

from clip.exceptions import TransferTimeoutError
from clip.models import DownloadResult
from clip.protocol import DataFrame, FileEndFrame, FileStartFrame, TransferDoneFrame
from clip.transfer import FileReceiver


class DuplicateStartTolerantReceiver(FileReceiver):
    """Ignore only an identical FILE_START repeated before any file data."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._last_data_sequence: int | None = None
        self._last_data_payload: bytes | None = None
        self._saw_file_start = False

    def _on_file_start(self, frame: FileStartFrame) -> None:
        if (
            self._handle is not None
            and self._received == 0
            and self._filename == frame.filename
            and self._expected_size == frame.size
        ):
            return
        super()._on_file_start(frame)
        self._saw_file_start = True

    def _on_data(self, frame: DataFrame) -> None:
        # Firmware may repeat a notification around a BLE link transition.
        # Ignore only a byte-for-byte duplicate of the immediately preceding
        # sequence.  Gaps, reordering and conflicting duplicates still flow to
        # the SDK receiver and fail its sequence/length/CRC checks.
        if self._handle is None:
            # A reconnect can deliver tail notifications from the abandoned
            # transfer before the new AT+DOWNLOAD emits FILE_START.
            return
        if (
            frame.sequence == self._last_data_sequence
            and frame.payload == self._last_data_payload
        ):
            return
        self._last_data_sequence = frame.sequence
        self._last_data_payload = frame.payload
        super()._on_data(frame)

    def _on_file_end(self, frame: FileEndFrame) -> None:
        if self._handle is None:
            return
        super()._on_file_end(frame)

    def _on_transfer_done(self, frame: TransferDoneFrame) -> None:
        if not self._saw_file_start:
            return
        super()._on_transfer_done(frame)


def session_details_ready(details: Any) -> bool:
    """Return whether firmware has finished committing a recorded session."""
    return bool(
        int(getattr(details, "files", 0)) > 0
        and int(getattr(details, "size_bytes", 0)) > 0
        and int(getattr(details, "channels", 0)) > 0
        and int(getattr(details, "sample_rate_hz", 0)) > 0
    )


async def wait_for_session_ready(
    client: Any,
    session_id: str,
    *,
    timeout: float = 60.0,
    poll_interval: float = 1.0,
    stable_reads: int = 3,
) -> Any:
    """Poll metadata without starting transfer until the file is committed.

    A physical-button IDLE event can arrive before firmware has closed and
    indexed the Opus file.  During that window AT+LIST=<session> returns a
    syntactically valid all-zero record.  Sending AT+DOWNLOAD at that point
    produces incomplete frames and deterministic CRC failures.
    """
    if stable_reads < 1:
        raise ValueError("stable_reads must be positive")
    deadline = monotonic() + timeout
    previous_signature: tuple[Any, ...] | None = None
    consecutive = 0
    while True:
        details = await client.session_details(session_id)
        if session_details_ready(details):
            signature = (
                int(details.files),
                int(details.size_bytes),
                int(details.channels),
                int(details.sample_rate_hz),
                str(getattr(details, "mode", "")),
            )
            if signature == previous_signature:
                consecutive += 1
            else:
                previous_signature = signature
                consecutive = 1
            if consecutive >= stable_reads:
                return details
        else:
            previous_signature = None
            consecutive = 0
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TransferTimeoutError(
                f"session {session_id} metadata was not ready within {timeout:g}s"
            )
        await asyncio.sleep(min(poll_interval, remaining))


async def download_session_compatible(
    client: Any,
    session_id: str,
    destination: str | Path,
    *,
    timeout: float,
) -> DownloadResult:
    """Download with SDK-compatible metadata and stricter duplicate handling."""
    details = await wait_for_session_ready(client, session_id)
    output_dir = (Path(destination) / details.session_id).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "session_id": details.session_id,
        "files": details.files,
        "size_bytes": details.size_bytes,
        "bookmarks": details.bookmarks,
        "channels": details.channels,
        "sample_rate_hz": details.sample_rate_hz,
        "mode": details.mode,
    }
    (output_dir / "session.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )

    receiver = DuplicateStartTolerantReceiver(
        client.transport,
        details.session_id,
        output_dir,
        udp=client.transport.uses_udp_file_frames,
    )
    client.transport.set_file_frame_handler(receiver.feed)
    try:
        await client.start_download(details.session_id)
        await receiver.wait(timeout)
    except Exception:
        if client.transport.is_connected:
            try:
                await client.cancel_download()
            except Exception:
                pass
        raise
    finally:
        client.transport.set_file_frame_handler(None)
        receiver.close()

    return DownloadResult(
        session_id=details.session_id,
        files=receiver.files,
        expected_files=receiver.transferred_file_count,
        output_dir=str(output_dir),
    )
