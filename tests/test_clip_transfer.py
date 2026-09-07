"""Clip firmware transfer compatibility tests."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from clip.exceptions import TransferError
from clip.protocol import DataFrame, FileEndFrame, FileStartFrame, TransferDoneFrame
from clip.transports.base import BaseTransport

from backend.clip.transfer import (
    DuplicateStartTolerantReceiver,
    session_details_ready,
    wait_for_session_ready,
)


class FakeTransport(BaseTransport):
    @property
    def is_connected(self):
        return True

    async def connect(self):
        return None

    async def disconnect(self):
        return None

    async def send_command(self, command, *, timeout):
        return {"ok": True}


def test_identical_zero_byte_file_start_is_idempotent(tmp_path: Path):
    receiver = DuplicateStartTolerantReceiver(
        FakeTransport(),
        "00000000000001",
        tmp_path,
        udp=False,
    )
    frame = FileStartFrame(filename="0001.opus", size=123)
    receiver._on_file_start(frame)
    receiver._on_file_start(frame)
    receiver.close()


def test_different_file_start_is_still_rejected(tmp_path: Path):
    receiver = DuplicateStartTolerantReceiver(
        FakeTransport(),
        "00000000000001",
        tmp_path,
        udp=False,
    )
    receiver._on_file_start(FileStartFrame(filename="0001.opus", size=123))
    with pytest.raises(TransferError, match="FILE_START"):
        receiver._on_file_start(FileStartFrame(filename="0002.opus", size=123))
    receiver.close()


def test_identical_consecutive_data_frame_is_idempotent(tmp_path: Path):
    receiver = DuplicateStartTolerantReceiver(
        FakeTransport(),
        "00000000000001",
        tmp_path,
        udp=False,
    )
    receiver._on_file_start(FileStartFrame(filename="0001.opus", size=3))
    frame = DataFrame(sequence=0, payload=b"abc")
    receiver._on_data(frame)
    receiver._on_data(frame)
    assert receiver._received == 3
    assert receiver._expected_sequence == 1
    receiver.close()


def test_orphan_tail_frames_before_new_file_start_are_ignored(tmp_path: Path):
    receiver = DuplicateStartTolerantReceiver(
        FakeTransport(),
        "00000000000001",
        tmp_path,
        udp=False,
    )
    receiver._on_data(DataFrame(sequence=99, payload=b"stale"))
    receiver._on_file_end(FileEndFrame(crc32=123))
    receiver._on_transfer_done(
        TransferDoneFrame(session_id="00000000000001", file_count=1)
    )
    assert receiver.error is None
    assert receiver.done.is_set() is False
    assert receiver._received == 0
    receiver.close()


def test_zero_metadata_is_not_ready_for_download():
    details = SimpleNamespace(files=0, size_bytes=0, channels=0, sample_rate_hz=0)
    assert session_details_ready(details) is False


def test_waits_for_committed_metadata_before_download():
    zero = SimpleNamespace(files=0, size_bytes=0, channels=0, sample_rate_hz=0)
    ready = SimpleNamespace(
        files=1,
        size_bytes=70156,
        channels=1,
        sample_rate_hz=16000,
        mode="mono",
    )

    class Client:
        def __init__(self):
            self.responses = [zero, ready, ready, ready]
            self.calls = 0

        async def session_details(self, _session_id):
            self.calls += 1
            return self.responses.pop(0)

    async def body():
        client = Client()
        result = await wait_for_session_ready(
            client,
            "00000000000647",
            timeout=1,
            poll_interval=0,
        )
        assert result is ready
        assert client.calls == 4

    asyncio.run(body())
