"""Shared audio -> transcript -> LangGraph -> persistence pipeline.

Extracted from the browser voice route so the Clip ingestion workflow and the
legacy browser microphone path run through identical processing (STT, routing,
conversation persistence, memory, vector indexing).  The service accepts raw
bytes or a local file path and returns
``{"transcript", "response", "conversation_id", "route"}``.
"""

from __future__ import annotations

import logging

from backend.database import (
    create_conversation,
    save_turn,
    get_recent_messages,
)
from backend.graph import build_graph, AgentState
from backend.llm.stt import transcribe_bytes
from backend.memory import recall, save_exchange
from backend.services import index_conversation_async

logger = logging.getLogger(__name__)


class AudioService:
    """Single-user audio chat pipeline used by browser and Clip inputs."""

    def __init__(self) -> None:
        self._graph = None

    def _get_graph(self):
        if self._graph is None:
            self._graph = build_graph()
        return self._graph

    def process_transcript(
        self,
        transcript: str,
        conversation_id: str | None = None,
    ) -> dict:
        """Run the transcript through LangGraph and persist the exchange."""
        cid = conversation_id or create_conversation()

        state: AgentState = {
            "messages": [],
            "transcript": transcript,
            "route": "",
            "response": "",
            "error": None,
            "memories": recall(transcript),
            "history": get_recent_messages(cid, 10),
        }
        result = self._get_graph().invoke(state)

        save_turn(cid, "user", transcript)
        save_turn(cid, "assistant", result["response"])
        save_exchange(transcript, result["response"])
        index_conversation_async(cid)

        return {
            "transcript": transcript,
            "response": result["response"],
            "conversation_id": cid,
            "route": result.get("route", ""),
        }

    def process_audio(
        self,
        audio_bytes: bytes,
        filename: str = "audio.wav",
        conversation_id: str | None = None,
    ) -> dict:
        """Transcribe raw audio bytes, then run the shared pipeline."""
        transcript = transcribe_bytes(audio_bytes, filename)
        return self.process_transcript(transcript, conversation_id)

    def process_audio_file(
        self,
        file_path: str,
        filename: str | None = None,
        conversation_id: str | None = None,
    ) -> dict:
        """Read a local audio file (e.g. a Clip Ogg) and process it."""
        import os

        path = file_path
        with open(path, "rb") as handle:
            audio_bytes = handle.read()
        return self.process_audio(
            audio_bytes,
            filename or os.path.basename(path),
            conversation_id,
        )
