import io
import zipfile

import pytest

from project_zip import inspect_project_zip


def make_zip(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return buffer.getvalue()


def test_rejects_non_zip_input():
    with pytest.raises(ValueError, match="valid .zip"):
        inspect_project_zip(b"not a zip", "review project")


def test_skips_path_traversal_secrets_dependencies_and_binary_files():
    payload = make_zip([
        ("../outside.py", "print('outside')"),
        ("src/main.py", "api_key = 'sk-abcdefghijklmnopqrstuvwxyz'"),
        (".env", "SECRET=super-secret-value"),
        ("node_modules/pkg/index.js", "ignored()"),
        ("assets/image.png", "not really png"),
        ("README.md", "Project overview"),
    ])
    result = inspect_project_zip(payload, "review main code")
    paths = [item["path"] for item in result["files"]]
    assert "../outside.py" not in paths
    assert ".env" not in paths
    assert not any("node_modules" in path for path in paths)
    assert not any(path.endswith(".png") for path in paths)
    rendered = "\n".join(item["content"] for item in result["files"])
    assert "super-secret-value" not in rendered
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in rendered


def test_rejects_too_many_entries():
    payload = make_zip([(f"file{i}.py", "x=1") for i in range(251)])
    with pytest.raises(ValueError, match="too many entries"):
        inspect_project_zip(payload, "review")


def test_rejects_oversized_archive_bytes():
    with pytest.raises(ValueError, match="15 MB"):
        inspect_project_zip(b"x" * (15 * 1024 * 1024 + 1), "review")


def test_zip_is_inspected_without_extracting_and_returns_bounded_text():
    payload = make_zip([
        ("backend/main.py", "def main():\n    return 'hello'\n"),
        ("frontend/App.jsx", "export default function App() { return null; }\n"),
    ])
    result = inspect_project_zip(payload, "review main")
    assert result["file_count"] >= 1
    assert result["characters_sent"] <= 36_000
    assert all("content" in item and "path" in item for item in result["files"])
