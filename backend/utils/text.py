import re

_EMOJI_PATTERN = re.compile(
    "[\U0001F300-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\U0001F000-\U0001F0FF"
    "\U00002600-\U000027BF"
    "\U0000FE00-\U0000FE0F"
    "\U0000200D"
    "\U00002190-\U000021FF"
    "\U00002B00-\U00002BFF"
    "\U00002300-\U000023FF"
    "]+"
)


def strip_thinking(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"<think>.*$", "", text, flags=re.DOTALL)
    return text.strip()


def extract_answer(text: str) -> str:
    """Extract the model's answer, stripping reasoning.

    Falls back to the last non-empty line when the thinking block is unclosed
    or malformed (so the response is never silently emptied).
    """
    if not text:
        return ""
    stripped = strip_thinking(text)
    if stripped:
        return clean_text(stripped)
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    last = lines[-1] if lines else text.strip()
    return clean_text(last)


def clean_text(text: str) -> str:
    if not text:
        return ""

    text = strip_thinking(text)

    text = _EMOJI_PATTERN.sub("", text)

    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)

    text = text.replace("**", "").replace("__", "").replace("`", "")

    text = re.sub(r"^\s*#{1,6}\s*", "", text, flags=re.MULTILINE)

    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)

    text = re.sub(r"\s+", " ", text).strip()
    return text
