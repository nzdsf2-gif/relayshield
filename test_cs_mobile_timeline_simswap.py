#!/usr/bin/env python3
"""Crypto Shield Mobile v1.6.0: attack-chain screen, SIM swap enrolment, error path.

Three changes that only work if THREE places agree, and none of the three
places can see the others fail:

  * the app calls an endpoint,
  * the API's billing branch lets that key call it,
  * the monitor can actually reach the user afterwards.

Each got a test that goes through the real code rather than reading a
sentence about it, because every one of these defects is quiet.

THE BILLING ONE IS THE EASY ONE TO SHIP BROKEN. /v1/metered/incident-timeline
is a priced endpoint. A Crypto Shield key is scoped to an explicit allowlist
(CS_MOBILE_ALLOWED_ENDPOINTS), so an endpoint missing from it falls through to
the Stripe meter branch and the screen 402s for the one audience it is built
for, while the endpoint's own tests stay green.

THE DELIVERY ONE IS WORSE. A number enrolled from the app has no WhatsApp
session and no Telegram chat. With no delivery_channels the monitor treats it
as a legacy WhatsApp record, so the user would be watched, messaged on a
channel they never opted in to, and never told on the one surface they have.
"""

import ast
import re
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
APP = ROOT / "crypto-shield-app"
SRC = APP / "src"


def _stub_boto3():
    b = types.ModuleType("boto3"); b.__path__ = []
    b.client = lambda *a, **k: mock.MagicMock()
    b.resource = lambda *a, **k: mock.MagicMock()
    cond = types.ModuleType("boto3.dynamodb.conditions")
    cond.Key = lambda *a, **k: mock.MagicMock()
    cond.Attr = lambda *a, **k: mock.MagicMock()
    ddb = types.ModuleType("boto3.dynamodb"); ddb.__path__ = []; ddb.conditions = cond
    b.dynamodb = ddb
    bc = types.ModuleType("botocore"); bc.__path__ = []
    ex = types.ModuleType("botocore.exceptions")
    class _CE(Exception): pass
    ex.ClientError = _CE; ex.BotoCoreError = _CE; bc.exceptions = ex
    for name, mod in (("boto3", b), ("boto3.dynamodb", ddb), ("boto3.dynamodb.conditions", cond),
                      ("botocore", bc), ("botocore.exceptions", ex)):
        sys.modules.setdefault(name, mod)


_stub_boto3()
sys.path.insert(0, str(ROOT))
import relayshield_api as api  # noqa: E402
import relayshield_sim_swap_consent as consent  # noqa: E402


def strip_ts_comments(text: str) -> str:
    text = re.sub(r"\{\s*/\*.*?\*/\s*\}", " ", text, flags=re.S)
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"^\s*//.*$", "", text, flags=re.M)


def app_source(rel: str) -> str:
    return strip_ts_comments((SRC / rel).read_text())


# ---------------------------------------------------------------------------
# 1. Billing: the key the app holds is allowed to make the call
# ---------------------------------------------------------------------------

class TestTheAppKeyMayCallTheTimeline(unittest.TestCase):

    def test_incident_timeline_is_in_the_cs_mobile_allowlist(self):
        self.assertIn("/v1/metered/incident-timeline", api.CS_MOBILE_ALLOWED_ENDPOINTS)

    def test_the_allowlist_still_excludes_the_enterprise_endpoint(self):
        """bulk-identity-risk is a $2.00 enterprise call and must never become
        free because somebody pays for the mobile app."""
        self.assertNotIn("/v1/metered/bulk-identity-risk", api.CS_MOBILE_ALLOWED_ENDPOINTS)

    def test_the_app_only_calls_allowlisted_metered_paths(self):
        """Every /v1/metered/* path the app can post is covered, so no screen
        402s. Read from the client, not retyped here."""
        paths = set(re.findall(r'"(/v1/metered/[a-z0-9-]+)"', app_source("api/relayshield.ts")))
        missing = sorted(p for p in paths
                         if p not in api.CS_MOBILE_ALLOWED_ENDPOINTS
                         # dead code in the app, called from no screen, and
                         # deliberately never allowlisted
                         and p != "/v1/metered/bulk-identity-risk")
        self.assertEqual(missing, [], f"app posts paths a CS Mobile key cannot call: {missing}")

    def test_the_billing_branch_is_still_derived_from_the_allowlist(self):
        src = (ROOT / "relayshield_api.py").read_text()
        self.assertRegex(src, r"is_cs_mobile_call\s*=\s*bool\(key_record\.get\(\"cs_mobile_access\"\)\)\s*and\s*path in CS_MOBILE_ALLOWED_ENDPOINTS")


