import os

from dotenv import load_dotenv
from groq import Groq


load_dotenv()


api_key = os.getenv("GROQ_API_KEY")

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
"""


def get_ai_response(
    messages: list[dict[str, str]] | str,
) -> str:

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

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            *conversation_messages,
        ],
        temperature=0.7,
        max_completion_tokens=2048,
    )

    return (
        response
        .choices[0]
        .message
        .content
    )