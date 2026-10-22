"""Unit tests for the MCP tool-description drift checker."""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tool_drift import (
    build_pins,
    compare_tools,
    load_snapshot_file,
    main,
    tool_pin,
)

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "fixtures")


def _tool(name, description="", schema=None):
    t = {"name": name}
    if description:
        t["description"] = description
    if schema is not None:
        t["inputSchema"] = schema
    return t


def _schema(props, required=None, **extra):
    s = {"type": "object", "properties": props}
    if required:
        s["required"] = required
    s.update(extra)
    return s


def _load_fixture(name):
    tools, error = load_snapshot_file(os.path.join(FIXTURES, name))
    assert error is None, error
    return tools


BASE_TOOLS = [
    _tool("get_weather", "Returns the current weather for a city.",
          _schema({"city": {"type": "string"}}, required=["city"])),
    _tool("read_file", "Reads a text file and returns its contents.",
          _schema({"path": {"type": "string"}}, required=["path"])),
    _tool("get_report", "Returns the weekly analytics report for a project.",
          _schema({"project": {"type": "string"}}, required=["project"])),
]


def _pins(tools=None):
    return build_pins(tools if tools is not None else BASE_TOOLS)["tools"]


def _find(findings, tool, check):
    return [f for f in findings
            if f["tool"] == tool and f["check"] == check]


class TestPinning(unittest.TestCase):
    def test_pin_is_stable(self):
        tool = BASE_TOOLS[0]
        self.assertEqual(tool_pin(tool), tool_pin(dict(tool)))

    def test_pin_ignores_key_order(self):
        a = _tool("t", "d", {"type": "object",
                             "properties": {"x": {"type": "string"}}})
        b = _tool("t", "d", {"properties": {"x": {"type": "string"}},
                             "type": "object"})
        self.assertEqual(tool_pin(a), tool_pin(b))

    def test_pin_changes_with_description(self):
        a = _tool("t", "first wording")
        b = _tool("t", "second wording")
        self.assertNotEqual(tool_pin(a), tool_pin(b))

    def test_pin_changes_with_schema(self):
        a = _tool("t", "d", _schema({"x": {"type": "string"}}))
        b = _tool("t", "d", _schema({"x": {"type": "integer"}}))
        self.assertNotEqual(tool_pin(a), tool_pin(b))

    def test_build_pins_records_definition(self):
        doc = build_pins(BASE_TOOLS, source="fixture")
        self.assertEqual(doc["version"], 1)
        self.assertEqual(doc["source"], "fixture")
        self.assertIn("get_weather", doc["tools"])
        rec = doc["tools"]["get_weather"]
        self.assertEqual(rec["description"],
                         "Returns the current weather for a city.")
        self.assertEqual(rec["pin"], tool_pin(BASE_TOOLS[0]))


class TestSnapshotLoading(unittest.TestCase):
    def test_loads_jsonrpc_response(self):
        tools = _load_fixture("snapshot_v1.json")
        self.assertEqual(len(tools), 3)
        self.assertEqual(tools[0]["name"], "get_weather")

    def test_loads_bare_list_and_tools_key(self):
        with tempfile.TemporaryDirectory() as td:
            for payload in (BASE_TOOLS, {"tools": BASE_TOOLS}):
                path = os.path.join(td, "snap.json")
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(payload, fh)
                tools, error = load_snapshot_file(path)
                self.assertIsNone(error)
                self.assertEqual(len(tools), 3)

    def test_missing_file_is_error(self):
        tools, error = load_snapshot_file("/nonexistent/snap.json")
        self.assertIsNone(tools)
        self.assertIn("not found", error)


class TestNoDrift(unittest.TestCase):
    def test_identical_snapshot_is_clean(self):
        self.assertEqual(compare_tools(_pins(), BASE_TOOLS), [])

    def test_fixture_against_itself_is_clean(self):
        tools = _load_fixture("snapshot_v1.json")
        pins = build_pins(tools)["tools"]
        self.assertEqual(compare_tools(pins, tools), [])


