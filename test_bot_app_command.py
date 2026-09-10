"""The /app command must exist in BOTH places, because either alone is useless.

A handler branch with no entry in _BOT_COMMANDS_BASE works when typed and is
invisible in Telegram's native "/" menu -- and TGWA-1 records that the menu is
populated ONLY by setMyCommands via commands_for_tier. For a command whose whole
purpose is being FOUND, invisible is the same as absent.

A menu entry with no handler branch is worse: it advertises a command that does
nothing.

Parsed with ast and no boto3, like test_developer_signup_banners.py, because
importing the handler pulls module-level AWS clients.
"""

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BOT = ROOT / "relayshield_telegram_webhook.py"
WORKER = ROOT / "cloudflare_worker_miniapp.js"


def _source() -> str:
    return BOT.read_text(encoding="utf-8")


def _base_commands() -> list:
    """The literal command names in _BOT_COMMANDS_BASE, read from the AST."""
    tree = ast.parse(_source())
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = [getattr(t, "id", None) for t in node.targets]
        elif isinstance(node, ast.AnnAssign):
            targets = [getattr(node.target, "id", None)]
        if "_BOT_COMMANDS_BASE" in targets and isinstance(node.value, ast.List):
            out = []
            for el in node.value.elts:
                if isinstance(el, ast.Tuple) and el.elts:
                    first = el.elts[0]
                    if isinstance(first, ast.Constant):
                        out.append(first.value)
            return out
    raise AssertionError("_BOT_COMMANDS_BASE not found")


class TestAppCommand(unittest.TestCase):
    def test_it_is_in_the_native_menu(self):
        self.assertIn("app", _base_commands(),
                      "not in _BOT_COMMANDS_BASE, so it never appears in the / menu")

    def test_it_has_a_handler_branch(self):
        self.assertRegex(_source(), r'cmd in \("app", "idcheck", "check"\)',
                         "menu entry with no handler advertises a dead command")

    def test_it_sends_a_web_app_button_not_a_url_button(self):
        src = _source()
        i = src.index('cmd in ("app", "idcheck", "check")')
        block = src[i:i + 1600]
        self.assertIn('"web_app"', block,
                      "a url button opens the browser instead of the Mini App")
        self.assertNotIn('"url":', block.split('"web_app"')[0])

    def test_the_button_carries_attribution_the_worker_accepts(self):
        src = _source()
        i = src.index('cmd in ("app", "idcheck", "check")')
        block = src[i:i + 1600]
        m = re.search(r"https://app\.relayshield\.net/\?s=([a-z0-9-]+)", block)
        self.assertIsNotNone(m, "the button URL must carry ?s= -- a web_app "
                                "launch sets no start_param, so without it every "
                                "bot-launched session looks anonymous")
        key = m.group(1)
        worker = WORKER.read_text(encoding="utf-8")
        allowed = worker.split("ALLOWED_SOURCES = new Set([", 1)[1].split("]);", 1)[0]
        self.assertIn(f'"{key}"', allowed,
                      f"{key} is not in the Worker's ALLOWED_SOURCES, so it would "
                      f"be dropped and the launch attributed to nothing")

    def test_the_worker_reads_the_query_fallback(self):
        worker = WORKER.read_text(encoding="utf-8")
        self.assertIn('URLSearchParams(location.search).get("s")', worker,
                      "without this the ?s= on the button URL is never read")


if __name__ == "__main__":
    unittest.main()
