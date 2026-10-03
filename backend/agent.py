import json
import os
import re

from dotenv import load_dotenv
from groq import Groq

from groq_usage import capture_groq_usage
from memory import language_instruction
from response_policy import response_style_instruction
from tools import execute_tool, get_tool_schemas


load_dotenv()


api_key = os.getenv("GROQ_API_KEY")
MODEL_NAME = "openai/gpt-oss-120b"
MAX_TOOL_CALLS = 5

client = Groq(api_key=api_key) if api_key else None


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
17. Use tools only when they materially help answer the user's request. Do not call a tool for ordinary conversation or for information already present in the chat.
18. If an attached file is relevant, use read_file in bounded chunks instead of asking for the whole file to be pasted.
19. You may make multiple tool calls when needed, but stop as soon as you have enough evidence.
20. Never invent a tool result. If a tool returns an error, either recover with another safe tool call or explain the limitation clearly.
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


def parse_chat_title_response(content: str) -> tuple[str, str | None]:
    """Extract hidden chat-title metadata from a first-turn AI response."""
    text = str(content or "")
    match = re.match(
        r"^\s*\[\[CHAT_TITLE:\s*(.*?)\s*\]\]\s*(?:\r?\n)?",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return text.strip(), None
    title = " ".join(match.group(1).split()).strip(" \"'`#*-")
    answer = text[match.end():].strip()
    if not title or not answer:
        return text.strip(), None
    if len(title) > 50:
        title = title[:50].rstrip()
    return answer, title


def _capture_completion(request_args: dict):
    try:
        raw_response = client.chat.completions.with_raw_response.create(**request_args)
        capture_groq_usage(raw_response.headers, model=MODEL_NAME)
        return raw_response.parse()
    except Exception as exc:
        raw_error_response = getattr(exc, "response", None)
        error_headers = getattr(raw_error_response, "headers", None)
        status_code = getattr(exc, "status_code", None)
        if error_headers:
            capture_groq_usage(
                error_headers,
                model=MODEL_NAME,
                rate_limited=(status_code == 429),
            )
        raise


def _tool_call_dict(tool_call) -> dict:
    return {
        "id": tool_call.id,
        "type": getattr(tool_call, "type", "function") or "function",
        "function": {
            "name": tool_call.function.name,
            "arguments": tool_call.function.arguments or "{}",
        },
    }


def _invalid_arguments_result(tool_name: str, message: str) -> dict:
    return {
        "ok": False,
        "tool": tool_name,
        "data": None,
        "error": {
            "code": "INVALID_ARGUMENTS",
            "message": message,
        },
    }


def get_ai_response(
    messages: list[dict[str, str]] | str,
    memories: list[dict[str, str]] | None = None,
    include_chat_title: bool = False,
    tool_context: dict | None = None,
) -> str | tuple[str, str | None]:
    if not client:
        raise ValueError("GROQ_API_KEY is missing from the .env file")

    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]

    conversation_messages = []
    for item in messages:
        role = item.get("role")
        content = str(item.get("content", "")).strip()
        if role not in {"user", "assistant"} or not content:
            continue
        conversation_messages.append({"role": role, "content": content})

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
            system_prompt += "\n\nSaved user memories (explicitly saved by this user):\n" + "\n".join(memory_lines)

    if latest_user_text:
        system_prompt += "\n\nLanguage instruction for this turn:\n" + language_instruction(latest_user_text)
        system_prompt += "\n\nResponse length instruction for this turn:\n" + response_style_instruction(latest_user_text)

    if include_chat_title:
        system_prompt += "\n\nChat title instruction for this first turn:\n" + CHAT_TITLE_INSTRUCTION.strip()

    if tool_context and tool_context.get("active_file_name"):
        system_prompt += (
            "\n\nAttached file available for this conversation: "
            + str(tool_context["active_file_name"])
            + ". Read it with read_file only when relevant."
        )

    working_messages = [
        {"role": "system", "content": system_prompt},
        *conversation_messages,
    ]
    tool_context = tool_context or {}
    total_tool_calls = 0
    force_final = False

    while True:
        request_args = {
            "model": MODEL_NAME,
            "messages": working_messages,
            "temperature": 0.7,
            "max_completion_tokens": 2048,
        }
        if not force_final:
            request_args["tools"] = get_tool_schemas()
            request_args["tool_choice"] = "auto"

        response = _capture_completion(request_args)
        message = response.choices[0].message
        tool_calls = list(getattr(message, "tool_calls", None) or [])

        if not tool_calls:
            content = str(getattr(message, "content", "") or "").strip()
            if include_chat_title:
                return parse_chat_title_response(content)
            return content

        working_messages.append({
            "role": "assistant",
            "content": getattr(message, "content", None) or "",
            "tool_calls": [_tool_call_dict(call) for call in tool_calls],
        })

        remaining = MAX_TOOL_CALLS - total_tool_calls
        for index, tool_call in enumerate(tool_calls):
            name = tool_call.function.name
            if index >= remaining:
                result = {
                    "ok": False,
                    "tool": name,
                    "data": None,
                    "error": {
                        "code": "TOOL_CALL_LIMIT_REACHED",
                        "message": f"The maximum of {MAX_TOOL_CALLS} tool calls for one message was reached.",
                    },
                }
            else:
                try:
                    arguments = json.loads(tool_call.function.arguments or "{}")
                    if not isinstance(arguments, dict):
                        raise ValueError("Tool arguments must be a JSON object.")
                except (json.JSONDecodeError, ValueError) as exc:
                    result = _invalid_arguments_result(name, str(exc))
                else:
                    result = execute_tool(name, arguments, tool_context)
                total_tool_calls += 1

            working_messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result, ensure_ascii=False),
            })

        if total_tool_calls >= MAX_TOOL_CALLS:
            force_final = True
