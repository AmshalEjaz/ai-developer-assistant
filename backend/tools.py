from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx


# ============================================================
# LIMITS
# ============================================================

MAX_UPLOAD_BYTES = (
    2 * 1024 * 1024
)

DEFAULT_READ_LINES = 200
MAX_READ_LINES = 400
MAX_READ_CHARS = 16000

MAX_ANALYZE_CODE_CHARS = 20000

MAX_PYTHON_CODE_CHARS = 12000
MAX_PYTHON_OUTPUT_CHARS = 8000
PYTHON_TIMEOUT_SECONDS = 5

MAX_SEARCH_RESULTS = 5


ALLOWED_TEXT_EXTENSIONS = {
    ".py",
    ".php",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".cs",
    ".sql",
    ".json",
    ".html",
    ".css",
    ".md",
    ".txt",
    ".xml",
    ".yml",
    ".yaml",
}


# ============================================================
# RESULT HELPERS
# ============================================================

def tool_success(
    tool: str,
    data: Any,
) -> dict:

    return {
        "ok": True,
        "tool": tool,
        "data": data,
        "error": None,
    }


def tool_error(
    tool: str,
    code: str,
    message: str,
    *,
    details: Any = None,
) -> dict:

    error = {
        "code": code,
        "message": message,
    }

    if details is not None:
        error["details"] = details

    return {
        "ok": False,
        "tool": tool,
        "data": None,
        "error": error,
    }


# ============================================================
# COMMON HELPERS
# ============================================================

def _safe_int(
    value: Any,
    default: int,
    minimum: int,
    maximum: int,
) -> int:

    try:
        result = int(value)
    except (TypeError, ValueError):
        result = default

    return max(
        minimum,
        min(result, maximum),
    )


def _is_inside_workspace(
    file_path: Path,
    workspace_path: Path,
) -> bool:

    try:
        file_path.relative_to(
            workspace_path
        )
        return True

    except ValueError:
        return False


def _validate_active_file(
    context: dict,
) -> tuple[
    Path | None,
    Path | None,
    dict | None,
]:

    workspace_raw = context.get(
        "workspace_path"
    )

    file_raw = context.get(
        "active_file_path"
    )

    if not workspace_raw:
        return (
            None,
            None,
            tool_error(
                "read_file",
                "WORKSPACE_UNAVAILABLE",
                "No conversation workspace is available.",
            ),
        )

    if not file_raw:
        return (
            None,
            None,
            tool_error(
                "read_file",
                "NO_ACTIVE_FILE",
                "No file is attached to this conversation.",
            ),
        )

    try:
        workspace = (
            Path(workspace_raw)
            .expanduser()
            .resolve()
        )

        file_path = (
            Path(file_raw)
            .expanduser()
            .resolve()
        )

    except Exception:
        return (
            None,
            None,
            tool_error(
                "read_file",
                "INVALID_FILE_PATH",
                "The attached file path is invalid.",
            ),
        )

    if not _is_inside_workspace(
        file_path,
        workspace,
    ):
        return (
            None,
            None,
            tool_error(
                "read_file",
                "WORKSPACE_VIOLATION",
                "The requested file is outside the allowed workspace.",
            ),
        )

    if not file_path.exists():
        return (
            None,
            None,
            tool_error(
                "read_file",
                "FILE_NOT_FOUND",
                "The attached file could not be found.",
            ),
        )

    if not file_path.is_file():
        return (
            None,
            None,
            tool_error(
                "read_file",
                "INVALID_FILE",
                "The requested path is not a file.",
            ),
        )

    extension = (
        file_path
        .suffix
        .lower()
    )

    if extension not in ALLOWED_TEXT_EXTENSIONS:
        return (
            None,
            None,
            tool_error(
                "read_file",
                "UNSUPPORTED_FILE",
                "This file type is not supported.",
            ),
        )

    if file_path.stat().st_size > MAX_UPLOAD_BYTES:
        return (
            None,
            None,
            tool_error(
                "read_file",
                "FILE_TOO_LARGE",
                "The attached file exceeds the 2 MB limit.",
            ),
        )

    return (
        workspace,
        file_path,
        None,
    )


