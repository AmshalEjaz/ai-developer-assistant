import os
import re

from dotenv import load_dotenv
from groq import Groq

from memory import language_instruction
from response_policy import response_style_instruction
from groq_usage import capture_groq_usage


load_dotenv()


api_key = os.getenv("GROQ_API_KEY")
MODEL_NAME = "openai/gpt-oss-120b"

client = (
    Groq(api_key=api_key)
    if api_key
    else None
)


SYSTEM_PROMPT = """
You are DevPilot, an AI Developer Assistant.

You help developers with:

- Programming
- Python
- JavaScript
- React
- FastAPI
- Laravel
- SQL and databases
- Debugging
- Explaining errors
- Writing and improving code
- Software architecture
- APIs
- Development concepts
- Best practices

Your behavior:

1. Be conversational and helpful.
2. Understand the user's question before answering.
3. Give practical answers instead of generic explanations.
4. When the user asks for code, provide clean working code.
5. When debugging an error, explain the likely cause and then provide the solution.
6. Keep simple answers concise.
7. Give detailed explanations when the problem is complex.
8. Do not unnecessarily repeat the user's question.
9. If the user asks a programming question, respond like an experienced developer helping another developer.
10. If the user asks something unrelated to programming, you can still answer normally.
11. Put multi-line code in fenced Markdown code blocks and include the correct language tag, such as python, php, javascript, jsx, sql, css, html, bash, or json.
12. Reply in the same language and writing script as the user's latest natural-language message unless they explicitly request another language.
13. If the user writes Roman Urdu in the Latin alphabet, reply in Roman Urdu with natural English technical terms. Never convert Roman Urdu into Hindi/Devanagari script unless the user explicitly asks for Hindi/Devanagari.
14. Saved user memories are explicit user-provided preferences or context. Use them when relevant, but the user's current instruction always overrides an older memory.
15. Default to concise answers. Do not turn a simple question into a long article, table, or checklist unless the user asks for detail or the task genuinely requires it.
16. Answer the user's actual question first, then stop when the useful answer is complete. Avoid generic extra advice and repeated warnings.
"""


CHAT_TITLE_INSTRUCTION = """
This is the first message of a new chat.
Before the actual answer, output exactly one metadata line in this format:
[[CHAT_TITLE: <short title>]]

Title rules:
- 3 to 6 words.
- Maximum 50 characters.
- Summarize the user's real topic or intent instead of copying the raw prompt.
- No quotes, Markdown, emoji, or trailing punctuation.
- Then continue with the normal answer on the next line.
- Never mention or explain the CHAT_TITLE metadata to the user.
"""


def parse_chat_title_response(
    content: str,
) -> tuple[str, str | None]:
    """Extract hidden chat-title metadata from a first-turn AI response."""

    text = str(content or "")

    match = re.match(
        r"^\s*\[\[CHAT_TITLE:\s*(.*?)\s*\]\]\s*(?:\r?\n)?",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return text.strip(), None

    title = " ".join(
        match.group(1).split()
    ).strip(" \"'`#*-")

    answer = text[match.end():].strip()

    if not title or not answer:
        return text.strip(), None

    if len(title) > 50:
        title = title[:50].rstrip()

    return answer, title


def get_ai_response(
    messages: list[dict[str, str]] | str,
    memories: list[dict[str, str]] | None = None,
    include_chat_title: bool = False,
) -> str | tuple[str, str | None]:

    if not client:
        raise ValueError(
            "GROQ_API_KEY is missing from the .env file"
        )

    # Backwards compatibility
    if isinstance(messages, str):
        messages = [
            {
                "role": "user",
                "content": messages,
            }
        ]

    conversation_messages = []

    for item in messages:
        role = item.get("role")
        content = str(
            item.get("content", "")
        ).strip()

        if role not in {
            "user",
            "assistant",
        }:
            continue

        if not content:
            continue

        conversation_messages.append(
            {
                "role": role,
                "content": content,
            }
        )

    latest_user_text = ""
    for item in reversed(conversation_messages):
        if item["role"] == "user":
            latest_user_text = item["content"]
            break

    system_prompt = SYSTEM_PROMPT.strip()

    if memories:
        memory_lines = [
            f"- {str(item.get('value', '')).strip()}"
            for item in memories
            if str(item.get("value", "")).strip()
        ]

        if memory_lines:
            system_prompt += (
                "\n\nSaved user memories (explicitly saved by this user):\n"
                + "\n".join(memory_lines)
            )

    if latest_user_text:
        system_prompt += (
            "\n\nLanguage instruction for this turn:\n"
            + language_instruction(latest_user_text)
        )
        system_prompt += (
            "\n\nResponse length instruction for this turn:\n"
            + response_style_instruction(latest_user_text)
        )

    if include_chat_title:
        system_prompt += (
            "\n\nChat title instruction for this first turn:\n"
            + CHAT_TITLE_INSTRUCTION.strip()
        )

    request_args = dict(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            *conversation_messages,
        ],
        temperature=0.7,
        max_completion_tokens=2048,
    )

    try:
        raw_response = (
            client.chat.completions
            .with_raw_response
            .create(**request_args)
        )

        capture_groq_usage(
            raw_response.headers,
            model=MODEL_NAME,
        )

        response = raw_response.parse()

    except Exception as exc:
        raw_error_response = getattr(
            exc,
            "response",
            None,
        )
        error_headers = getattr(
            raw_error_response,
            "headers",
            None,
        )
        status_code = getattr(
            exc,
            "status_code",
            None,
        )

        if error_headers:
            capture_groq_usage(
                error_headers,
                model=MODEL_NAME,
                rate_limited=(status_code == 429),
            )

        raise

    content = (
        response
        .choices[0]
        .message
        .content
    )

    if include_chat_title:
        return parse_chat_title_response(
            content
        )

    return content
