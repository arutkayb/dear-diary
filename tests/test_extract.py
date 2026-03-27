"""Unit tests for extract.py"""

import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from extract import (
    _is_subprocess_session,
    assemble_output,
    discover_sessions,
    extract_messages,
    filter_sessions_by_date,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


class TestExtractMessages(unittest.TestCase):
    def test_basic_text_messages_extracted(self):
        msgs = list(extract_messages(os.path.join(FIXTURES, "session_basic.jsonl")))
        self.assertEqual(len(msgs), 4)
        roles = [m["role"] for m in msgs]
        self.assertEqual(roles, ["user", "assistant", "user", "assistant"])

    def test_basic_text_content_correct(self):
        msgs = list(extract_messages(os.path.join(FIXTURES, "session_basic.jsonl")))
        self.assertEqual(msgs[0]["text"], "Hello, what can you do?")
        self.assertEqual(msgs[1]["text"], "I can help you with many things!")

    def test_imeta_messages_skipped(self):
        """isMeta=true messages must not appear in output."""
        msgs = list(extract_messages(os.path.join(FIXTURES, "session_mixed.jsonl")))
        # u1 is isMeta=true — should be skipped
        texts = [m["text"] for m in msgs]
        self.assertNotIn("Run the tests for me", texts)

    def test_tool_use_blocks_stripped(self):
        """tool_use blocks inside an assistant message should be dropped; text kept."""
        msgs = list(extract_messages(os.path.join(FIXTURES, "session_mixed.jsonl")))
        assistant_msgs = [m for m in msgs if m["role"] == "assistant"]
        # First assistant message has thinking + text + tool_use — only text survives
        self.assertEqual(assistant_msgs[0]["text"], "Sure, I will run the tests.")

    def test_thinking_blocks_stripped(self):
        """thinking blocks should not appear in extracted text."""
        msgs = list(extract_messages(os.path.join(FIXTURES, "session_mixed.jsonl")))
        for m in msgs:
            self.assertNotIn("Let me think about this...", m["text"])

    def test_tool_result_messages_skipped(self):
        """Messages whose content is only tool_result blocks yield no output."""
        msgs = list(extract_messages(os.path.join(FIXTURES, "session_mixed.jsonl")))
        texts = [m["text"] for m in msgs]
        self.assertNotIn("3 tests passed", texts)

    def test_malformed_lines_skipped_valid_extracted(self):
        """Malformed JSON lines are skipped; valid lines still extracted."""
        import io
        from contextlib import redirect_stderr

        stderr_capture = io.StringIO()
        with redirect_stderr(stderr_capture):
            msgs = list(extract_messages(os.path.join(FIXTURES, "session_malformed.jsonl")))

        # Two valid messages despite two broken lines
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]["text"], "First valid message")
        self.assertEqual(msgs[1]["text"], "Valid response after malformed line.")

        # Warnings were emitted to stderr
        warnings = stderr_capture.getvalue()
        self.assertIn("WARNING", warnings)

    def test_timestamps_present(self):
        msgs = list(extract_messages(os.path.join(FIXTURES, "session_basic.jsonl")))
        for m in msgs:
            self.assertIsNotNone(m["timestamp"])

    def test_cwd_present(self):
        msgs = list(extract_messages(os.path.join(FIXTURES, "session_basic.jsonl")))
        for m in msgs:
            self.assertEqual(m["cwd"], "/Users/test/project")