# ============================================================
# READ FILE
# ============================================================

def read_file(
    arguments: dict,
    context: dict,
) -> dict:

    (
        _workspace,
        file_path,
        validation_error,
    ) = _validate_active_file(
        context
    )

    if validation_error:
        return validation_error

    start_line = _safe_int(
        arguments.get("start_line"),
        default=1,
        minimum=1,
        maximum=1_000_000,
    )

    max_lines = _safe_int(
        arguments.get("max_lines"),
        default=DEFAULT_READ_LINES,
        minimum=1,
        maximum=MAX_READ_LINES,
    )

    try:
        content = file_path.read_text(
            encoding="utf-8-sig",
        )

    except UnicodeDecodeError:
        return tool_error(
            "read_file",
            "TEXT_DECODE_ERROR",
            "The attached file is not valid UTF-8 text.",
        )

    except OSError:
        return tool_error(
            "read_file",
            "FILE_READ_ERROR",
            "The attached file could not be read.",
        )

    lines = content.splitlines()

    total_lines = len(lines)

    if total_lines == 0:
        return tool_success(
            "read_file",
            {
                "filename":
                    file_path.name,

                "start_line": 1,
                "end_line": 0,
                "total_lines": 0,
                "has_more": False,
                "truncated": False,
                "content": "",
            },
        )

    if start_line > total_lines:
        return tool_error(
            "read_file",
            "INVALID_LINE_RANGE",
            (
                f"start_line {start_line} exceeds "
                f"the file's {total_lines} lines."
            ),
        )

    start_index = (
        start_line - 1
    )

    end_index = min(
        start_index + max_lines,
        total_lines,
    )

    selected = lines[
        start_index:end_index
    ]

    numbered_lines = []

    for index, line in enumerate(
        selected,
        start=start_line,
    ):
        numbered_lines.append(
            f"{index}: {line}"
        )

    rendered = "\n".join(
        numbered_lines
    )

    truncated = False

    if len(rendered) > MAX_READ_CHARS:
        rendered = (
            rendered[
                :MAX_READ_CHARS
            ]
            + "\n...[chunk truncated]"
        )

        truncated = True

    return tool_success(
        "read_file",
        {
            "filename":
                file_path.name,

            "start_line":
                start_line,

            "end_line":
                end_index,

            "total_lines":
                total_lines,

            "has_more":
                end_index < total_lines,

            "next_start_line": (
                end_index + 1
                if end_index < total_lines
                else None
            ),

            "truncated":
                truncated,

            "content":
                rendered,
        },
    )


# ============================================================
# ANALYZE CODE
# ============================================================

def _detect_language(
    code: str,
    declared_language: str | None,
) -> str:

    declared = (
        str(declared_language or "")
        .strip()
        .lower()
    )

    aliases = {
        "py": "python",
        "js": "javascript",
        "ts": "typescript",
        "cs": "csharp",
    }

    if declared:
        return aliases.get(
            declared,
            declared,
        )

    stripped = code.strip()

    if (
        "<?php" in stripped
        or "$this->" in stripped
    ):
        return "php"

    if (
        "def " in stripped
        or "import " in stripped
        or "print(" in stripped
    ):
        return "python"

    if (
        "SELECT " in stripped.upper()
        or "INSERT INTO " in stripped.upper()
        or "UPDATE " in stripped.upper()
    ):
        return "sql"

    if (
        "const " in stripped
        or "let " in stripped
        or "function " in stripped
        or "=>" in stripped
    ):
        return "javascript"

    if (
        stripped.startswith("{")
        or stripped.startswith("[")
    ):
        try:
            json.loads(stripped)
            return "json"
        except Exception:
            pass

    return "unknown"


