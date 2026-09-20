#!/usr/bin/env python3
"""A bot-directory key must not be counted by the BOT stage.

WHY THIS EXISTS, AND IT WAS A LIVE DEFECT FOR ONE COMMIT.

tools/miniapp_funnel.py has two stages reading the SAME log line,
`acquisition source=<key>` in the Telegram webhook's group:

    BOT        regex (miniapp|tg-miniapp[a-z-]*)   "does the Mini App feed the bot"
    DIRECTORY  regex built from bot_directories.json's keys

Those are different questions on purpose, and that stage's own comment says
widening one to answer the other destroys the answer it already gives.

On 2026-09-20 the tgboard row was registered with the key `tg-miniapp-tgboard`,
shared with its miniapp_routes.json row under a one-key-per-destination
argument. Running the two regexes against one line showed the collision
immediately: a directory arrival matched BOTH, inflating the Mini-App-to-bot
number with traffic that never touched the Mini App.

Every other key in that file is bare (`storebot`, `botsarchive`, `tlgrm`) for
exactly this reason, and nothing was checking that the next one would be.
Two keys for one destination costs adding two numbers together; one key cost
corrupting a metric that already worked.

NOT a style rule about prefixes. The assertion is behavioural: each key is run
through the ACTUAL compiled BOT-stage regex, against the line the handler
actually writes. A prefix check would pass on a key the regex happens to match
for some other reason, and fail on a key that is fine.

    python3 test_bot_directory_keys.py
"""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _funnel():
    spec = importlib.util.spec_from_file_location(
        "miniapp_funnel", ROOT / "tools" / "miniapp_funnel.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _stage(mod, name):
    for stage in mod.STAGES:
        if stage[0].split()[0] == name:
            return stage
    raise AssertionError(f"no {name} stage in miniapp_funnel.STAGES")


class BotDirectoryKeys(unittest.TestCase):
    def setUp(self):
        self.mod = _funnel()
        self.keys = [r["key"] for r in
                     json.loads((ROOT / "bot_directories.json").read_text())["routes"]]

    def test_there_are_keys_to_check(self):
        # An empty set passes every assertion below and proves nothing, which is
        # the shape a scoped guard fails in silently.
        self.assertGreater(len(self.keys), 5, "bot_directories.json looks empty")

    def test_no_bot_directory_key_is_counted_by_the_BOT_stage(self):
        rx = _stage(self.mod, "BOT")[3]
        for key in self.keys:
            line = f"acquisition source={key} uid=deadbeef"
            self.assertIsNone(
                rx.search(line),
                f"bot-directory key {key!r} is ALSO matched by the BOT stage, whose "
                f"question is whether the Mini App feeds the bot. Its arrivals would "
                f"inflate that number with traffic that never touched the Mini App. "
                f"Use a bare key, as every other row in bot_directories.json does.")

    def test_every_bot_directory_key_IS_counted_by_the_DIRECTORY_stage(self):
        # The other direction, because a key nobody counts is a channel that
        # reports a confident zero forever.
        rx = _stage(self.mod, "DIRECTORY")[3]
        for key in self.keys:
            line = f"acquisition source={key} uid=deadbeef"
            got = rx.search(line)
            self.assertIsNotNone(got, f"key {key!r} is in no stage at all")
            self.assertEqual(got.group(1), key)


if __name__ == "__main__":
    unittest.main(verbosity=2)