# ---------------------------------------------------------------------------
# 2. Enrolment: the delivery channel, EXECUTED
# ---------------------------------------------------------------------------

class TestEnrolmentCarriesADeliveryChannel(unittest.TestCase):

    def enroll(self, existing, **kw):
        written = {}
        table = mock.MagicMock()
        def _update(**k):
            names, vals = k["ExpressionAttributeNames"], k["ExpressionAttributeValues"]
            written.update({attr: vals[":" + attr] for attr in (n[1:] for n in names)})
        table.update_item.side_effect = _update
        table.put_item.side_effect = lambda Item: written.update(Item)
        db = mock.MagicMock(); db.Table.return_value = table
        kms = mock.MagicMock(); kms.encrypt.return_value = {"CiphertextBlob": b"x"}
        with mock.patch.object(consent, "_dynamodb", db), mock.patch.object(consent, "_kms", kms), \
             mock.patch.object(consent, "find_user_by_phone_hash", return_value=existing):
            consent.enroll("+15551230000", enrollment_type="self", consent_source="cs_mobile",
                           consent_acknowledged=True, enrolled_by="rs_key", **kw)
        return written

    def test_a_new_app_number_gets_push_and_nothing_else(self):
        w = self.enroll(None, add_delivery_channel="push")
        self.assertEqual(w["delivery_channels"], ["push"])
        self.assertIs(w["sim_swap_monitoring"], True)

    def test_an_existing_telegram_record_keeps_telegram(self):
        """Overwriting the list with ["push"] would silently turn their alerts off."""
        w = self.enroll({"user_id": "u", "delivery_channels": ["telegram"]}, add_delivery_channel="push")
        self.assertEqual(w["delivery_channels"], ["telegram", "push"])

    def test_a_legacy_whatsapp_record_keeps_whatsapp_explicitly(self):
        """An EXISTING record with no list is a legacy WhatsApp record, and the
        moment the list gains a member that default would otherwise vanish."""
        w = self.enroll({"user_id": "u"}, add_delivery_channel="push")
        self.assertEqual(w["delivery_channels"], ["whatsapp", "push"])

    def test_re_enrolling_does_not_duplicate_the_channel(self):
        w = self.enroll({"user_id": "u", "delivery_channels": ["push"]}, add_delivery_channel="push")
        self.assertEqual(w["delivery_channels"], ["push"])

    def test_no_channel_argument_leaves_the_list_untouched(self):
        """Telegram, WhatsApp and Stripe enrol through this function too."""
        w = self.enroll({"user_id": "u", "delivery_channels": ["telegram"]})
        self.assertNotIn("delivery_channels", w)


class TestTheHttpHandlerPassesTheChannel(unittest.TestCase):

    def call(self, source):
        seen = {}
        with mock.patch.object(api.simswap_consent, "enroll",
                               side_effect=lambda phone, **k: (seen.update(k), {"consent_state": "CONFIRMED", "monitoring": True})[1]):
            api.handle_sim_swap_enroll(
                {"phone": "+15551230000", "enrollment_type": "self", "consent_source": source,
                 "consent_acknowledged": True}, api_key_record={"api_key": "rs_key"})
        return seen

    def test_cs_mobile_enrolments_get_the_push_channel(self):
        self.assertEqual(self.call("cs_mobile")["add_delivery_channel"], "push")

    def test_other_surfaces_do_not(self):
        for src in ("telegram", "whatsapp", "api", "web"):
            self.assertIsNone(self.call(src)["add_delivery_channel"], src)


# ---------------------------------------------------------------------------
# 3. The app: what it posts, what it shows
# ---------------------------------------------------------------------------