class TestRugPull(unittest.TestCase):
    def test_rugpull_fixture_flags_description_change_high(self):
        pins = build_pins(_load_fixture("snapshot_v1.json"))["tools"]
        current = _load_fixture("snapshot_v2_rugpull.json")
        findings = compare_tools(pins, current)
        hits = _find(findings, "get_report", "description_changed")
        self.assertEqual(len(hits), 1)
        # The mutated text adds an exfiltration instruction with an
        # external URL, so the change escalates past the MEDIUM floor.
        self.assertEqual(hits[0]["severity"], "HIGH")
        self.assertIn("collector.example.net", hits[0]["detail"])

    def test_other_tools_untouched_by_rugpull_fixture(self):
        pins = build_pins(_load_fixture("snapshot_v1.json"))["tools"]
        current = _load_fixture("snapshot_v2_rugpull.json")
        findings = compare_tools(pins, current)
        self.assertTrue(all(f["tool"] == "get_report" for f in findings))


class TestDescriptionChange(unittest.TestCase):
    def test_plain_wording_change_is_medium(self):
        current = [dict(t) for t in BASE_TOOLS]
        current[0] = _tool(
            "get_weather", "Returns the weather right now for any city.",
            _schema({"city": {"type": "string"}}, required=["city"]))
        findings = compare_tools(_pins(), current)
        hits = _find(findings, "get_weather", "description_changed")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["severity"], "MEDIUM")

    def test_new_url_alone_escalates_to_high(self):
        current = [dict(t) for t in BASE_TOOLS]
        current[0] = _tool(
            "get_weather",
            "Returns the current weather for a city. Docs: "
            "https://weather.example.org/api",
            _schema({"city": {"type": "string"}}, required=["city"]))
        findings = compare_tools(_pins(), current)
        hits = _find(findings, "get_weather", "description_changed")
        self.assertEqual(hits[0]["severity"], "HIGH")


class TestSchemaChange(unittest.TestCase):
    def _drifted(self, tool):
        current = [t for t in BASE_TOOLS if t["name"] != tool["name"]]
        current.append(tool)
        return compare_tools(_pins(), current)

    def test_new_parameter_is_high(self):
        tool = _tool("read_file", "Reads a text file and returns its contents.",
                     _schema({"path": {"type": "string"},
                              "webhook_url": {"type": "string"}},
                             required=["path"]))
        hits = _find(self._drifted(tool), "read_file", "schema_changed")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["severity"], "HIGH")
        self.assertIn("webhook_url", hits[0]["detail"])

    def test_widened_type_is_high(self):
        tool = _tool("get_weather", "Returns the current weather for a city.",
                     _schema({"city": {"type": ["string", "null"]}},
                             required=["city"]))
        hits = _find(self._drifted(tool), "get_weather", "schema_changed")
        self.assertEqual(hits[0]["severity"], "HIGH")
        self.assertIn("widened", hits[0]["detail"])

    def test_type_unconstrained_is_high(self):
        tool = _tool("get_weather", "Returns the current weather for a city.",
                     _schema({"city": {}}, required=["city"]))
        hits = _find(self._drifted(tool), "get_weather", "schema_changed")
        self.assertEqual(hits[0]["severity"], "HIGH")

    def test_dropped_required_is_high(self):
        tool = _tool("get_weather", "Returns the current weather for a city.",
                     _schema({"city": {"type": "string"}}))
        hits = _find(self._drifted(tool), "get_weather", "schema_changed")
        self.assertEqual(hits[0]["severity"], "HIGH")
        self.assertIn("no longer required", hits[0]["detail"])

    def test_removed_parameter_is_medium(self):
        # Remove an optional parameter (the required one stays), so the
        # only change is the removal itself.
        pinned = build_pins([_tool(
            "read_file", "Reads a text file and returns its contents.",
            _schema({"path": {"type": "string"},
                     "encoding": {"type": "string"}},
                    required=["path"]))])["tools"]
        current = [_tool(
            "read_file", "Reads a text file and returns its contents.",
            _schema({"path": {"type": "string"}}, required=["path"]))]
        hits = _find(compare_tools(pinned, current),
                     "read_file", "schema_changed")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["severity"], "MEDIUM")
        self.assertIn("encoding", hits[0]["detail"])

    def test_narrowed_type_is_medium(self):
        pinned = build_pins([_tool(
            "t", "d", _schema({"x": {"type": ["string", "integer"]}}))])["tools"]
        current = [_tool("t", "d", _schema({"x": {"type": "string"}}))]
        hits = _find(compare_tools(pinned, current), "t", "schema_changed")
        self.assertEqual(hits[0]["severity"], "MEDIUM")


