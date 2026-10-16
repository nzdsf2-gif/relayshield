"""relayshield_verifier_nonces -- shared replay protection for the hosted verifiers.

    store = DynamoNonceStore("relayshield_verifier_nonces")
    store.seen("tap|<keyid>|<nonce>", now)   # False the first time, True on any repeat

WHY THIS EXISTS. Replay protection has to be shared by every Lambda container, or it is
not protection: a replay that lands on a different container than the original finds an
empty cache. The TAP verifier also built `MemoryNonceStore()` INSIDE the call whenever no
store was passed, so even one container forgot every nonce as soon as the request ended.

HOW. One conditional PutItem per nonce: it succeeds only if the key is not already there,
so "have I seen this" and "remember it" are ONE atomic step. A GetItem followed by a
PutItem would let two simultaneous replays both pass. A DynamoDB TTL deletes rows late
(up to a couple of days), so an expired row is treated as absent by the condition and
overwritten, not trusted.

FAILURE. Any error other than "already exists" RAISES. The caller decides what that
means; the TAP verifier answers a reject with the reason `nonce_store_error`, which
threat telemetry does not count as an attack. Silently treating a failed lookup as "not
seen" would turn a DynamoDB outage into a free replay window.

Keys are namespaced by the caller ("tap|keyid|nonce", "x401|issuer|jti") because nonces
are only unique per signer, and the key holds a hash, never the nonce, the key id or the
issuer themselves.
"""

import hashlib
import time

DEFAULT_TABLE = "relayshield_verifier_nonces"
# Longer than the freshness window plus clock skew, so a nonce is remembered for as long
# as the request it came with could still be accepted.
DEFAULT_TTL_SECONDS = 3600


class DynamoNonceStore:
    def __init__(self, table_name=DEFAULT_TABLE, ttl_seconds=DEFAULT_TTL_SECONDS, table=None):
        self.table_name = table_name
        self.ttl_seconds = int(ttl_seconds)
        self._table = table

    def _tbl(self):
        if self._table is None:
            import boto3  # lazily: the pure parts of the verifier import with nothing installed
            self._table = boto3.resource("dynamodb").Table(self.table_name)
        return self._table

    @staticmethod
    def key(nonce) -> str:
        return hashlib.sha256(str(nonce).encode("utf-8")).hexdigest()

    def seen(self, nonce, now=None) -> bool:
        """True if this nonce was already recorded (a replay); False if it is new, and it
        is recorded by this very call."""
        now = int(now if now is not None else time.time())
        try:
            self._tbl().put_item(
                Item={"pk": self.key(nonce), "ttl": now + self.ttl_seconds},
                ConditionExpression="attribute_not_exists(pk) OR #t < :now",
                ExpressionAttributeNames={"#t": "ttl"},
                ExpressionAttributeValues={":now": now},
            )
            return False
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
            if code == "ConditionalCheckFailedException":
                return True
            raise