class TestTheAppEnrolsForReal(unittest.TestCase):

    def test_enrol_posts_the_enrolment_endpoint_with_the_consent_fields(self):
        body = app_source("api/relayshield.ts")
        m = re.search(r"export async function enrollSimSwap.*?\n}\n", body, flags=re.S)
        self.assertTrue(m, "enrollSimSwap is missing")
        fn = m.group(0)
        self.assertIn('"/v1/sim-swap/enroll"', fn)
        self.assertIn('consent_source: "cs_mobile"', fn)
        self.assertIn('enrollment_type: "self"', fn)
        self.assertIn("consent_acknowledged: true", fn)
        self.assertNotIn("/v1/metered/sim-swap", fn,
                         "the metered one-shot lookup enrols nobody")

    def test_the_consent_text_is_byte_identical_to_the_server(self):
        """A carrier audit rests on this wording and four surfaces show it."""
        ts = (SRC / "api" / "relayshield.ts").read_text()
        m = re.search(r"CARRIER_CONSENT_TEXT\s*=\s*((?:\s*\"[^\"]*\"\s*\+?)+);", ts)
        self.assertTrue(m, "CARRIER_CONSENT_TEXT not found")
        literal = "".join(re.findall(r'"([^"]*)"', m.group(1)))
        self.assertEqual(literal, consent.CARRIER_CONSENT_TEXT)

    def test_enrol_cannot_be_pressed_before_the_consent_is_accepted(self):
        st = app_source("screens/SettingsScreen.tsx")
        self.assertIn("RS.CARRIER_CONSENT_TEXT", st, "the wording must be SHOWN, in full")
        self.assertRegex(st, r"disabled=\{!accepted\s*\|\|\s*busy\}")
        turn_on = re.search(r"async function turnOn\(\).*?\n  }\n", st, flags=re.S).group(0)
        self.assertIn("RS.enrollSimSwap", turn_on)

    def test_enrol_refuses_when_no_device_can_receive_the_alert(self):
        """Monitoring that cannot reach the user is the failure this feature
        exists to avoid, and the alert is a push notification."""
        st = app_source("screens/SettingsScreen.tsx")
        turn_on = re.search(r"async function turnOn\(\).*?\n  }\n", st, flags=re.S).group(0)
        self.assertLess(turn_on.index("PUSH_TOKEN_KEY"), turn_on.index("RS.enrollSimSwap"),
                        "the push-token check must come BEFORE the enrol call")

    def test_turning_it_off_withdraws_on_the_server(self):
        st = app_source("screens/SettingsScreen.tsx")
        self.assertIn("RS.withdrawSimSwap", st)


class TestTheAttackChainScreenIsBehindThePaywall(unittest.TestCase):

    def test_it_calls_the_timeline_endpoint(self):
        body = app_source("api/relayshield.ts")
        self.assertRegex(body, r"getIncidentTimeline[\s\S]*?/v1/metered/incident-timeline")

    def test_it_is_not_a_free_scan(self):
        """Andrew's call 2026-10-03: a real upstream cost sits behind the paywall."""
        scan = app_source("screens/ScanScreen.tsx")
        free = re.search(r"FREE_SCAN_TYPES[^=]*=\s*new Set<ScanType>\(\[(.*?)\]\)", scan, flags=re.S).group(1)
        self.assertNotIn('"timeline"', free)
        self.assertIn('"timeline"', scan)

    def test_it_is_not_called_on_every_render_or_tap(self):
        scan = app_source("screens/ScanScreen.tsx")
        self.assertIn("timelineCache", scan)
        self.assertIn("TIMELINE_TTL_MS", scan)

    def test_a_check_that_did_not_complete_never_renders_as_clear(self):
        """The three states must stay three: clear, could not check, not run."""
        c = app_source("components/IncidentTimeline.tsx")
        self.assertIn('check.checked === false) return "unknown"', c)
        self.assertIn('"skipped"', c)
        # The one legitimate use of the word is the disclaimer that a result is
        # NOT proof of safety; remove it, then nothing else may claim it.
        affirmative = c.replace("is not proof an account is safe", "")
        hit = re.search(r".{30}\b(safe|secure|protected)\b.{20}", affirmative)
        self.assertIsNone(hit, "the screen must never claim an identity is safe: " + (hit.group(0) if hit else ""))


class TestTheErrorNamesTheCallAndTheKeyIsTrimmed(unittest.TestCase):

    def test_the_error_names_the_endpoint(self):
        body = app_source("api/relayshield.ts")
        self.assertIn("RS API error ${status} on ${endpoint}", body)
        self.assertNotIn("RS API error ${resp.status}:", body,
                         "a bare status with no path is the report nobody can act on")

    def test_every_call_goes_through_the_trim(self):
        body = app_source("api/relayshield.ts")
        self.assertIn("cleanKey(apiKey)", body)
        # No call may put the raw key in a header.
        self.assertNotRegex(body, r'"X-RS-API-KEY"\]\s*=\s*apiKey')
        self.assertNotRegex(body, r'"X-API-Key":\s*apiKey\b')

    def test_the_version_was_bumped(self):
        """A build with three fixes and the same version number cannot be told
        apart from the old one on a device."""
        import json
        cfg = json.loads((APP / "app.json").read_text())["expo"]
        self.assertNotEqual(cfg["version"], "1.5.0")
        self.assertGreater(cfg["android"]["versionCode"], 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
