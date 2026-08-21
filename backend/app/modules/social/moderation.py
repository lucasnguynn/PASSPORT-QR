"""Small, deterministic first-line content moderation for the MVP."""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re
import unicodedata


@dataclass(frozen=True)
class BadwordResult:
    passed: bool
    flagged_words: list[str]


@dataclass(frozen=True)
class ModerationResult:
    status: str
    reason: str | None = None
    flagged_words: tuple[str, ...] = ()


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold()).replace("đ", "d")
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


@lru_cache(maxsize=1)
def load_badwords() -> tuple[str, ...]:
    """Load and normalize both bundled word lists once per process."""
    data_dir = Path(__file__).resolve().parents[3] / "data"
    words: set[str] = set()
    for filename in ("badwords_vi.txt", "badwords_en.txt"):
        for line in (data_dir / filename).read_text(encoding="utf-8").splitlines():
            value = line.strip()
            if value and not value.startswith("#"):
                words.add(_normalize(value))
    return tuple(sorted(words))


def badword_filter(value: str) -> BadwordResult:
    """Find prohibited whole words or phrases without case/diacritic sensitivity."""
    normalized = _normalize(value)
    flagged = [word for word in load_badwords() if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", normalized)]
    return BadwordResult(passed=not flagged, flagged_words=flagged)


def auto_moderate(content: str, title: str | None) -> ModerationResult:
    """Apply bad-word and minimum-length checks; duplicate spam is checked by the service."""
    filtered = badword_filter(f"{title or ''} {content}")
    if not filtered.passed:
        return ModerationResult("flagged", "contains_prohibited_words", tuple(filtered.flagged_words))
    if len(content.strip()) < 10:
        return ModerationResult("flagged", "too_short")
    return ModerationResult("approved")
