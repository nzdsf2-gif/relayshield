"""Exercise the SIM swap consent state machine against a fake DynamoDB + KMS.

The point is the invariant: sim_swap_monitoring == True must mean "this number's
own owner consented". Every test below is a way that could go wrong.
"""
import base64
import importlib
import sys
import types
from unittest import mock

sys.path.insert(0, "/Users/andrewgibbs/Side SaaS Hustle")

# ---- fake AWS -------------------------------------------------------------
STORE = {}          # user_id -> item
BY_HASH = {}        # phone_hash -> [user_id, ...]


class FakeTable:
    def __init__(self, name): self.name = name

    def query(self, **kw):
        cond = kw.get("KeyConditionExpression")
        ph = cond._values[1] if hasattr(cond, "_values") else None
        return {"Items": [STORE[u] for u in BY_HASH.get(ph, []) if u in STORE]}

    def put_item(self, Item):
        STORE[Item["user_id"]] = dict(Item)
        BY_HASH.setdefault(Item["phone_hash"], [])
        if Item["user_id"] not in BY_HASH[Item["phone_hash"]]:
            BY_HASH[Item["phone_hash"]].append(Item["user_id"])

    def update_item(self, Key, UpdateExpression, ExpressionAttributeValues,
                    ExpressionAttributeNames=None):
        item = STORE[Key["user_id"]]
        names = ExpressionAttributeNames or {}
        expr = UpdateExpression
        set_part = expr.split("REMOVE")[0].replace("SET", "", 1)
        for assign in set_part.split(","):
            if "=" not in assign:
                continue
            lhs, rhs = [s.strip() for s in assign.split("=", 1)]
            field = names.get(lhs, lhs)
            item[field] = ExpressionAttributeValues[rhs]
        if "REMOVE" in expr:
            for f in expr.split("REMOVE")[1].split(","):
                item.pop(f.strip(), None)


class FakeDynamo:
    def Table(self, name): return FakeTable(name)


class FakeKMS:
    def encrypt(self, KeyId, Plaintext):
        return {"CiphertextBlob": b"ENC:" + Plaintext}


def fake_boto3_client(name, *a, **k):
    return FakeKMS() if name == "kms" else mock.MagicMock()


def _Key(field):
    return types.SimpleNamespace(
        eq=lambda v: types.SimpleNamespace(_values=(field, v)))


conditions_mod = types.ModuleType("boto3.dynamodb.conditions")
conditions_mod.Key = _Key
conditions_mod.Attr = mock.MagicMock()

dynamodb_mod = types.ModuleType("boto3.dynamodb")
dynamodb_mod.conditions = conditions_mod

fake_boto3 = types.ModuleType("boto3")
fake_boto3.client = fake_boto3_client
fake_boto3.resource = lambda *a, **k: FakeDynamo()
fake_boto3.dynamodb = dynamodb_mod

patched = {
    "boto3": fake_boto3,
    "boto3.dynamodb": dynamodb_mod,
    "boto3.dynamodb.conditions": conditions_mod,
}

with mock.patch.dict(sys.modules, patched):
    api = importlib.import_module("relayshield_api")
    consent = importlib.import_module("relayshield_sim_swap_consent")
    api.dynamodb = FakeDynamo()
    consent._dynamodb = FakeDynamo()
    consent._kms = FakeKMS()


KEY = {"api_key": "rs_test_key_for_state_machine"}
api.enroll   = lambda p: api.handle_sim_swap_enroll(p, api_key_record=KEY)
api.confirm  = lambda p: api.handle_sim_swap_confirm(p, api_key_record=KEY)
api.withdraw = lambda p: api.handle_sim_swap_withdraw(p, api_key_record=KEY)

PHONE = "+12125551234"
OTHER = "+12125559999"


def body(resp):
    import json
    return json.loads(resp["body"])


def reset():
    STORE.clear(); BY_HASH.clear()


results = []
def check(name, cond, detail=""):
    results.append((name, cond, detail))
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"   {detail}" if not cond and detail else ""))


# 1. self enrollment -> monitoring on immediately
reset()
r = api.enroll(
    {"phone": PHONE, "enrollment_type": "self", "consent_source": "cs_mobile",
     "consent_acknowledged": True})
d = body(r)["data"]
check("self enroll -> CONFIRMED", d["consent_state"] == "CONFIRMED", str(d))
check("self enroll -> monitoring True", d["monitoring"] is True)
check("self enroll records terms version", d["terms_version"] == api.CONSENT_TERMS_VERSION)
check("self enroll issues NO token", "confirmation_token" not in d)
stored = STORE[d["user_id"]]
check("phone stored encrypted, not plaintext",
      PHONE not in str(stored.get("phone_encrypted")) and stored["phone_encrypted"].startswith(base64.b64encode(b"ENC:")[:4].decode()))
check("consent_at recorded", "consent_at" in stored)

# 2. self enrollment WITHOUT acknowledgement is refused
reset()
r = api.enroll(
    {"phone": PHONE, "enrollment_type": "self", "consent_source": "cs_mobile"})
check("self enroll requires consent_acknowledged", r["statusCode"] >= 400, str(r["statusCode"]))
check("refused enrollment wrote nothing", len(STORE) == 0)

# 3. third-party enrollment -> PENDING, NOT monitored
reset()
r = api.enroll(
    {"phone": OTHER, "enrollment_type": "third_party", "consent_source": "whatsapp"})
