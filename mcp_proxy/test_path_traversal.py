"""Unit tests for path traversal detection.

Run: python3 -m unittest mcp_proxy.test_path_traversal -v
"""

import os
import tempfile
import unittest

from mcp_proxy.path_traversal import (
    POISON_PATH_TRAVERSAL,
    _has_traversal,
    _is_absolute_path,
    _is_sensitive_path,
    is_path_param,
    screen_path_param,
    screen_tool_paths,
)


class TestHasTraversal(unittest.TestCase):
    def test_dotdot_slash(self):
        self.assertTrue(_has_traversal("../../etc/passwd"))

    def test_dotdot_backslash(self):
        self.assertTrue(_has_traversal("..\\..\\windows\\system32"))

    def test_encoded(self):
        self.assertTrue(_has_traversal("%2e%2e%2fetc%2fpasswd"))

    def test_double_encoded(self):
        self.assertTrue(_has_traversal("%252e%252e%252fetc"))

    def test_null_byte(self):
        self.assertTrue(_has_traversal("safe.txt%00../../etc"))

    def test_clean_relative(self):
        self.assertFalse(_has_traversal("src/components/Button.js"))

    def test_clean_dotfile(self):
        self.assertFalse(_has_traversal("./data/output.json"))

    def test_single_dot(self):
        # Single dot is fine, only double-dot traverses.
        self.assertFalse(_has_traversal("./config.yaml"))


class TestIsAbsolutePath(unittest.TestCase):
    def test_unix_absolute(self):
        self.assertTrue(_is_absolute_path("/etc/passwd"))

    def test_windows_drive(self):
        self.assertTrue(_is_absolute_path("C:\\Windows\\System32"))

    def test_windows_unc(self):
        self.assertTrue(_is_absolute_path("\\\\server\\share"))

    def test_relative(self):
        self.assertFalse(_is_absolute_path("src/index.js"))

    def test_dot_relative(self):
        self.assertFalse(_is_absolute_path("./data.json"))


class TestIsSensitivePath(unittest.TestCase):
    def test_ssh_dir(self):
        self.assertTrue(_is_sensitive_path("/home/user/.ssh/id_rsa"))

    def test_pem_extension(self):
        self.assertTrue(_is_sensitive_path("certs/server.pem"))

    def test_env_file(self):
        self.assertTrue(_is_sensitive_path(".env"))

    def test_id_rsa(self):
        self.assertTrue(_is_sensitive_path("/tmp/id_rsa"))

    def test_clean(self):
        self.assertEqual(_is_sensitive_path("src/app.js"), [])


class TestIsPathParam(unittest.TestCase):
    def test_known_name(self):
        self.assertTrue(is_path_param("repo_path", "../../etc"))

    def test_case_insensitive(self):
        self.assertTrue(is_path_param("File_Path", "/tmp/x"))

    def test_path_like_value(self):
        self.assertTrue(is_path_param("target", "a/b/c"))

    def test_url_not_path(self):
        self.assertFalse(is_path_param("url", "https://example.com/x"))

    def test_non_string(self):
        self.assertFalse(is_path_param("path", 123))

    def test_plain_string(self):
        self.assertFalse(is_path_param("message", "hello world"))


class TestScreenPathParam(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_traversal_blocked(self):
        r = screen_path_param("repo_path", "../../etc/passwd",
                              workspace_root=self.tmp)
        self.assertEqual(r.verdict, "block")
        self.assertTrue(any("traversal" in x for x in r.reasons))

    def test_absolute_escape_blocked(self):
        r = screen_path_param("path", "/etc/passwd",
                              workspace_root=self.tmp)
        self.assertEqual(r.verdict, "block")

    def test_absolute_within_root_allowed(self):
        # Absolute path inside workspace root is fine when allow_absolute.
        target = os.path.join(self.tmp, "sub", "file.txt")
        r = screen_path_param("path", target, workspace_root=self.tmp,
                              allow_absolute=True)
        self.assertEqual(r.verdict, "allow")

    def test_relative_within_root_allowed(self):
        r = screen_path_param("directory", "src/components",
                              workspace_root=self.tmp)
        self.assertEqual(r.verdict, "allow")

    def test_sensitive_flagged(self):
        r = screen_path_param("path", ".ssh/id_rsa",
                              workspace_root=self.tmp)
        # Traversal-free but sensitive -> flag.
        self.assertEqual(r.verdict, "flag")
        self.assertTrue(any("sensitive" in x for x in r.reasons))

    def test_sensitive_block_mode(self):
        r = screen_path_param("path", "server.pem",
                              workspace_root=self.tmp,
                              sensitive_mode="block")
        self.assertEqual(r.verdict, "block")

    def test_traversal_overrides_sensitive(self):
        # Block wins over flag.
        r = screen_path_param("path", "../../.ssh/id_rsa",
                              workspace_root=self.tmp)
        self.assertEqual(r.verdict, "block")

    def test_disabled_modes(self):
        r = screen_path_param("repo_path", "../../etc",
                              workspace_root=self.tmp,
                              traversal_mode="disabled",
                              sensitive_mode="disabled")
        self.assertEqual(r.verdict, "allow")

    def test_symlink_escape(self):
        # Symlink inside root pointing outside -> blocked after canonicalization.
        outside = tempfile.mkdtemp()
        link = os.path.join(self.tmp, "evil")
        try:
            os.symlink(outside, link)
        except OSError:
            self.skipTest("symlinks not supported")
        r = screen_path_param("path", "evil/passwd",
                              workspace_root=self.tmp)
        self.assertEqual(r.verdict, "block")

    def test_windows_traversal(self):
        r = screen_path_param("path", "..\\..\\Windows\\System32",
                              workspace_root=self.tmp)
        self.assertEqual(r.verdict, "block")


class TestScreenToolPaths(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_clean_args(self):
        results = screen_tool_paths(
            {"repo_path": "myrepo", "branch": "main"},
            workspace_root=self.tmp)
        self.assertEqual(results, [])

    def test_finds_traversal(self):
        results = screen_tool_paths(
            {"repo_path": "../../etc", "branch": "main"},
            workspace_root=self.tmp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].verdict, "block")
        self.assertEqual(results[0].param, "repo_path")

    def test_multiple_params(self):
        results = screen_tool_paths(
            {"source": "../../a", "dest": "/etc/b"},
            workspace_root=self.tmp)
        self.assertEqual(len(results), 2)

    def test_non_dict(self):
        self.assertEqual(screen_tool_paths(None, workspace_root=self.tmp), [])
        self.assertEqual(screen_tool_paths("x", workspace_root=self.tmp), [])


if __name__ == "__main__":
    unittest.main()
