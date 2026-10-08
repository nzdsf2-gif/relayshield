"""Unit tests for the MCP config scanner."""

import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scanner import scan_config, load_config, main, _version_tuple


def _cfg(servers):
    return {"mcpServers": servers}


class TestCleanConfig(unittest.TestCase):
    def test_clean_config(self):
        config = _cfg({
            "weather": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-weather"],
            }
        })
        self.assertEqual(scan_config(config), [])


class TestHardcodedSecrets(unittest.TestCase):
    def test_openai_key_value(self):
        config = _cfg({
            "agent": {
                "command": "node",
                "args": ["server.js"],
                "env": {"OPENAI_API_KEY": "sk-abcdefghijklmnopqrstuvwx123456"},
            }
        })
        findings = scan_config(config)
        self.assertTrue(any(
            f["check"] == "hardcoded_secret" and f["severity"] == "CRITICAL"
            for f in findings))

    def test_secret_env_name(self):
        config = _cfg({
            "agent": {
                "command": "node",
                "args": ["server.js"],
                "env": {"MY_SECRET_TOKEN": "hunter2value"},
            }
        })
        findings = scan_config(config)
        self.assertTrue(any(
            f["check"] == "hardcoded_secret" and f["severity"] == "HIGH"
            for f in findings))

    def test_secret_in_arg(self):
        config = _cfg({
            "agent": {
                "command": "node",
                "args": ["server.js", "--token=ghp_abcdefghijklmnopqrstuv"],
            }
        })
        findings = scan_config(config)
        self.assertTrue(any(f["check"] == "hardcoded_secret" for f in findings))


class TestFilesystem(unittest.TestCase):
    def test_root_mount(self):
        config = _cfg({
            "fs": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/"],
            }
        })
        findings = scan_config(config)
        self.assertTrue(any(
            f["check"] == "overprivileged_filesystem" for f in findings))

    def test_home_mount(self):
        config = _cfg({
            "fs": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "~"],
            }
        })
        findings = scan_config(config)
        self.assertTrue(any(
            f["check"] == "overprivileged_filesystem" for f in findings))

    def test_scoped_ok(self):
        config = _cfg({
            "fs": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem",
                         "/Users/alice/projects"],
            }
        })
        findings = scan_config(config)
        self.assertFalse(any(
            f["check"] == "overprivileged_filesystem" for f in findings))


class TestAdvisories(unittest.TestCase):
    def test_vulnerable_git_server(self):
        config = _cfg({
            "git": {
                "command": "npx",
                "args": ["-y", "mcp-server-git@1.2.3"],
            }
        })
        findings = scan_config(config)
        self.assertTrue(any(
            f["check"] == "known_vulnerable_server" for f in findings))

    def test_fixed_git_server(self):
        config = _cfg({
            "git": {
                "command": "npx",
                "args": ["-y", "mcp-server-git@2026.1.15"],
            }
        })
        findings = scan_config(config)
        self.assertFalse(any(
            f["check"] == "known_vulnerable_server" for f in findings))

    def test_version_tuple(self):
        self.assertGreaterEqual(_version_tuple("2026.1.15"), (2025, 12, 8))
        self.assertLess(_version_tuple("1.2.3"), (2025, 12, 8))


class TestRemoteAuth(unittest.TestCase):
    def test_unauthenticated_remote(self):
        config = _cfg({
            "remote": {"url": "https://mcp.example.com/mcp"},
        })
        findings = scan_config(config)
        self.assertTrue(any(
            f["check"] == "unauthenticated_remote" for f in findings))

    def test_authenticated_remote_ok(self):
        config = _cfg({
            "remote": {
                "url": "https://mcp.example.com/mcp",
                "headers": {"Authorization": "Bearer ${TOKEN}"},
            },
        })
        findings = scan_config(config)
        self.assertFalse(any(
            f["check"] == "unauthenticated_remote" for f in findings))


class TestDangerousTools(unittest.TestCase):
    def test_shell_server(self):
        config = _cfg({
            "shell": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-shell"],
            }
        })
        findings = scan_config(config)
        self.assertTrue(any(f["check"] == "dangerous_tools" for f in findings))


class TestMain(unittest.TestCase):
    def _write_config(self, config):
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False)
        json.dump(config, tmp)
        tmp.close()
        self.addCleanup(os.unlink, tmp.name)
        return tmp.name

    def test_json_format(self):
        path = self._write_config(_cfg({
            "agent": {"command": "node", "args": [],
                      "env": {"API_KEY": "sk-abcdefghijklmnopqrstuvwx123456"}},
        }))
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            code = main([path, "--format", "json"])
        finally:
            sys.stdout = old
        self.assertEqual(code, 1)
        data = json.loads(buf.getvalue())
        self.assertTrue(data["findings"])

    def test_missing_file(self):
        self.assertEqual(main(["/nonexistent/config.json"]), 2)

    def test_clean_exit_zero(self):
        path = self._write_config(_cfg({
            "weather": {"command": "npx", "args": ["server-weather"]},
        }))
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            code = main([path, "--no-color"])
        finally:
            sys.stdout = old
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
