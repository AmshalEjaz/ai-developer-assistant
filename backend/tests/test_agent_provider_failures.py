"""Provider fallback regression tests do not make live network requests."""
import importlib.util
import sys
import types

if "groq" not in sys.modules and importlib.util.find_spec("groq") is None:
    groq_stub = types.ModuleType("groq")
    groq_stub.Groq = lambda *args, **kwargs: None
    sys.modules["groq"] = groq_stub

import pytest
import agent


def test_gemini_fallback_is_used_when_groq_fails(monkeypatch):
    monkeypatch.setattr(agent, "_get_groq_ai_response", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("quota")))
    monkeypatch.setattr(agent, "_get_gemini_response", lambda *args, **kwargs: "fallback answer")
    assert agent.get_ai_response("hello") == "fallback answer"


def test_provider_failure_is_reported_when_both_providers_fail(monkeypatch):
    monkeypatch.setattr(agent, "_get_groq_ai_response", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("quota")))
    monkeypatch.setattr(agent, "_get_gemini_response", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("unavailable")))
    with pytest.raises(RuntimeError, match="Groq failed.*Gemini fallback failed"):
        agent.get_ai_response("hello")


def test_agent_supports_multiple_tool_calls_in_one_turn(monkeypatch):
    from types import SimpleNamespace

    calls = []
    def tool_call(call_id, name, arguments):
        return SimpleNamespace(
            id=call_id,
            function=SimpleNamespace(name=name, arguments=arguments),
        )

    first_message = SimpleNamespace(
        content="Checking two things.",
        tool_calls=[
            tool_call("call-1", "analyze_code", '{"code":"x = 1"}'),
            tool_call("call-2", "analyze_code", '{"code":"y = 2"}'),
        ],
    )
    final_message = SimpleNamespace(content="Both checks are complete.", tool_calls=[])
    responses = iter([
        SimpleNamespace(choices=[SimpleNamespace(message=first_message)]),
        SimpleNamespace(choices=[SimpleNamespace(message=final_message)]),
    ])
    monkeypatch.setattr(agent, "client", object())
    monkeypatch.setattr(agent, "_capture_completion", lambda args: next(responses))
    def fake_execute_tool(name, arguments, context):
        calls.append((name, arguments["code"]))
        return {"ok": True, "tool": name, "data": {"checked": True}, "error": None}
    monkeypatch.setattr(agent, "execute_tool", fake_execute_tool)

    answer = agent._get_groq_ai_response("Review these examples")
    assert answer == "Both checks are complete."
    assert calls == [("analyze_code", "x = 1"), ("analyze_code", "y = 2")]
