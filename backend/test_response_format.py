import unittest
from pathlib import Path


class TestResponseFormattingPrompt(unittest.TestCase):
    def test_system_prompt_requires_language_tagged_fenced_code(self):
        source = Path(__file__).with_name("agent.py").read_text(encoding="utf-8")
        self.assertIn("fenced Markdown code blocks", source)
        self.assertIn("correct language tag", source)


if __name__ == "__main__":
    unittest.main()