def analyze_code(
    arguments: dict,
    context: dict,
) -> dict:

    del context

    code = str(
        arguments.get(
            "code",
            "",
        )
    )

    if not code.strip():
        return tool_error(
            "analyze_code",
            "EMPTY_CODE",
            "No code was provided for analysis.",
        )

    if len(code) > MAX_ANALYZE_CODE_CHARS:
        return tool_error(
            "analyze_code",
            "CODE_TOO_LARGE",
            (
                "The code chunk is too large. "
                "Read or analyze a smaller section."
            ),
        )

    language = _detect_language(
        code,
        arguments.get("language"),
    )

    lines = code.splitlines()

    syntax_valid = None
    syntax_error = None

    if language == "python":

        try:
            ast.parse(code)
            syntax_valid = True

        except SyntaxError as error:
            syntax_valid = False

            syntax_error = {
                "message":
                    error.msg,

                "line":
                    error.lineno,

                "offset":
                    error.offset,
            }

    elif language == "json":

        try:
            json.loads(code)
            syntax_valid = True

        except json.JSONDecodeError as error:
            syntax_valid = False

            syntax_error = {
                "message":
                    error.msg,

                "line":
                    error.lineno,

                "column":
                    error.colno,
            }

    return tool_success(
        "analyze_code",
        {
            "language":
                language,

            "line_count":
                len(lines),

            "character_count":
                len(code),

            "syntax_checked":
                syntax_valid is not None,

            "syntax_valid":
                syntax_valid,

            "syntax_error":
                syntax_error,

            "analysis_note": (
                "Use this deterministic result together "
                "with the code itself for semantic, logical, "
                "framework, and best-practice analysis."
            ),
        },
    )


# ============================================================
# RUN PYTHON
# ============================================================

FORBIDDEN_PYTHON_CALLS = {
    "__import__",
    "breakpoint",
    "compile",
    "dir",
    "eval",
    "exec",
    "getattr",
    "globals",
    "help",
    "input",
    "locals",
    "open",
    "setattr",
    "vars",
}


FORBIDDEN_ATTRIBUTE_NAMES = {
    "system",
    "popen",
    "spawn",
    "fork",
    "remove",
    "unlink",
    "rmdir",
    "chmod",
    "chown",
    "kill",
    "connect",
    "bind",
    "listen",
    "accept",
}


def _validate_python_code(
    code: str,
) -> str | None:

    try:
        tree = ast.parse(code)

    except SyntaxError as error:
        return (
            f"Python syntax error on line "
            f"{error.lineno}: {error.msg}"
        )

    for node in ast.walk(tree):

        if isinstance(
            node,
            (
                ast.Import,
                ast.ImportFrom,
            ),
        ):
            return (
                "Python imports are disabled "
                "in the restricted runner."
            )

        if isinstance(
            node,
            ast.Call,
        ):
            if isinstance(
                node.func,
                ast.Name,
            ):
                if (
                    node.func.id
                    in FORBIDDEN_PYTHON_CALLS
                ):
                    return (
                        f"{node.func.id}() is not "
                        "allowed in the restricted runner."
                    )

        if isinstance(
            node,
            ast.Attribute,
        ):
            attribute = node.attr

            if attribute.startswith("__"):
                return (
                    "Dunder attribute access is disabled "
                    "in the restricted runner."
                )

            if (
                attribute
                in FORBIDDEN_ATTRIBUTE_NAMES
            ):
                return (
                    f"Attribute '{attribute}' is not "
                    "allowed in the restricted runner."
                )

        if isinstance(
            node,
            ast.Name,
        ):
            if node.id in {
                "__builtins__",
                "__loader__",
                "__spec__",
            }:
                return (
                    f"Name '{node.id}' is not allowed "
                    "in the restricted runner."
                )

    return None


def _trim_output(
    text: str,
) -> tuple[str, bool]:

    if len(text) <= MAX_PYTHON_OUTPUT_CHARS:
        return text, False

    return (
        text[
            :MAX_PYTHON_OUTPUT_CHARS
        ]
        + "\n...[output truncated]",
        True,
    )


