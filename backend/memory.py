import re


ROMAN_URDU_WORDS = {
    "acha", "abhi", "ap", "apka", "apki", "apko", "bas", "bhi",
    "chahiye", "chahye", "hai", "hain", "han", "haan", "ho", "hoon",
    "is", "ka", "ke", "ki", "kia", "kya", "ko", "kr", "kro", "kar",
    "karo", "karna", "main", "ma", "mera", "meri", "mujhe", "mujhy",
    "nahi", "nhi", "phir", "q", "raha", "rha", "rhay", "rhy", "sai",
    "se", "suno", "theek", "tum", "tumhara", "wo", "woh", "ya", "ye",
    "yr", "zara",
}

MEMORY_PREFIX_RE = re.compile(
    r"^(?:remember(?:\s+this|\s+that)?|add\s+to\s+memory|save\s+to\s+memory|"
    r"yaad\s+rakhna|yaad\s+rakho|memory\s+me\s+save\s+karo|memory\s+ma\s+save\s+kro)"
    r"\s*[:,-]?\s*(.+)$",
    re.IGNORECASE | re.DOTALL,
)

MEMORY_SUFFIX_RE = re.compile(
    r"^(.+?)\s+(?:yaad\s+rakhna|yaad\s+rakho|remember\s+karna|remember\s+krna)\s*[.!?]*$",
    re.IGNORECASE | re.DOTALL,
)


def detect_user_language(text: str) -> str:
    """Return a small language/script hint for the latest user message."""
    value = str(text or "")

    if re.search(r"[\u0900-\u097F]", value):
        return "Hindi/Devanagari"

    if re.search(r"[\u0600-\u06FF]", value):
        return "Urdu script"

    tokens = re.findall(r"[A-Za-z]+", value.lower())
    score = sum(token in ROMAN_URDU_WORDS for token in tokens)

    if score >= 2:
        return "Roman Urdu"

    return "English"


def language_instruction(text: str) -> str:
    detected = detect_user_language(text)

    if detected == "Roman Urdu":
        return (
            "Current user language: Roman Urdu written in the Latin alphabet. "
            "Reply in Roman Urdu, keeping natural English technical terms. "
            "Do not switch to Hindi/Devanagari script unless the user explicitly asks for it."
        )

    if detected == "Urdu script":
        return (
            "Current user language: Urdu script. Reply in Urdu script, keeping technical "
            "terms clear where English terminology is standard."
        )

    if detected == "Hindi/Devanagari":
        return (
            "Current user language: Hindi written in Devanagari. Reply in the same language "
            "and script unless the user asks for another language."
        )

    return "Current user language: English. Reply in English unless the user asks otherwise."


def classify_memory_text(text: str) -> dict[str, str] | None:
    value = " ".join(str(text or "").strip().split())

    if len(value) < 3:
        return None

    lowered = value.lower()

    roman_urdu_preference = (
        "roman urdu" in lowered
        and any(
            marker in lowered
            for marker in (
                "reply", "respond", "language", "baat", "jawab", "answer"
            )
        )
    )

    if roman_urdu_preference:
        return {
            "key": "preferred_language",
            "value": (
                "Prefer Roman Urdu written in the Latin alphabet with natural English "
                "technical terms. Do not use Hindi/Devanagari unless explicitly requested."
            ),
        }

    return {
        "key": "note",
        "value": value,
    }


def extract_explicit_memory(text: str) -> dict[str, str] | None:
    raw = str(text or "").strip()

    if not raw:
        return None

    prefix_match = MEMORY_PREFIX_RE.match(raw)
    if prefix_match:
        return classify_memory_text(prefix_match.group(1))

    suffix_match = MEMORY_SUFFIX_RE.match(raw)
    if suffix_match:
        return classify_memory_text(suffix_match.group(1))

    return None