class TestAddedRemoved(unittest.TestCase):
    def test_added_tool_is_medium(self):
        current = BASE_TOOLS + [_tool("run_shell", "Runs a shell command.",
                                      _schema({"cmd": {"type": "string"}}))]
        hits = _find(compare_tools(_pins(), current),
                     "run_shell", "tool_added")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["severity"], "MEDIUM")

    def test_removed_tool_is_low(self):
        current = [t for t in BASE_TOOLS if t["name"] != "read_file"]
        hits = _find(compare_tools(_pins(), current),
                     "read_file", "tool_removed")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["severity"], "LOW")


class TestCLI(unittest.TestCase):
    def _run(self, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(argv)
        return code, buf.getvalue()

    def test_pin_then_check_clean(self):
        with tempfile.TemporaryDirectory() as td:
            pins = os.path.join(td, "pins.json")
            snap = os.path.join(FIXTURES, "snapshot_v1.json")
            code, _ = self._run(["pin", "--pins", pins, "--file", snap])
            self.assertEqual(code, 0)
            self.assertTrue(os.path.isfile(pins))
            code, out = self._run(["check", "--pins", pins, "--file", snap])
            self.assertEqual(code, 0)
            self.assertIn("No drift", out)

    def test_check_rugpull_exits_1(self):
        with tempfile.TemporaryDirectory() as td:
            pins = os.path.join(td, "pins.json")
            v1 = os.path.join(FIXTURES, "snapshot_v1.json")
            v2 = os.path.join(FIXTURES, "snapshot_v2_rugpull.json")
            self.assertEqual(
                self._run(["pin", "--pins", pins, "--file", v1])[0], 0)
            code, out = self._run(
                ["check", "--pins", pins, "--file", v2, "--ci"])
            self.assertEqual(code, 1)
            self.assertIn("description_changed", out)
            self.assertIn("HIGH=1", out)

    def test_check_json_format(self):
        with tempfile.TemporaryDirectory() as td:
            pins = os.path.join(td, "pins.json")
            v1 = os.path.join(FIXTURES, "snapshot_v1.json")
            v2 = os.path.join(FIXTURES, "snapshot_v2_rugpull.json")
            self._run(["pin", "--pins", pins, "--file", v1])
            code, out = self._run(["check", "--pins", pins, "--file", v2,
                                   "--format", "json"])
            self.assertEqual(code, 1)
            doc = json.loads(out)
            self.assertEqual(len(doc["findings"]), 1)
            self.assertEqual(doc["findings"][0]["check"],
                             "description_changed")

    def test_check_missing_pins_exits_2(self):
        snap = os.path.join(FIXTURES, "snapshot_v1.json")
        code, _ = self._run(["check", "--pins", "/nonexistent/pins.json",
                             "--file", snap])
        self.assertEqual(code, 2)

    def test_check_missing_snapshot_exits_2(self):
        with tempfile.TemporaryDirectory() as td:
            pins = os.path.join(td, "pins.json")
            snap = os.path.join(FIXTURES, "snapshot_v1.json")
            self._run(["pin", "--pins", pins, "--file", snap])
            code, _ = self._run(["check", "--pins", pins,
                                 "--file", "/nonexistent/snap.json"])
            self.assertEqual(code, 2)

    def test_check_medium_only_exits_0(self):
        with tempfile.TemporaryDirectory() as td:
            pins = os.path.join(td, "pins.json")
            snap = os.path.join(td, "snap.json")
            drifted = [dict(t) for t in BASE_TOOLS]
            drifted[0] = _tool(
                "get_weather", "Returns the weather right now for any city.",
                _schema({"city": {"type": "string"}}, required=["city"]))
            with open(snap, "w", encoding="utf-8") as fh:
                json.dump(drifted, fh)
            v1 = os.path.join(FIXTURES, "snapshot_v1.json")
            self._run(["pin", "--pins", pins, "--file", v1])
            code, _ = self._run(["check", "--pins", pins, "--file", snap,
                                 "--ci"])
            self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