class TestFilterSessionsByDate(unittest.TestCase):
    def _make_session(self, tmpdir, session_id, timestamp_str):
        """Write a minimal JSONL file with one message at the given timestamp."""
        project_dir = os.path.join(tmpdir, "project")
        os.makedirs(project_dir, exist_ok=True)
        path = os.path.join(project_dir, f"{session_id}.jsonl")
        msg = {
            "parentUuid": None,
            "isSidechain": False,
            "type": "user",
            "message": {"role": "user", "content": "hello"},
            "isMeta": False,
            "uuid": session_id,
            "timestamp": timestamp_str,
            "cwd": tmpdir,
        }
        with open(path, "w") as f:
            f.write(json.dumps(msg) + "\n")
        return {"file_path": path, "session_id": session_id, "project_dir": "project"}

    def test_session_on_target_date_included(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session = self._make_session(tmpdir, "s1", "2026-03-25T12:00:00.000Z")
            local_tz = datetime.now().astimezone().tzinfo
            result = filter_sessions_by_date([session], date(2026, 3, 25), local_tz)
            self.assertEqual(len(result), 1)

    def test_session_on_different_date_excluded(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session = self._make_session(tmpdir, "s1", "2026-03-24T12:00:00.000Z")
            local_tz = datetime.now().astimezone().tzinfo
            result = filter_sessions_by_date([session], date(2026, 3, 25), local_tz)
            self.assertEqual(len(result), 0)

    def test_midnight_spanning_session_assigned_to_last_message_date(self):
        """A session with messages on Mar 25 23:50 and Mar 26 00:10 UTC goes to Mar 26 UTC."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = os.path.join(tmpdir, "project")
            os.makedirs(project_dir, exist_ok=True)
            path = os.path.join(project_dir, "midnight.jsonl")
            msgs = [
                {
                    "type": "user",
                    "message": {"role": "user", "content": "late message"},
                    "isMeta": False,
                    "uuid": "a",
                    "timestamp": "2026-03-25T23:50:00.000Z",
                    "cwd": tmpdir,
                },
                {
                    "type": "assistant",
                    "message": {"role": "assistant", "content": [{"type": "text", "text": "response"}]},
                    "isMeta": False,
                    "uuid": "b",
                    "timestamp": "2026-03-26T00:10:00.000Z",
                    "cwd": tmpdir,
                },
            ]
            with open(path, "w") as f:
                for m in msgs:
                    f.write(json.dumps(m) + "\n")

            session = {"file_path": path, "session_id": "midnight", "project_dir": "project"}
            # Use UTC timezone so Mar 26 00:10 UTC is Mar 26
            utc = timezone.utc
            result_mar26 = filter_sessions_by_date([session], date(2026, 3, 26), utc)
            result_mar25 = filter_sessions_by_date([session], date(2026, 3, 25), utc)
            self.assertEqual(len(result_mar26), 1, "session should be assigned to Mar 26")
            self.assertEqual(len(result_mar25), 0, "session should NOT be assigned to Mar 25")


class TestAssembleOutput(unittest.TestCase):
    def test_empty_sessions_produces_valid_output(self):
        """No matched sessions → valid JSON with zero stats and empty projects."""
        data = assemble_output(date(2026, 3, 25), [])
        self.assertEqual(data["date"], "2026-03-25")
        self.assertIn("extracted_at", data)
        self.assertEqual(data["stats"]["session_count"], 0)
        self.assertEqual(data["stats"]["project_count"], 0)
        self.assertEqual(data["stats"]["message_count"], 0)
        self.assertEqual(data["projects"], [])

    def test_output_schema_fields_present(self):
        """Output contains all required top-level fields with correct types."""
        session = {
            "file_path": os.path.join(FIXTURES, "session_basic.jsonl"),
            "session_id": "test-session",
            "project_dir": "project",
        }
        data = assemble_output(date(2026, 3, 25), [session])
        self.assertIsInstance(data["date"], str)
        self.assertIsInstance(data["extracted_at"], str)
        self.assertIsInstance(data["stats"], dict)
        self.assertIsInstance(data["projects"], list)

        self.assertIn("session_count", data["stats"])
        self.assertIn("project_count", data["stats"])
        self.assertIn("message_count", data["stats"])
        self.assertEqual(len(data["projects"]), 1)
        project = data["projects"][0]
        self.assertIn("project", project)
        self.assertIn("sessions", project)

        session_out = project["sessions"][0]
        self.assertIn("session_id", session_out)
        self.assertIn("time_range", session_out)
        self.assertIn("git_branch", session_out)
        self.assertIn("summary", session_out)
        self.assertIn("messages", session_out)

    def test_summary_is_first_user_message_truncated(self):
        session = {
            "file_path": os.path.join(FIXTURES, "session_basic.jsonl"),
            "session_id": "test-session",
            "project_dir": "project",
        }
        data = assemble_output(date(2026, 3, 25), [session])
        summary = data["projects"][0]["sessions"][0]["summary"]
        self.assertEqual(summary, "Hello, what can you do?")

    def test_stats_are_non_zero_for_real_session(self):
        session = {
            "file_path": os.path.join(FIXTURES, "session_basic.jsonl"),
            "session_id": "test-session",
            "project_dir": "project",
        }
        data = assemble_output(date(2026, 3, 25), [session])
        self.assertGreater(data["stats"]["session_count"], 0)
        self.assertGreater(data["stats"]["message_count"], 0)
    def test_project_key_uses_majority_cwd(self):
        """Session starting in parent dir but moving to subdirectory should be
        grouped under the subdirectory (majority cwd), not the parent."""
        session = {
            "file_path": os.path.join(FIXTURES, "session_multi_cwd.jsonl"),
            "session_id": "multi-cwd-session",
            "project_dir": "workspace",
        }
        data = assemble_output(date(2026, 3, 25), [session])
        self.assertEqual(len(data["projects"]), 1)
        # 6 messages have /my-website, 2 have /workspace — majority wins
        self.assertEqual(data["projects"][0]["project"], "/Users/test/workspace/my-website")

    def test_subprocess_sessions_excluded_from_output(self):
        """Sessions with queue-operation messages should be filtered out of projects
        but their tokens should still be counted in estimated_tokens."""
        human_session = {
            "file_path": os.path.join(FIXTURES, "session_basic.jsonl"),
            "session_id": "human-session",
            "project_dir": "project",
        }
        subprocess_session = {
            "file_path": os.path.join(FIXTURES, "session_subprocess.jsonl"),
            "session_id": "sub-session",
            "project_dir": "project",
        }
        data = assemble_output(date(2026, 3, 25), [human_session, subprocess_session])
        self.assertEqual(data["stats"]["session_count"], 1)
        self.assertEqual(data["stats"]["subprocess_session_count"], 1)
        # Only the human session's messages should be in message_count
        human_msgs = list(extract_messages(os.path.join(FIXTURES, "session_basic.jsonl")))
        self.assertEqual(data["stats"]["message_count"], len(human_msgs))

    def test_is_subprocess_session_detection(self):
        """queue-operation at start → subprocess; regular messages → not subprocess."""
        self.assertTrue(_is_subprocess_session(os.path.join(FIXTURES, "session_subprocess.jsonl")))
        self.assertFalse(_is_subprocess_session(os.path.join(FIXTURES, "session_basic.jsonl")))

    def test_project_key_falls_back_to_project_dir(self):
        """Session with no cwd in messages should fall back to project_dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "no_cwd.jsonl")
            msg = {
                "type": "user",
                "message": {"role": "user", "content": "hello"},
                "isMeta": False,
                "uuid": "u1",
                "timestamp": "2026-03-25T10:00:00.000Z",
            }
            with open(path, "w") as f:
                f.write(json.dumps(msg) + "\n")
            session = {"file_path": path, "session_id": "no-cwd", "project_dir": "fallback-project"}
            data = assemble_output(date(2026, 3, 25), [session])
            self.assertEqual(data["projects"][0]["project"], "fallback-project")


if __name__ == "__main__":
    unittest.main()
