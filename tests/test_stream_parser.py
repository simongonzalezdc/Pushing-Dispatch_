import unittest

from dispatch_lib.stream_parser import count_turns, extract_final_text, extract_token_usage


class ClaudeStreamParserTests(unittest.TestCase):
    def setUp(self):
        self.events = [
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "Status: DONE"}],
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                },
            },
            {
                "type": "result",
                "subtype": "success",
                "num_turns": 2,
                "result": "First heading: # TasteCheck\n\nStatus: DONE",
                "usage": {"input_tokens": 1823, "output_tokens": 74},
            },
        ]

    def test_extracts_terminal_result_from_current_claude_jsonl(self):
        self.assertEqual(
            extract_final_text(self.events),
            "First heading: # TasteCheck\n\nStatus: DONE",
        )

    def test_extracts_result_usage(self):
        self.assertEqual(
            extract_token_usage(self.events),
            {"tokens_in": 1823, "tokens_out": 74},
        )

    def test_extracts_result_turn_count(self):
        self.assertEqual(count_turns(self.events), 2)


if __name__ == "__main__":
    unittest.main()