d = body(r)["data"]
tok = d.get("confirmation_token", "")
check("third-party -> PENDING", d["consent_state"] == "PENDING")
check("third-party NOT monitored", d["monitoring"] is False)
check("third-party issues a token", len(tok) > 20)
check("stored record has monitoring False", STORE[d["user_id"]]["sim_swap_monitoring"] is False)

# 4. wrong token cannot enable monitoring
r = api.confirm( {"phone": OTHER, "confirmation_token": "wrong-token-value"})
check("confirm with wrong token rejected", r["statusCode"] == 403, str(r["statusCode"]))
check("still not monitored after bad token",
      STORE[list(STORE)[0]]["sim_swap_monitoring"] is False)

# 5. correct token enables it
r = api.confirm( {"phone": OTHER, "confirmation_token": tok})
d = body(r)["data"]
check("confirm with right token -> CONFIRMED", d["consent_state"] == "CONFIRMED")
check("now monitored", d["monitoring"] is True)
rec = STORE[d["user_id"]]
check("token cleared after use", "consent_token" not in rec)
check("consent_method records double opt-in", rec["consent_method"] == "double_opt_in_reply")

# 6. token cannot be replayed
r = api.confirm( {"phone": OTHER, "confirmation_token": tok})
check("token not replayable", r["statusCode"] == 409, str(r["statusCode"]))

# 7. withdrawal turns monitoring off
r = api.withdraw( {"phone": OTHER})
d = body(r)["data"]
check("withdraw -> WITHDRAWN", d["consent_state"] == "WITHDRAWN")
check("withdraw stops monitoring", d["monitoring"] is False)

# 8. re-enrolling an existing number updates, never duplicates
reset()
r1 = api.enroll(
    {"phone": PHONE, "enrollment_type": "self", "consent_source": "stripe_checkout",
     "consent_acknowledged": True})
uid1 = body(r1)["data"]["user_id"]
r2 = api.enroll(
    {"phone": PHONE, "enrollment_type": "self", "consent_source": "cs_mobile",
     "consent_acknowledged": True})
uid2 = body(r2)["data"]["user_id"]
check("re-enroll reuses the same user_id", uid1 == uid2, f"{uid1} vs {uid2}")
check("no duplicate record created", len(STORE) == 1, f"{len(STORE)} records")
check("consent_source updated on re-enroll", STORE[uid1]["consent_source"] == "cs_mobile")

# 9. input validation
reset()
for bad in ["2125551234", "+1", "", "notaphone", "+1212555123456789012"]:
    r = api.enroll(
        {"phone": bad, "enrollment_type": "self", "consent_source": "web",
         "consent_acknowledged": True})
    check(f"rejects malformed phone {bad!r}", r["statusCode"] >= 400)
r = api.enroll(
    {"phone": PHONE, "enrollment_type": "self", "consent_source": "not_a_source",
     "consent_acknowledged": True})
check("rejects unknown consent_source", r["statusCode"] >= 400)
check("no writes from any invalid input", len(STORE) == 0)

# 10. confirm on a number with no enrollment
r = api.confirm( {"phone": "+12125550000", "confirmation_token": "x" * 30})
check("confirm on unknown number -> 404", r["statusCode"] == 404, str(r["statusCode"]))


# 11. UNAUTHENTICATED calls must be refused on every endpoint
reset()
for name, fn, args in [
    ("enroll", api.handle_sim_swap_enroll,
     {"phone": PHONE, "enrollment_type": "self", "consent_source": "web", "consent_acknowledged": True}),
    ("confirm", api.handle_sim_swap_confirm, {"phone": PHONE, "confirmation_token": "x" * 30}),
    ("withdraw", api.handle_sim_swap_withdraw, {"phone": PHONE}),
]:
    r = fn(args, api_key_record=None)
    check(f"{name} rejects unauthenticated", r["statusCode"] == 401, str(r["statusCode"]))
check("unauthenticated calls wrote nothing", len(STORE) == 0)


# 12. DUPLICATE phone_hash records: the bug that hit production 2026-08-14
reset()
ph = consent.hash_phone(PHONE)
STORE["stale-test-acct"] = {"user_id": "stale-test-acct", "phone_hash": ph,
                            "active": False, "sim_swap_monitoring": False,
                            "updated_at": "2026-08-07T00:00:00+00:00"}
STORE["real-acct"] = {"user_id": "real-acct", "phone_hash": ph,
                      "active": True, "sim_swap_monitoring": True,
                      "updated_at": "2026-08-14T00:00:00+00:00"}
BY_HASH[ph] = ["stale-test-acct", "real-acct"]
found = consent.find_user_by_phone_hash(ph)
check("duplicate hashes: picks the ACTIVE record, not an arbitrary one",
      found["user_id"] == "real-acct", str(found.get("user_id")))
check("stale deactivated record left alone",
      STORE["stale-test-acct"]["active"] is False)

# two ACTIVE duplicates must refuse rather than guess
STORE["second-active"] = {"user_id": "second-active", "phone_hash": ph,
                          "active": True, "sim_swap_monitoring": False,
                          "updated_at": "2026-08-10T00:00:00+00:00"}
BY_HASH[ph].append("second-active")
r = api.enroll({"phone": PHONE, "enrollment_type": "self",
                "consent_source": "api", "consent_acknowledged": True})
check("two active duplicates -> 409, refuses to guess", r["statusCode"] == 409, str(r["statusCode"]))
check("ambiguous enroll changed nothing",
      STORE["real-acct"]["sim_swap_monitoring"] is True
      and STORE["second-active"]["sim_swap_monitoring"] is False)

failed = [n for n, ok, _ in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} passed")
if failed:
    print("FAILED: " + ", ".join(failed))
sys.exit(1 if failed else 0)
