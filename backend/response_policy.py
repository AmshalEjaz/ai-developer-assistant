DETAIL_MARKERS = (
    "step by step",
    "in detail",
    "detailed",
    "full explanation",
    "explain fully",
    "complete guide",
    "deep dive",
    "deeply",
)

CODE_MARKERS = (
    "full code",
    "complete code",
    "entire code",
    "whole code",
    "full file",
    "complete file",
)


def response_style_instruction(user_text: str) -> str:
    text = (user_text or "").strip().lower()

    if any(marker in text for marker in DETAIL_MARKERS):
        return (
            "Detailed mode: the user explicitly asked for a detailed answer. "
            "Explain thoroughly, but stay organized and avoid repeating the same point."
        )

    if (
        any(marker in text for marker in CODE_MARKERS)
        or ("full" in text and "code" in text)
        or ("complete" in text and "code" in text)
    ):
        return (
            "Code-request mode: keep the explanation concise, but provide the complete requested code. "
            "Do not pad the answer with generic background unless it is necessary."
        )

    return (
        "Concise mode: answer directly and briefly. For a simple question, usually use 2-8 sentences. "
        "Use no table, long checklist, or multiple headings unless they materially help. "
        "Do not repeat the user's message or add generic extras after the answer. "
        "If the topic is safety/security-sensitive, state the important action first and keep the explanation focused."
    )
