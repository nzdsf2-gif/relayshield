"""tools/prm_tag_resources.py: adds one tag, never overwrites another value, refuses the wrong account.

These use plain fake clients. The REAL request and response shapes were checked separately with
botocore.stub.Stubber (see LOG_CURRENT 2026-10-26, PRM), because a fake written by the same hand as the
code proves nothing about the library's shapes."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import prm_tag_resources as T  # noqa: E402

SPEC = json.load(open(ROOT / "aws_marketplace" / "prm_tag_spec.json"))


class Fake:
    """One fake for the three services. tags maps arn -> {key: value}; absent arn raises NotFound."""
    def __init__(self, tags):
        self.tags, self.writes = tags, []

    def _get(self, arn):
        if arn not in self.tags:
            raise RuntimeError("ResourceNotFoundException")
        return self.tags[arn]

    def list_tags(self, Resource): return {"Tags": dict(self._get(Resource))}
    def get_tags(self, resourceArn): return {"tags": dict(self._get(resourceArn))}
    def list_tags_of_resource(self, ResourceArn):
        return {"Tags": [{"Key": k, "Value": v} for k, v in self._get(ResourceArn).items()]}

    def tag_resource(self, **kw):
        arn = kw.get("Resource") or kw.get("resourceArn") or kw.get("ResourceArn")
        add = kw.get("Tags") or kw.get("tags")
        add = add if isinstance(add, dict) else {t["Key"]: t["Value"] for t in add}
        self.writes.append((arn, add))
        self.tags[arn].update(add)


def world(overrides=None, drop=()):
    tags = {arn: {} for _k, _n, arn in T.arns(SPEC, SPEC["account"])}
    for a in drop:
        tags.pop(a)
    tags.update(overrides or {})
    f = Fake(tags)
    return f, {"lambda": f, "apigateway": f, "dynamodb": f}


def run(clients, apply=False, account=None):
    lines = []
    rc = T.run(clients, lambda: account or SPEC["account"], SPEC, apply, out=lines.append)
    return rc, "\n".join(lines)


class SpecShape(unittest.TestCase):
    def test_tag_is_aws_apn_id_with_the_real_product_code(self):
        self.assertEqual(SPEC["tag_key"], "aws-apn-id")
        fixture = json.load(open(ROOT / "aws_marketplace/fixtures/prod_kkvurtspreofy_before_2026-10-25.json"))
        self.assertEqual(SPEC["tag_value"], "pc:" + fixture["Description"]["ProductCode"])

    def test_the_bundle_d_functions_are_listed(self):
        for n in ("relayshield-agentic-api", "relayshield-mcp-http"):
            self.assertIn(n, SPEC["lambda_functions"])


class Behaviour(unittest.TestCase):
    def test_dry_run_writes_nothing_and_lists_todo(self):
        f, c = world()
        rc, out = run(c)
        self.assertEqual((rc, f.writes), (0, []))
        self.assertIn("TODO", out)
        self.assertIn("Dry run only", out)

    def test_apply_adds_exactly_one_tag_and_keeps_the_others(self):
        arn = next(iter(world()[0].tags))
        f, c = world({arn: {"team": "x"}})
        rc, _ = run(c, apply=True)
        self.assertEqual(rc, 0)
        self.assertEqual(f.tags[arn], {"team": "x", "aws-apn-id": SPEC["tag_value"]})
        self.assertTrue(all(w[1] == {"aws-apn-id": SPEC["tag_value"]} for w in f.writes))

    def test_apply_twice_is_a_no_op(self):
        f, c = world()
        run(c, apply=True)
        n = len(f.writes)
        rc, out = run(c, apply=True)
        self.assertEqual((rc, len(f.writes)), (0, n))
        self.assertIn("0 to tag", out)

    def test_a_different_existing_value_is_never_overwritten(self):
        arn = next(iter(world()[0].tags))
        f, c = world({arn: {"aws-apn-id": "pc:other"}})
        rc, out = run(c, apply=True)
        self.assertEqual(rc, 1)
        self.assertEqual(f.tags[arn]["aws-apn-id"], "pc:other")
        self.assertIn("CONFLICT", out)

    def test_a_missing_resource_is_reported_not_created(self):
        arn = next(iter(world()[0].tags))
        f, c = world(drop=[arn])
        rc, out = run(c, apply=True)
        self.assertEqual(rc, 1)
        self.assertIn("MISSING", out)
        self.assertNotIn(arn, f.tags)

    def test_wrong_account_is_refused_before_any_read_or_write(self):
        f, c = world()
        rc, out = run(c, apply=True, account="620534471984")
        self.assertEqual((rc, f.writes), (2, []))
        self.assertIn("620534471984", out)


if __name__ == "__main__":
    unittest.main()