def run_python(
    arguments: dict,
    context: dict,
) -> dict:

    del context

    code = str(
        arguments.get(
            "code",
            "",
        )
    )

    if not code.strip():
        return tool_error(
            "run_python",
            "EMPTY_CODE",
            "No Python code was provided.",
        )

    if len(code) > MAX_PYTHON_CODE_CHARS:
        return tool_error(
            "run_python",
            "CODE_TOO_LARGE",
            "The Python snippet is too large to execute.",
        )

    safety_error = (
        _validate_python_code(
            code
        )
    )

    if safety_error:
        return tool_error(
            "run_python",
            "UNSAFE_PYTHON",
            safety_error,
        )

    safe_environment = {
        "PYTHONIOENCODING":
            "utf-8",
    }

    for name in (
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
    ):
        value = os.environ.get(
            name
        )

        if value:
            safe_environment[name] = value

    try:
        with tempfile.TemporaryDirectory() as temp_dir:

            completed = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-S",
                    "-c",
                    code,
                ],

                cwd=temp_dir,

                env=safe_environment,

                capture_output=True,

                text=True,

                encoding="utf-8",

                errors="replace",

                timeout=
                    PYTHON_TIMEOUT_SECONDS,

                shell=False,

                check=False,
            )

    except subprocess.TimeoutExpired:
        return tool_error(
            "run_python",
            "PYTHON_TIMEOUT",
            (
                "Python execution exceeded the "
                f"{PYTHON_TIMEOUT_SECONDS}-second limit."
            ),
        )

    except Exception:
        return tool_error(
            "run_python",
            "PYTHON_EXECUTION_ERROR",
            "The Python snippet could not be executed.",
        )

    stdout, stdout_truncated = (
        _trim_output(
            completed.stdout or ""
        )
    )

    stderr, stderr_truncated = (
        _trim_output(
            completed.stderr or ""
        )
    )

    if completed.returncode != 0:

        return tool_error(
            "run_python",
            "PYTHON_RUNTIME_ERROR",
            "The Python snippet returned an error.",
            details={
                "return_code":
                    completed.returncode,

                "stdout":
                    stdout,

                "stderr":
                    stderr,

                "output_truncated":
                    (
                        stdout_truncated
                        or stderr_truncated
                    ),
            },
        )

    return tool_success(
        "run_python",
        {
            "return_code":
                completed.returncode,

            "stdout":
                stdout,

            "stderr":
                stderr,

            "output_truncated":
                (
                    stdout_truncated
                    or stderr_truncated
                ),
        },
    )


# ============================================================
# SEARCH DOCUMENTATION
# ============================================================

def search_documentation(
    arguments: dict,
    context: dict,
) -> dict:

    del context

    query = str(
        arguments.get(
            "query",
            "",
        )
    ).strip()

    if not query:
        return tool_error(
            "search_documentation",
            "EMPTY_QUERY",
            "A documentation search query is required.",
        )

    api_key = os.getenv(
        "SERPER_API_KEY"
    )

    if not api_key:
        return tool_error(
            "search_documentation",
            "SEARCH_UNAVAILABLE",
            "Live documentation search is not configured.",
        )

    result_count = _safe_int(
        arguments.get("max_results"),
        default=5,
        minimum=1,
        maximum=MAX_SEARCH_RESULTS,
    )

    try:
        response = httpx.post(
            "https://google.serper.dev/search",

            headers={
                "X-API-KEY":
                    api_key,

                "Content-Type":
                    "application/json",
            },

            json={
                "q":
                    query,

                "num":
                    result_count,
            },

            timeout=8.0,
        )

        response.raise_for_status()

        payload = response.json()

    except (
        httpx.HTTPError,
        ValueError,
    ):
        return tool_error(
            "search_documentation",
            "SEARCH_PROVIDER_ERROR",
            (
                "Live documentation search is "
                "temporarily unavailable."
            ),
        )

    normalized_results = []

    for item in (
        payload.get("organic")
        or []
    )[:result_count]:

        link = str(
            item.get(
                "link",
                "",
            )
        ).strip()

        if not link:
            continue

        parsed = urlparse(
            link
        )

        normalized_results.append(
            {
                "title":
                    str(
                        item.get(
                            "title",
                            "",
                        )
                    ).strip(),

                "url":
                    link,

                "domain":
                    parsed.netloc,

                "snippet":
                    str(
                        item.get(
                            "snippet",
                            "",
                        )
                    ).strip(),
            }
        )

    return tool_success(
        "search_documentation",
        {
            "query":
                query,

            "results":
                normalized_results,

            "result_count":
                len(
                    normalized_results
                ),
        },
    )


