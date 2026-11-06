"""Phase 3b signed-verdict tenant proof, for review, Mac test only.

Place this file in /Users/andrewgibbs/dev/relayshield/mcp_proxy,
next to proxy.py, then run:
  python3 -m pytest test_tenant_session_ph3b_signed_verdict_proof.py -q

This proves, with the real VerdictSigner and a fresh random
key:

1. A verdict issued with tenant_id, binding_id, and
   location_id carries them, and verify() returns True.
2. Tampering with the tenant_id after issue breaks the
   signature, verify() returns False, so the tenant is
   inside the signature, not beside it, and cannot be
   stripped or swapped without detection.
3. A verdict issued without a tenant carries empty tenant
   fields and still verifies, so existing callers are
   unchanged.
4. Source check, proxy.py: exactly the 3 signer.issue calls
   in _handle_tools_call carry tenant_id=_audit_tenant, and
   the 1 signer.issue call in _record_kill_chain_outcome
   carries tenant_id=_kc_tenant, resolved from corr.
"""

import os
import pathlib
import re

from mcp_proxy.verdicts import VerdictSigner


def _signer():
    return VerdictSigner(signing_key_hex=os.urandom(32).hex())


def test_verdict_carries_tenant_and_verifies():
    signer = _signer()
    assert signer.signing_enabled
    verdict = signer.issue(
        decision="block", tool_name="check_link",
        content_hash="abc123", evidence=[],
        poison_category="kill_chain",
        tenant_id="tenant-a", binding_id="bind_test",
        location_id="loc-1")
    assert verdict["tenant_id"] == "tenant-a"
    assert verdict["binding_id"] == "bind_test"
    assert verdict["location_id"] == "loc-1"
    assert signer.verify(verdict) is True


def test_tampered_tenant_breaks_signature():
    signer = _signer()
    verdict = signer.issue(
        decision="block", tool_name="check_link",
        content_hash="abc123", evidence=[],
        poison_category="kill_chain",
        tenant_id="tenant-a", binding_id="bind_test",
        location_id="loc-1")
    verdict["tenant_id"] = "tenant-b"
    assert signer.verify(verdict) is False


def test_default_verdict_has_empty_tenant_and_verifies():
    signer = _signer()
    verdict = signer.issue(
        decision="allow", tool_name="check_link",
        content_hash="abc123", evidence=[],
        poison_category="clean")
    assert verdict["tenant_id"] == ""
    assert verdict["binding_id"] == ""
    assert verdict["location_id"] == ""
    assert signer.verify(verdict) is True


def _issue_calls(body):
    """Return the text of every signer.issue( call in body,
    matched by paren counting, so nested calls do not cut
    the match short."""
    calls = []
    i = 0
    while True:
        j = body.find("signer.issue(", i)
        if j == -1:
            return calls
        depth = 0
        k = j
        while k < len(body):
            ch = body[k]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        calls.append(body[j:k + 1])
        i = k + 1


def test_proxy_verdict_sites():
    text = pathlib.Path(__file__).with_name("proxy.py").read_text(encoding="utf-8")

    def body_of(name):
        funcs = list(re.finditer(rf"^    def {name}\(", text, flags=re.MULTILINE))
        assert len(funcs) == 1
        start = funcs[0].end()
        rest = text[start:]
        nxt = re.search(r"^    def ", rest, flags=re.MULTILINE)
        return rest[:nxt.start()] if nxt else rest

    # Only the kwargs inside signer.issue( calls count. The
    # audit rows and evaluate calls in _handle_tools_call
    # also carry tenant_id=_audit_tenant, and a plain count
    # of the whole function body would mix them in.
    tc = _issue_calls(body_of("_handle_tools_call"))
    assert len(tc) == 4
    for call in tc:
        assert "tenant_id=_audit_tenant" in call
        assert "binding_id=_audit_binding" in call
        assert "location_id=_audit_location" in call
    sr = body_of("_screen_result")
    assert "_sr_tenant, _sr_binding, _sr_location = self._audit_session_fields(_sr_corr_key)" in sr
    sr_calls = _issue_calls(sr)
    assert len(sr_calls) == 1
    assert "tenant_id=_sr_tenant" in sr_calls[0]
    assert "binding_id=_sr_binding" in sr_calls[0]
    assert "location_id=_sr_location" in sr_calls[0]
    sd_calls = _issue_calls(body_of("_screen_discovery"))
    assert len(sd_calls) == 1
    assert "tenant_id=tenant_id" in sd_calls[0]
    assert 'binding_id=""' in sd_calls[0]
    assert 'location_id=""' in sd_calls[0]
    # _record_kill_chain_outcome issues no verdict.
    assert _issue_calls(body_of("_record_kill_chain_outcome")) == []
