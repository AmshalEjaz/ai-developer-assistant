from tools import read_file, run_python


def test_python_execution_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("DEVPILOT_ENABLE_UNSANDBOXED_PYTHON", raising=False)
    result = run_python({"code": "print('should not run')"}, {})
    assert result["ok"] is False
    assert result["error"]["code"] == "PYTHON_EXECUTION_DISABLED"


def test_environment_flag_cannot_enable_unsandboxed_python(monkeypatch):
    monkeypatch.setenv("DEVPILOT_ENABLE_UNSANDBOXED_PYTHON", "true")
    result = run_python({"code": "print('must not execute')"}, {})
    assert result["ok"] is False
    assert result["error"]["code"] == "PYTHON_EXECUTION_DISABLED"


def test_read_file_requires_an_active_file_context():
    result = read_file({}, {})
    assert result["ok"] is False
    assert result["error"]["code"] in {"NO_ACTIVE_FILE", "ACTIVE_FILE_NOT_FOUND", "INVALID_ACTIVE_FILE", "WORKSPACE_UNAVAILABLE"}


def test_read_file_rejects_path_outside_active_workspace(tmp_path):
    from pathlib import Path
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("SECRET = 'not for this conversation'", encoding="utf-8")
    result = read_file({"path": str(outside)}, {
        "workspace_path": str(workspace),
        "active_file_path": str(outside),
        "active_file_name": "outside.py",
    })
    assert result["ok"] is False
    assert result["error"]["code"] == "WORKSPACE_VIOLATION"


def test_python_execution_does_not_run_malicious_payload_even_with_legacy_flag(monkeypatch):
    marker = __import__("pathlib").Path(__file__).with_name("must_not_be_created.txt")
    marker.unlink(missing_ok=True)
    monkeypatch.setenv("DEVPILOT_ENABLE_UNSANDBOXED_PYTHON", "true")
    code = f"open({str(marker)!r}, 'w').write('executed')"
    result = run_python({"code": code}, {})
    assert result["error"]["code"] == "PYTHON_EXECUTION_DISABLED"
    assert not marker.exists()
