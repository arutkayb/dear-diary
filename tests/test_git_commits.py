"""Unit tests for git commit collection functions in extract.py"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch

from extract import (
    load_config,
    _collect_cwds,
    _git_repo_root,
    _git_root_cache,
    _is_temp_path,
    discover_repo_paths,
    collect_git_commits,
    _group_commits_by_repo,
)

LOCAL_TZ = datetime.now().astimezone().tzinfo


def _make_git_repo(path: str, commits: list[dict]) -> None:
    """Init a bare git repo at path and create the given commits.

    Each commit dict: {message, date_str} where date_str is ISO 8601.
    """
    env = os.environ.copy()
    env.update({
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@test.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@test.com",
    })
    subprocess.run(["git", "init", path], check=True, capture_output=True)
    subprocess.run(["git", "-C", path, "config", "user.email", "test@test.com"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", path, "config", "user.name", "Test"],
                   check=True, capture_output=True)
    for i, commit in enumerate(commits):
        # Write a dummy file so git has something to commit
        dummy = os.path.join(path, f"file{i}.txt")
        with open(dummy, "w") as f:
            f.write(commit["message"])
        subprocess.run(["git", "-C", path, "add", "."], check=True, capture_output=True)
        date_env = env.copy()
        date_env["GIT_AUTHOR_DATE"] = commit["date_str"]
        date_env["GIT_COMMITTER_DATE"] = commit["date_str"]
        subprocess.run(
            ["git", "-C", path, "commit", "-m", commit["message"]],
            check=True, capture_output=True, env=date_env,
        )


class TestLoadConfig(unittest.TestCase):
    def test_missing_file_returns_defaults(self):
        cfg = load_config("/nonexistent/path/config.json")
        self.assertFalse(cfg["git_commits"]["enabled"])
        self.assertEqual(cfg["git_commits"]["additional_repos"], [])

    def test_valid_config_loaded(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"git_commits": {"enabled": True, "additional_repos": ["/tmp/repo"]}}, f)
            path = f.name
        try:
            cfg = load_config(path)
            self.assertTrue(cfg["git_commits"]["enabled"])
            self.assertEqual(cfg["git_commits"]["additional_repos"], ["/tmp/repo"])
        finally:
            os.unlink(path)

    def test_malformed_json_returns_defaults(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{not valid json")
            path = f.name
        try:
            cfg = load_config(path)
            self.assertFalse(cfg["git_commits"]["enabled"])
        finally:
            os.unlink(path)

    def test_none_path_falls_back_to_script_dir(self):
        # With no config.json in the project root (or if it exists), shouldn't crash
        cfg = load_config(None)
        self.assertIn("git_commits", cfg)


class TestCollectCwds(unittest.TestCase):
    def _make_session_file(self, tmpdir: str, cwd: str) -> dict:
        path = os.path.join(tmpdir, "session.jsonl")
        with open(path, "w") as f:
            line = json.dumps({
                "timestamp": "2026-03-26T10:00:00+00:00",
                "cwd": cwd,
                "message": {"role": "user", "content": "hello"},
            })
            f.write(line + "\n")
        return {"file_path": path, "session_id": "abc", "project_dir": tmpdir}

    def test_extracts_cwd_from_session(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_cwd = os.path.join(tmpdir, "myrepo")
            os.makedirs(fake_cwd)
            session = self._make_session_file(tmpdir, fake_cwd)
            cwds = _collect_cwds([session])
            self.assertIn(fake_cwd, cwds)

    def test_deduplicates_cwds(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            s1 = self._make_session_file(tmpdir, "/same/path")
            path2 = os.path.join(tmpdir, "session2.jsonl")
            with open(path2, "w") as f:
                f.write(json.dumps({"cwd": "/same/path", "message": {"role": "user", "content": "hi"}}) + "\n")
            s2 = {"file_path": path2, "session_id": "def", "project_dir": tmpdir}
            cwds = _collect_cwds([s1, s2])
            self.assertEqual(len([c for c in cwds if c == "/same/path"]), 1)

    def test_no_cwd_field_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "session.jsonl")
            with open(path, "w") as f:
                f.write(json.dumps({"message": {"role": "user", "content": "no cwd"}}) + "\n")
            session = {"file_path": path, "session_id": "xyz", "project_dir": tmpdir}
            cwds = _collect_cwds([session])
            self.assertEqual(cwds, set())


class TestDiscoverRepoPaths(unittest.TestCase):
    def setUp(self):
        _git_root_cache.clear()

    @patch("extract._is_temp_path", return_value=False)
    def test_includes_additional_repos(self, _mock):
        with tempfile.TemporaryDirectory() as tmpdir:
            real_tmpdir = os.path.realpath(tmpdir)
            _make_git_repo(tmpdir, [{"message": "init", "date_str": "2026-03-26T10:00:00+00:00"}])
            repos = discover_repo_paths([], [tmpdir])
            self.assertIn(real_tmpdir, repos)

    def test_skips_nonexistent_additional_repo(self):
        repos = discover_repo_paths([], ["/nonexistent/path/xyz"])
        self.assertEqual(repos, [])

    def test_skips_non_git_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repos = discover_repo_paths([], [tmpdir])
            self.assertEqual(repos, [])

    @patch("extract._is_temp_path", return_value=False)
    def test_deduplicates_repos_from_sessions_and_config(self, _mock):
        with tempfile.TemporaryDirectory() as tmpdir:
            real_tmpdir = os.path.realpath(tmpdir)
            _make_git_repo(tmpdir, [{"message": "init", "date_str": "2026-03-26T10:00:00+00:00"}])
            # Both session cwd and additional_repos point to same repo
            session_file = os.path.join(tmpdir, "s.jsonl")
            with open(session_file, "w") as f:
                f.write(json.dumps({"cwd": tmpdir, "message": {"role": "user", "content": "x"}}) + "\n")
            session = {"file_path": session_file, "session_id": "s1", "project_dir": tmpdir}
            repos = discover_repo_paths([session], [tmpdir])
            self.assertEqual(repos.count(real_tmpdir), 1)


class TestCollectGitCommits(unittest.TestCase):
    def setUp(self):
        _git_root_cache.clear()

    def test_collects_commits_for_date(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_git_repo(tmpdir, [
                {"message": "feat: add feature", "date_str": "2026-03-26T10:00:00+00:00"},
            ])
            commits = collect_git_commits([tmpdir], date(2026, 3, 26), timezone.utc)
            self.assertEqual(len(commits), 1)
            self.assertEqual(commits[0]["message"], "feat: add feature")
            self.assertEqual(commits[0]["repo"], tmpdir)

    def test_excludes_commits_from_other_date(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_git_repo(tmpdir, [
                {"message": "old commit", "date_str": "2026-03-24T10:00:00+00:00"},
            ])
            commits = collect_git_commits([tmpdir], date(2026, 3, 26), timezone.utc)
            self.assertEqual(len(commits), 0)

    def test_handles_non_git_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            commits = collect_git_commits([tmpdir], date(2026, 3, 26), timezone.utc)
            self.assertEqual(commits, [])

    def test_handles_nonexistent_path(self):
        commits = collect_git_commits(["/nonexistent/path"], date(2026, 3, 26), timezone.utc)
        self.assertEqual(commits, [])

    def test_deduplicates_by_hash_across_repos(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_git_repo(tmpdir, [
                {"message": "shared commit", "date_str": "2026-03-26T10:00:00+00:00"},
            ])
            # Same repo passed twice — commit should appear once
            commits = collect_git_commits([tmpdir, tmpdir], date(2026, 3, 26), timezone.utc)
            hashes = [c["hash"] for c in commits]
            self.assertEqual(len(hashes), len(set(hashes)))

    def test_multiple_commits_same_day(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_git_repo(tmpdir, [
                {"message": "first", "date_str": "2026-03-26T09:00:00+00:00"},
                {"message": "second", "date_str": "2026-03-26T11:00:00+00:00"},
            ])
            commits = collect_git_commits([tmpdir], date(2026, 3, 26), timezone.utc)
            self.assertEqual(len(commits), 2)
            messages = {c["message"] for c in commits}
            self.assertEqual(messages, {"first", "second"})

    def test_commit_has_required_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_git_repo(tmpdir, [
                {"message": "test fields", "date_str": "2026-03-26T10:00:00+00:00"},
            ])
            commits = collect_git_commits([tmpdir], date(2026, 3, 26), timezone.utc)
            self.assertEqual(len(commits), 1)
            c = commits[0]
            self.assertIn("repo", c)
            self.assertIn("hash", c)
            self.assertIn("timestamp", c)
            self.assertIn("branch", c)
            self.assertIn("message", c)


class TestGroupCommitsByRepo(unittest.TestCase):
    def test_groups_by_repo(self):
        commits = [
            {"repo": "/a", "hash": "h1", "timestamp": "t1", "branch": "main", "message": "m1"},
            {"repo": "/b", "hash": "h2", "timestamp": "t2", "branch": "", "message": "m2"},
            {"repo": "/a", "hash": "h3", "timestamp": "t3", "branch": "main", "message": "m3"},
        ]
        grouped = _group_commits_by_repo(commits)
        self.assertEqual(len(grouped), 2)
        repo_a = next(g for g in grouped if g["repo"] == "/a")
        self.assertEqual(repo_a["commit_count"], 2)
        self.assertEqual(len(repo_a["commits"]), 2)

    def test_empty_input(self):
        self.assertEqual(_group_commits_by_repo([]), [])

    def test_grouped_commits_lack_repo_field(self):
        commits = [
            {"repo": "/a", "hash": "h1", "timestamp": "t1", "branch": "main", "message": "m1"},
        ]
        grouped = _group_commits_by_repo(commits)
        self.assertNotIn("repo", grouped[0]["commits"][0])


if __name__ == "__main__":
    unittest.main()