# ============================================================
# TOOL REGISTRY
# ============================================================

TOOL_REGISTRY = {

    "read_file": {
        "description": (
            "Read a bounded range of lines from the "
            "single active developer file attached to "
            "the current conversation. Use this when "
            "the user's question depends on file content."
        ),

        "parameters": {
            "type": "object",

            "properties": {
                "start_line": {
                    "type": "integer",
                    "minimum": 1,
                    "description": (
                        "First 1-based line to read."
                    ),
                },

                "max_lines": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum":
                        MAX_READ_LINES,

                    "description": (
                        "Maximum number of lines to return."
                    ),
                },
            },

            "additionalProperties":
                False,
        },

        "handler":
            read_file,
    },

    "analyze_code": {
        "description": (
            "Perform lightweight deterministic analysis "
            "of a code snippet, including language "
            "identification and syntax validation where "
            "supported. Use it before reasoning about "
            "code when structured diagnostics help."
        ),

        "parameters": {
            "type": "object",

            "properties": {
                "code": {
                    "type": "string",
                    "description":
                        "Code snippet to inspect.",
                },

                "language": {
                    "type": "string",
                    "description": (
                        "Optional language name such as "
                        "python, php, javascript, sql, "
                        "json, or csharp."
                    ),
                },
            },

            "required": [
                "code",
            ],

            "additionalProperties":
                False,
        },

        "handler":
            analyze_code,
    },

    "run_python": {
        "description": (
            "Execute a small restricted Python snippet "
            "for calculation, debugging, or verification. "
            "Imports, file access, shell execution, and "
            "dangerous runtime capabilities are disabled."
        ),

        "parameters": {
            "type": "object",

            "properties": {
                "code": {
                    "type": "string",
                    "description": (
                        "Small Python snippet to execute."
                    ),
                },
            },

            "required": [
                "code",
            ],

            "additionalProperties":
                False,
        },

        "handler":
            run_python,
    },

    "search_documentation": {
        "description": (
            "Search current developer documentation "
            "and technical sources using live web search. "
            "Use when up-to-date library, framework, API, "
            "or documentation information is needed."
        ),

        "parameters": {
            "type": "object",

            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Focused developer documentation "
                        "search query. Prefer official "
                        "documentation wording when possible."
                    ),
                },

                "max_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum":
                        MAX_SEARCH_RESULTS,
                },
            },

            "required": [
                "query",
            ],

            "additionalProperties":
                False,
        },

        "handler":
            search_documentation,
    },
}


# ============================================================
# PUBLIC REGISTRY API
# ============================================================

def get_tool_schemas() -> list[dict]:

    schemas = []

    for name, definition in (
        TOOL_REGISTRY.items()
    ):

        schemas.append(
            {
                "type": "function",

                "function": {
                    "name":
                        name,

                    "description":
                        definition[
                            "description"
                        ],

                    "parameters":
                        definition[
                            "parameters"
                        ],
                },
            }
        )

    return schemas


def execute_tool(
    name: str,
    arguments: dict | None,
    context: dict | None,
) -> dict:

    definition = (
        TOOL_REGISTRY.get(
            str(name or "")
        )
    )

    if not definition:
        return tool_error(
            str(name or "unknown"),
            "UNKNOWN_TOOL",
            "The requested tool is not available.",
        )

    if arguments is None:
        arguments = {}

    if context is None:
        context = {}

    if not isinstance(
        arguments,
        dict,
    ):
        return tool_error(
            name,
            "INVALID_ARGUMENTS",
            "Tool arguments must be an object.",
        )

    if not isinstance(
        context,
        dict,
    ):
        return tool_error(
            name,
            "INVALID_CONTEXT",
            "Tool execution context is invalid.",
        )

    try:
        return definition[
            "handler"
        ](
            arguments,
            context,
        )

    except Exception:
        return tool_error(
            name,
            "TOOL_EXECUTION_ERROR",
            (
                "The tool could not complete "
                "the requested operation."
            ),
        )