from config import settings
from backend.memory import recall, save_exchange, format_memories


class TestFormatMemories:
    def test_empty_list(self):
        assert format_memories([]) == ""

    def test_formats_strings(self):
        result = format_memories(["doctor said avoid milk", "meeting at 3pm"])
        assert "- doctor said avoid milk" in result
        assert "- meeting at 3pm" in result
        assert "past conversations" in result

    def test_formats_dicts_with_created_date(self):
        result = format_memories([
            {"text": "meeting Sunday", "created_at": "2026-08-20"},
            {"text": "meeting 3pm", "created_at": "2026-08-18"},
        ])
        assert "- meeting Sunday (created 2026-08-20)" in result
        assert "- meeting 3pm (created 2026-08-18)" in result

    def test_ends_with_blank_line(self):
        result = format_memories(["x"])
        assert result.endswith("\n\n")


class TestRecallNoKey:
    def test_recall_returns_empty_without_key(self, monkeypatch):
        monkeypatch.setattr(settings, "MEM0_API_KEY", "")
        assert recall("anything") == []

    def test_save_exchange_noops_without_key(self, monkeypatch):
        monkeypatch.setattr(settings, "MEM0_API_KEY", "")
        save_exchange("hi", "hello")  # should not raise
