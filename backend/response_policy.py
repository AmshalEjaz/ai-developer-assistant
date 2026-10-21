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
            "Lightweight coding mode: do not generate or rewrite an entire file or project by default. "
            "Explain the issue and offer the smallest relevant snippet or patch. "
            "If the request requires a large or complex implementation, explain the approach and ask which small step to tackle first. "
            "Preserve existing application logic and avoid unrelated changes."
        )

    return (
        "Concise mode: answer directly and briefly. For a simple question, usually use 2-8 sentences. "
        "Use no table, long checklist, or multiple headings unless they materially help. "
        "Do not repeat the user's message or add generic extras after the answer. "
        "If the topic is safety/security-sensitive, state the important action first and keep the explanation focused."
    )
