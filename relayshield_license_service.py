#!/usr/bin/env python3
"""RelayShield license service: GET /v1/license/status.

The RelayShield-side endpoint the appliance license gate calls to
ask whether a key is revoked. It is the online half of Step 4
licensing. The appliance calls it with the key's kid and tid; the
service answers active or revoked. Expiry is enforced offline by
the appliance (the service is never sent the key's expiry), so the
service only ever returns active or revoked.

Interface (defined by the license module, mcp_proxy/license.py):
    GET /v1/license/status?kid=<kid>&tid=<tid>
    Response JSON: {"status": "active"} or {"status": "revoked"}
    The kid and tid identify the key. A missing kid or tid is a 400.

Revocation records live in DynamoDB table
relayshield_license_revocations, keyed by tid (the tenant). Each
item carries:
    tid:            the tenant id (partition key)
    revoked_kids:   list of kids revoked for this tenant
    revoked_all:    bool, when true every key for the tenant is revoked
    revoked_reason: why (free text, e.g. "non-payment")
    updated_at:     ISO timestamp of the last revocation change
Revocations are written by the issuer tool (revoke subcommand) and
by the Stripe issuance flow (refund, subscription cancelled). This
Lambda is read-only for the appliance; it never writes a revocation.

Deployment: this file is a standalone Lambda (boto3, DynamoDB,
logging), following the RelayShield breach monitor Lambda pattern.
Wire it to API Gateway as GET /v1/license/status on
api.relayshield.net, with the table name in the
LICENSE_REVOCATIONS_TABLE env var. Deploy with the "Deploy Changed
Lambdas to AWS" workflow from main, on Andrew's separate go. Do not
deploy from a feature branch.

No em dashes in user-facing copy.
"""

import json
import logging
import os

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# boto3 is available in the Lambda runtime. It is not installed in
# the Muse VM, so the import is lazy: the pure logic
# (license_status_for with an injected table) is testable without
# it, and the Lambda path raises a clear error when boto3 is absent.
try:
    import boto3
    dynamodb = boto3.resource("dynamodb")
except ImportError:  # pragma: no cover - local test only
    boto3 = None
    dynamodb = None

LICENSE_REVOCATIONS_TABLE = os.environ.get(
    "LICENSE_REVOCATIONS_TABLE", "relayshield_license_revocations")


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def license_status_for(kid, tid, table=None):
    """Return the license status for a (kid, tid) pair.

    Returns "active" or "revoked". The lookup is by tid: the
    revocation record for the tenant lists the revoked kids and
    whether every key for the tenant is revoked. No record for the
    tenant means nothing is revoked, so the key is active. A
    missing or empty kid or tid is not a lookup; the caller treats
    it as a 400 before calling this.
    """
    if table is None:
        if dynamodb is None:
            raise RuntimeError(
                "boto3 is not available; pass a table (test) or run "
                "in Lambda")
        table = dynamodb.Table(LICENSE_REVOCATIONS_TABLE)
    try:
        item = table.get_item(Key={"tid": tid}).get("Item") or {}
    except Exception as exc:
        # A DynamoDB failure must not lock a paying customer out.
        # Log it and answer active; the appliance's offline check
        # (signature plus expiry) still governs, and the 7-day cap
        # still bounds offline operation.
        logger.exception(
            "license status lookup failed for tid=%s: %s", tid, exc)
        return "active"
    if item.get("revoked_all"):
        logger.info(
            "license status revoked (tenant-wide) tid=%s kid=%s",
            tid, kid)
        return "revoked"
    revoked_kids = item.get("revoked_kids") or []
    if kid in revoked_kids:
        logger.info(
            "license status revoked tid=%s kid=%s", tid, kid)
        return "revoked"
    return "active"


def lambda_handler(event, context):
    """API Gateway proxy integration entry point.

    GET /v1/license/status?kid=<kid>&tid=<tid>
    Returns {"status": "active"} or {"status": "revoked"}.
    A missing kid or tid is a 400. A DynamoDB failure answers
    active (fail open on the service side, because the appliance
    still enforces signature, expiry, and the 7-day cap offline).
    """
    params = event.get("queryStringParameters") or {}
    kid = (params.get("kid") or "").strip()
    tid = (params.get("tid") or "").strip()
    logger.info("license status request kid=%s tid=%s", kid, tid)
    if not kid or not tid:
        return _response(400, {
            "error": "kid and tid query parameters are required",
        })
    status = license_status_for(kid, tid)
    return _response(200, {"status": status})


if __name__ == "__main__":
    # Local smoke test: python3 step4-license-service-2026-11-09.py
    # Prints the status for a tid with no revocation record. Uses a
    # stub table, so no AWS credentials are needed.
    class _StubTable:
        def get_item(self, Key):
            return {}

    print(license_status_for("rslic-2026-11", "tnt_test",
                             table=_StubTable()))
    print(license_status_for(
        "rslic-2026-11", "tnt_test",
        table=type("_T", (), {
            "get_item": staticmethod(
                lambda Key: {"Item": {
                    "tid": "tnt_test",
                    "revoked_kids": ["rslic-2026-11"],
                    "revoked_all": False}}),
        })()))
