from backend.utils.text import clean_text, strip_thinking
from backend.llm.stt import _fuzzy_correct, _apply_corrections


class TestCleanText:
    def test_strips_bold_markdown(self):
        assert clean_text("The **XVF3800** is a chip.") == "The XVF3800 is a chip."

    def test_strips_headers(self):
        assert clean_text("# Introduction\nHello") == "Introduction Hello"

    def test_strips_emojis(self):
        assert clean_text("Great \U0001F44D result") == "Great result"

    def test_strips_list_markers(self):
        assert clean_text("- item one\n- item two") == "item one item two"

    def test_strips_backticks(self):
        assert clean_text("Use `dfu` mode") == "Use dfu mode"

    def test_collapses_whitespace(self):
        assert clean_text("hello   \n\n  world") == "hello world"

    def test_empty_string(self):
        assert clean_text("") == ""
        assert clean_text(None) == ""


class TestStripThinking:
    def test_strips_closed_think_block(self):
        assert strip_thinking("<think>reasoning</think>\n\nanswer") == "answer"

    def test_strips_unclosed_think_block(self):
        assert strip_thinking("<think>reasoning without closing tag\nsome answer") == ""

    def test_clean_text_strips_unclosed_think(self):
        assert clean_text("<think>reasoning without closing tag") == ""


class TestSttCorrections:
    def test_fuzzy_correct_near_miss(self):
        assert _fuzzy_correct("XVF380") == "XVF3800"

    def test_fuzzy_correct_typo(self):
        assert _fuzzy_correct("reSpeker") == "reSpeaker"

    def test_fuzzy_leaves_normal_words(self):
        assert _fuzzy_correct("hello world") == "hello world"

    def test_fuzzy_does_not_replace_common_short_words(self):
        assert _apply_corrections("what is I2S") == "what is I2S"
        assert _apply_corrections("the us and them") == "the us and them"

    def test_apply_corrections_xpm(self):
        assert _apply_corrections("what is XPM 3800") == "what is XVF3800"

    def test_apply_corrections_aids(self):
        assert _apply_corrections("what is AIDS 2") == "what is I2S"

    def test_apply_corrections_free_speaker(self):
        assert _apply_corrections("who built the free speaker") == "who built the reSpeaker"
