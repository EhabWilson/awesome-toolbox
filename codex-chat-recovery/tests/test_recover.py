import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from recover import export_sessions, recover_session, session_to_markdown


def write_jsonl(path: Path, records, damaged_line=False):
    lines = [json.dumps(record, ensure_ascii=False) for record in records]
    if damaged_line:
        lines.insert(1, "{not valid json")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class RecoverSessionTests(unittest.TestCase):
    def test_recovers_response_messages_and_skips_private_event_types(self):
        records = [
            {
                "timestamp": "2026-08-24T09:00:00Z",
                "type": "session_meta",
                "payload": {"id": "session-1", "cwd": "/tmp/project"},
            },
            {
                "timestamp": "2026-08-24T09:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "恢复这段聊天"}],
                },
            },
            {
                "timestamp": "2026-08-24T09:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "<environment_context>private runtime data</environment_context>",
                        }
                    ],
                },
            },
            {
                "timestamp": "2026-08-24T09:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "reasoning",
                    "summary": [{"text": "should not be exported"}],
                },
            },
            {
                "timestamp": "2026-08-24T09:00:03Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "phase": "commentary",
                    "content": [{"type": "output_text", "text": "处理中"}],
                },
            },
            {
                "timestamp": "2026-08-24T09:00:04Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "phase": "final_answer",
                    "content": [{"type": "output_text", "text": "已经恢复"}],
                },
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rollout.jsonl"
            write_jsonl(path, records, damaged_line=True)
            session = recover_session(path)

        self.assertEqual(session.session_id, "session-1")
        self.assertEqual([message.text for message in session.messages], ["恢复这段聊天", "已经恢复"])
        self.assertEqual(len(session.parse_errors), 1)
        self.assertNotIn("should not be exported", session_to_markdown(session))

    def test_can_include_commentary(self):
        records = [
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "phase": "commentary",
                    "content": [{"type": "output_text", "text": "进度更新"}],
                },
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rollout.jsonl"
            write_jsonl(path, records)
            hidden = recover_session(path)
            visible = recover_session(path, include_commentary=True)

        self.assertEqual(hidden.messages, [])
        self.assertEqual(visible.messages[0].text, "进度更新")

    def test_uses_event_messages_as_fallback(self):
        records = [
            {"type": "event_msg", "payload": {"type": "user_message", "message": "旧用户消息"}},
            {"type": "event_msg", "payload": {"type": "agent_message", "message": "旧助手消息"}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rollout.jsonl"
            write_jsonl(path, records)
            session = recover_session(path)

        self.assertEqual([message.role for message in session.messages], ["user", "assistant"])

    def test_exports_markdown_without_overwriting_existing_file(self):
        records = [
            {
                "type": "session_meta",
                "payload": {"id": "same-id", "timestamp": "2026-08-24T09:00:00Z"},
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "hello"}],
                },
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "rollout.jsonl"
            output = root / "exports"
            write_jsonl(source, records)
            session = recover_session(source)
            first = export_sessions([session], output, "markdown")
            second = export_sessions([session], output, "markdown")

            files = list(output.glob("*.md"))

        self.assertEqual(first, (1, 0))
        self.assertEqual(second, (1, 0))
        self.assertEqual(len(files), 2)


if __name__ == "__main__":
    unittest.main()
