"""Unit tests for pre-payment intent binding (v1 + v2 decisions)."""

import copy
import hashlib
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from intent_binding import (
    Artifact,
    Binding,
    BindingPolicy,
    BindingRefused,
    Ed25519Signer,
    ExecutedPayment,
    FunctionTextExtractor,
    InMemoryBindingStore,
    IntentBinder,
    NotEvaluatedImageScreener,
    OCRUnavailableError,
    OcrInvoiceImageScreener,
    PaymentIntent,
    ScreenResult,
    TesseractTextExtractor,
    RC_AMOUNT_MISMATCH,
    RC_ARTIFACT_FLAGGED,
    RC_ARTIFACT_MISSING,
    RC_ARTIFACT_TAMPERED,
    RC_ARTIFACT_UNEXPECTED,
    RC_BINDING_ALREADY_CONSUMED,
    RC_BINDING_EXPIRED,
    RC_COUNTERPARTY_FLAGGED,
    RC_COUNTERPARTY_MISMATCH,
    RC_CURRENCY_MISMATCH,
    RC_INVALID_INTENT,
    RC_INVOICE_IMAGE_FLAGGED,
    RC_OK,
    RC_SCREEN_NOT_EVALUATED,
    RC_SIGNATURE_INVALID,
)

# Deterministic test seed. Test-only: never use a derived seed in
# production.
TEST_SEED_HEX = bytes(range(32)).hex()

PAYER = "agent:buyer-42"
SELLER = "seller.example"
# The counterparty identity is the seller (domain / service id), not
# a session-specific checkout URL: canonicalization keeps host+path,
# so "https://seller.example/" and "seller.example" are the same
# counterparty, while a checkout path would be a different one.
SELLER_URL = "https://seller.example/"


class FakeClock:
    def __init__(self, start=1_760_000_000):
        self.t = start

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


class FakeCounterpartyScreener:
    """Flags counterparty identifiers in a fixed set."""

    def __init__(self, flagged=(), unevaluated=False):
        self.flagged = {s.lower() for s in flagged}
        self.unevaluated = unevaluated
        self.calls = []

    def screen_counterparty(self, counterparty, context):
        self.calls.append(counterparty)
        if self.unevaluated:
            return ScreenResult.not_evaluated("fake screener offline")
        if counterparty.lower() in self.flagged or \
                counterparty.rsplit("://", 1)[-1].strip("/").lower() \
                in self.flagged:
            return ScreenResult.flagged_result(
                ["counterparty appears in the threat corpus "
                 "(fake screen)"],
                evidence=[{"type": "corpus_hit", "id": counterparty}])
        return ScreenResult.no_flags()


class FakeArtifactScreener:
    """Flags artifacts whose descriptor carries {"flag": true}."""

    def screen_artifact(self, artifact, context):
        if artifact.descriptor.get("flag"):
            return ScreenResult.flagged_result(
                [f"artifact {artifact.artifact_id} carries a fraud "
                 "signal (fake screen)"])
        return ScreenResult.no_flags()


class FakeImageScreener:
    """Evaluates invoice images: flags a known-bad image hash."""

    def __init__(self, bad_hashes=()):
        self.bad_hashes = set(bad_hashes)

    def screen_invoice_image(self, image_ref, image_sha256, context):
        if image_sha256 in self.bad_hashes:
            return ScreenResult.flagged_result(
                ["invoice image renders payment instructions to a "
                 "flagged wallet (fake OCR screen)"])
        return ScreenResult.no_flags()


def _cart(total="25.00", qty=1):
    return Artifact(
        artifact_id="cart",
        kind="cart",
        descriptor={
            "seller": SELLER,
            "items": [{"sku": "WIDGET-1", "qty": qty, "price": total}],
            "total": total,
            "currency": "USD",
        })


def _invoice(number="INV-100", total="25.00"):
    return Artifact(
        artifact_id="invoice",
        kind="invoice",
        descriptor={
            "number": number,
            "seller": SELLER,
            "total": total,
            "currency": "USD",
            "payee": "Seller Example LLC",
        })


def _intent(**overrides):
    intent = PaymentIntent(
        payer=PAYER,
        counterparty=SELLER_URL,
        amount="25.00",
        currency="USD",
        artifacts=[_cart(), _invoice()],
        tap_intent_ref="tap_intent_abc",
    )
    for key, value in overrides.items():
        setattr(intent, key, value)
    return intent


def _executed(**overrides):
    executed = ExecutedPayment(
        payer=PAYER,
        counterparty=SELLER,  # bare domain: canonicalizes to the URL host
        amount="25.00",
        currency="USD",
        artifacts=[_cart(), _invoice()],
        rail_reference="skyfire_token_123",
    )
    for key, value in overrides.items():
        setattr(executed, key, value)
    return executed


class IntentBindingTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.signer = Ed25519Signer(TEST_SEED_HEX)
        self.cp_screener = FakeCounterpartyScreener()
        self.art_screener = FakeArtifactScreener()
        self.store = InMemoryBindingStore()
        self.binder = self._make_binder()

    def _make_binder(self, **kwargs):
        kwargs.setdefault("now_fn", self.clock)
        kwargs.setdefault("store", self.store)
        return IntentBinder(
            self.signer,
            counterparty_screener=self.cp_screener,
            artifact_screener=self.art_screener,
            **kwargs)

    # -- happy path ---------------------------------------------------

    def test_happy_path_match_allows_and_consumes(self):
        binding = self.binder.create_binding(_intent())
        self.assertTrue(binding.binding_id.startswith("bind_"))
        self.assertTrue(binding.signature_valid())
        self.assertEqual(
            binding.record["verdicts"]["counterparty"]["status"],
            "no_flags_found")

        decision = self.binder.verify_at_settlement(binding, _executed())
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason_codes, [RC_OK])
        # Wording rule: an allow never claims a payment is "safe".
        self.assertNotIn("safe", " ".join(decision.reasons).lower()
                         .replace("not a guarantee", ""))
        self.assertTrue(self.store.is_consumed(binding.binding_id))

    def test_verify_by_binding_id_from_store(self):
        binding = self.binder.create_binding(_intent())
        decision = self.binder.verify_at_settlement(
            binding.binding_id, _executed())
        self.assertTrue(decision.allowed)

    # -- amount checks --------------------------------------------------

    def test_amount_within_tolerance_allows(self):
        binder = self._make_binder(amount_tolerance_minor=100)
        binding = binder.create_binding(_intent())
        # $25.50 against a bound $25.00 with $1.00 tolerance.
        decision = binder.verify_at_settlement(
            binding, _executed(amount="25.50"))
        self.assertTrue(decision.allowed)

    def test_amount_drift_beyond_tolerance_blocks(self):
        binder = self._make_binder(amount_tolerance_minor=100)
        binding = binder.create_binding(_intent())
        # $30.00 against a bound $25.00, tolerance $1.00.
        decision = binder.verify_at_settlement(
            binding, _executed(amount="30.00"))
        self.assertFalse(decision.allowed)
        self.assertIn(RC_AMOUNT_MISMATCH, decision.reason_codes)
        # A block must not consume the binding: the corrected
        # payment can still settle.
        self.assertFalse(self.store.is_consumed(binding.binding_id))
        fixed = binder.verify_at_settlement(binding, _executed())
        self.assertTrue(fixed.allowed)

    def test_amount_below_bound_also_blocks(self):
        binding = self.binder.create_binding(_intent())
        decision = self.binder.verify_at_settlement(
            binding, _executed(amount="24.99"))
        self.assertFalse(decision.allowed)
        self.assertIn(RC_AMOUNT_MISMATCH, decision.reason_codes)

    def test_currency_mismatch_blocks(self):
        binding = self.binder.create_binding(_intent())
        decision = self.binder.verify_at_settlement(
            binding, _executed(currency="EUR"))
        self.assertFalse(decision.allowed)
        self.assertIn(RC_CURRENCY_MISMATCH, decision.reason_codes)

    # -- counterparty swap ----------------------------------------------

    def test_counterparty_swap_blocks(self):
        binding = self.binder.create_binding(_intent())
        # Screened seller.example; settlement pays a lookalike.
        decision = self.binder.verify_at_settlement(
            binding, _executed(counterparty="seller-example.evil.test"))
        self.assertFalse(decision.allowed)
        self.assertIn(RC_COUNTERPARTY_MISMATCH, decision.reason_codes)

    def test_payer_swap_blocks(self):
        binding = self.binder.create_binding(_intent())
        decision = self.binder.verify_at_settlement(
            binding, _executed(payer="agent:someone-else"))
        self.assertFalse(decision.allowed)
        self.assertIn("PAYER_MISMATCH", decision.reason_codes)

    # -- artifact integrity ----------------------------------------------

    def test_artifact_tamper_blocks(self):
        binding = self.binder.create_binding(_intent())
        tampered_cart = _cart(total="0.01")  # line total edited after binding
        decision = self.binder.verify_at_settlement(
            binding, _executed(artifacts=[tampered_cart, _invoice()]))
        self.assertFalse(decision.allowed)
        self.assertIn(RC_ARTIFACT_TAMPERED, decision.reason_codes)

    def test_artifact_missing_blocks(self):
        binding = self.binder.create_binding(_intent())
        decision = self.binder.verify_at_settlement(
            binding, _executed(artifacts=[_cart()]))  # invoice dropped
        self.assertFalse(decision.allowed)
        self.assertIn(RC_ARTIFACT_MISSING, decision.reason_codes)

    def test_unexpected_artifact_blocks(self):
        binding = self.binder.create_binding(_intent())
        extra = Artifact(artifact_id="giftcard", kind="other",
                         descriptor={"sku": "GC-50", "price": "50.00"})
        decision = self.binder.verify_at_settlement(
            binding,
            _executed(artifacts=[_cart(), _invoice(), extra]))
        self.assertFalse(decision.allowed)
        self.assertIn(RC_ARTIFACT_UNEXPECTED, decision.reason_codes)

    def test_invoice_image_bytes_are_bound(self):
        image_bytes = b"\x89PNG fake invoice image bytes"
        image = Artifact(
            artifact_id="invoice-img",
            kind="invoice_image",
            descriptor={"image_ref": "mem://invoice.png",
                        "image_sha256":
                            hashlib.sha256(image_bytes).hexdigest()},
            content_bytes=image_bytes)
        intent = _intent(artifacts=[_cart(), _invoice(), image])
        binding = self.binder.create_binding(intent)
        # Same descriptor, different bytes: the presented image is
        # not the screened image.
        swapped = Artifact(
            artifact_id="invoice-img",
            kind="invoice_image",
            descriptor={"image_ref": "mem://invoice.png",
                        "image_sha256":
                            hashlib.sha256(image_bytes).hexdigest()},
            content_bytes=b"\x89PNG edited payee details")
        decision = self.binder.verify_at_settlement(
            binding, _executed(artifacts=[_cart(), _invoice(), swapped]))
        self.assertFalse(decision.allowed)
        self.assertIn(RC_ARTIFACT_TAMPERED, decision.reason_codes)

    # -- expiry and replay -------------------------------------------------

    def test_expired_binding_blocks(self):
        binding = self.binder.create_binding(_intent())
        self.clock.advance(901)  # default TTL is 900 seconds
        decision = self.binder.verify_at_settlement(binding, _executed())
        self.assertFalse(decision.allowed)
        self.assertIn(RC_BINDING_EXPIRED, decision.reason_codes)

    def test_replay_of_consumed_binding_blocks(self):
        binding = self.binder.create_binding(_intent())
        first = self.binder.verify_at_settlement(binding, _executed())
        self.assertTrue(first.allowed)
        second = self.binder.verify_at_settlement(binding, _executed())
        self.assertFalse(second.allowed)
        self.assertIn(RC_BINDING_ALREADY_CONSUMED, second.reason_codes)

    # -- signature integrity ----------------------------------------------

    def test_altered_record_fails_signature(self):
        binding = self.binder.create_binding(_intent())
        forged = Binding.from_dict(copy.deepcopy(binding.to_dict()))
        forged.record["amount_minor"] = 1  # attacker edits the amount
        self.assertFalse(forged.signature_valid())
        decision = self.binder.verify_at_settlement(forged, _executed())
        self.assertFalse(decision.allowed)
        self.assertIn(RC_SIGNATURE_INVALID, decision.reason_codes)

    def test_unknown_binding_id_blocks(self):
        decision = self.binder.verify_at_settlement(
            "bind_doesnotexist", _executed())
        self.assertFalse(decision.allowed)
        self.assertIn("BINDING_NOT_FOUND", decision.reason_codes)

    # -- screening at creation ----------------------------------------------

    def test_flagged_counterparty_prevents_creation(self):
        self.cp_screener = FakeCounterpartyScreener(flagged={SELLER})
        binder = self._make_binder()
        with self.assertRaises(BindingRefused) as ctx:
            binder.create_binding(_intent())
        self.assertIn(RC_COUNTERPARTY_FLAGGED, ctx.exception.reason_codes)
        self.assertEqual(
            ctx.exception.verdicts["counterparty"]["status"], "flagged")
        # Nothing was stored, so nothing can be settled against it.

    def test_flagged_artifact_prevents_creation(self):
        flagged_invoice = _invoice()
        flagged_invoice.descriptor["flag"] = True
        with self.assertRaises(BindingRefused) as ctx:
            self.binder.create_binding(
                _intent(artifacts=[_cart(), flagged_invoice]))
        self.assertIn(RC_ARTIFACT_FLAGGED, ctx.exception.reason_codes)

    def test_unevaluated_counterparty_screen_prevents_creation(self):
        self.cp_screener = FakeCounterpartyScreener(unevaluated=True)
        binder = self._make_binder()
        with self.assertRaises(BindingRefused) as ctx:
            binder.create_binding(_intent())
        self.assertIn(RC_SCREEN_NOT_EVALUATED, ctx.exception.reason_codes)

    def test_empty_artifact_set_prevents_creation(self):
        with self.assertRaises(BindingRefused):
            self.binder.create_binding(_intent(artifacts=[]))

    # -- invoice image hook ---------------------------------------------------

    def test_image_stub_records_not_evaluated(self):
        image = Artifact(
            artifact_id="invoice-img",
            kind="invoice_image",
            descriptor={"image_ref": "mem://invoice.png",
                        "image_sha256": "ab" * 32})
        binding = self.binder.create_binding(
            _intent(artifacts=[_cart(), _invoice(), image]))
        image_verdict = \
            binding.record["verdicts"]["invoice_images"]["invoice-img"]
        self.assertEqual(image_verdict["status"], "not_evaluated")
        self.assertTrue(image_verdict["caveats"])
        # The stub binder in use really is the default stub.
        self.assertIsInstance(self.binder._image_screener,
                              NotEvaluatedImageScreener)

    def test_require_image_verdict_refuses_stub(self):
        binder = self._make_binder(require_image_verdict=True)
        image = Artifact(
            artifact_id="invoice-img",
            kind="invoice_image",
            descriptor={"image_ref": "mem://invoice.png",
                        "image_sha256": "ab" * 32})
        with self.assertRaises(BindingRefused) as ctx:
            binder.create_binding(
                _intent(artifacts=[_cart(), _invoice(), image]))
        self.assertIn(RC_SCREEN_NOT_EVALUATED, ctx.exception.reason_codes)

    def test_flagged_image_prevents_creation(self):
        bad_bytes = b"invoice image with a flagged wallet"
        bad_hash = hashlib.sha256(bad_bytes).hexdigest()
        binder = self._make_binder(
            image_screener=FakeImageScreener(bad_hashes={bad_hash}))
        image = Artifact(
            artifact_id="invoice-img",
            kind="invoice_image",
            descriptor={"image_ref": "mem://invoice.png",
                        "image_sha256": bad_hash},
            content_bytes=bad_bytes)
        with self.assertRaises(BindingRefused) as ctx:
            binder.create_binding(
                _intent(artifacts=[_cart(), _invoice(), image]))
        self.assertIn(RC_INVOICE_IMAGE_FLAGGED, ctx.exception.reason_codes)


# ---------------------------------------------------------------------------
# v2: OCR invoice-image screening.
# ---------------------------------------------------------------------------

# What the honest invoice image renders: agrees with _invoice() and
# the default intent on total ($25.00) and payee (seller.example).
GOOD_OCR = (
    "INVOICE INV-100\n"
    "Seller Example LLC\n"
    "seller.example\n"
    "Widget x1  25.00\n"
    "Total due: $25.00\n"
    "Pay to: seller.example\n"
)

# A substituted image: same invoice number on its face, but the
# rendered total is 100x the bound amount and payment is directed
# to a wallet that appears in no bound artifact.
SUBSTITUTED_OCR = (
    "INVOICE INV-100\n"
    "Seller Example LLC\n"
    "Total due: $2,500.00\n"
    "Pay instantly to wallet "
    "0x1111111111111111111111111111111111111111\n"
)

# Only the total diverges; the payee is the bound seller.
HIGH_TOTAL_OCR = GOOD_OCR.replace("$25.00", "$2,500.00")


def _ocr_unavailable(_image_bytes):
    raise OCRUnavailableError("no OCR engine in test")


def _image_artifact(image_bytes=b"fake invoice image bytes"):
    return Artifact(
        artifact_id="invoice-img",
        kind="invoice_image",
        descriptor={
            "image_ref": "mem://invoice.png",
            "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
        },
        content_bytes=image_bytes)


def _ocr_screener(text=None, extractor=None):
    if extractor is None:
        extractor = FunctionTextExtractor(lambda _b: text or "")
    return OcrInvoiceImageScreener(extractor)


class _V2BinderMixin:
    """Shared scaffolding for the v2 test classes."""

    def setUp(self):
        self.clock = FakeClock()
        self.signer = Ed25519Signer(TEST_SEED_HEX)
        self.store = InMemoryBindingStore()

    def _binder(self, **kwargs):
        kwargs.setdefault("now_fn", self.clock)
        kwargs.setdefault("store", self.store)
        kwargs.setdefault("counterparty_screener",
                          FakeCounterpartyScreener())
        kwargs.setdefault("artifact_screener", FakeArtifactScreener())
        return IntentBinder(self.signer, **kwargs)

    def _intent_with_image(self, image=None, **overrides):
        image = image if image is not None else _image_artifact()
        overrides.setdefault(
            "artifacts", [_cart(), _invoice(), image])
        return _intent(**overrides)


class OcrImageScreeningTests(_V2BinderMixin, unittest.TestCase):

    def test_ocr_matching_image_passes_and_settles(self):
        binder = self._binder(image_screener=_ocr_screener(GOOD_OCR))
        binding = binder.create_binding(self._intent_with_image())
        verdict = \
            binding.record["verdicts"]["invoice_images"]["invoice-img"]
        self.assertEqual(verdict["status"], "no_flags_found")
        self.assertFalse(verdict["advisory"])
        self.assertFalse(binding.record["step_up"]["required"])
        image = _image_artifact()
        decision = binder.verify_at_settlement(
            binding,
            _executed(artifacts=[_cart(), _invoice(), image]))
        self.assertTrue(decision.allowed)

    def test_ocr_substituted_image_flags_advisory_step_up(self):
        binder = self._binder(
            image_screener=_ocr_screener(SUBSTITUTED_OCR))
        # Advisory posture: creation is NOT refused.
        binding = binder.create_binding(self._intent_with_image())
        verdict = \
            binding.record["verdicts"]["invoice_images"]["invoice-img"]
        self.assertEqual(verdict["status"], "flagged")
        self.assertTrue(verdict["advisory"])
        step_up = binding.record["step_up"]
        self.assertTrue(step_up["required"])
        trigger_types = [t["type"] for t in step_up["triggers"]]
        self.assertIn("invoice_image_advisory", trigger_types)
        # Decided 2026-10-24: settle-check validates step-up
        # attestations. Without evidence the settlement blocks (and
        # does not consume); with a valid attestation for the
        # required method it allows.
        image = _image_artifact()
        executed = _executed(artifacts=[_cart(), _invoice(), image])
        decision = binder.verify_at_settlement(binding, executed)
        self.assertFalse(decision.allowed)
        self.assertIn("STEP_UP_ATTESTATION_MISSING",
                      decision.reason_codes)
        attestation = {
            "method": "human_approval",
            "evidence_ref": "https://approvals.example/records/appr-1001",
            "attested_at": binding.record["issued_at"],
            "attestor": "approver-7",
        }
        decision = binder.verify_at_settlement(
            binding, executed, attestations=[attestation])
        self.assertTrue(decision.allowed, decision)

    def test_ocr_totals_mismatch_flags_advisory(self):
        binder = self._binder(
            image_screener=_ocr_screener(HIGH_TOTAL_OCR))
        binding = binder.create_binding(self._intent_with_image())
        verdict = \
            binding.record["verdicts"]["invoice_images"]["invoice-img"]
        self.assertEqual(verdict["status"], "flagged")
        self.assertTrue(verdict["advisory"])
        self.assertTrue(any("total" in r for r in verdict["reasons"]))

    def test_ocr_unavailable_records_not_evaluated(self):
        screener = _ocr_screener(
            extractor=FunctionTextExtractor(_ocr_unavailable))
        binder = self._binder(image_screener=screener)
        binding = binder.create_binding(self._intent_with_image())
        verdict = \
            binding.record["verdicts"]["invoice_images"]["invoice-img"]
        self.assertEqual(verdict["status"], "not_evaluated")
        # Default policy: unevaluated OCR is a caveat, not a
        # step-up trigger.
        self.assertFalse(binding.record["step_up"]["required"])

    def test_ocr_unavailable_with_require_image_verdict_refuses(self):
        screener = _ocr_screener(
            extractor=FunctionTextExtractor(_ocr_unavailable))
        binder = self._binder(image_screener=screener,
                              require_image_verdict=True)
        with self.assertRaises(BindingRefused) as ctx:
            binder.create_binding(self._intent_with_image())
        self.assertIn(RC_SCREEN_NOT_EVALUATED,
                      ctx.exception.reason_codes)

    def test_ocr_advisory_refuses_under_hard_block_policy(self):
        policy = BindingPolicy.from_dict(
            {"binding": {"image_ocr": {"hard_block": True}}})
        binder = self._binder(
            image_screener=_ocr_screener(SUBSTITUTED_OCR),
            policy=policy)
        with self.assertRaises(BindingRefused) as ctx:
            binder.create_binding(self._intent_with_image())
        self.assertIn(RC_INVOICE_IMAGE_FLAGGED,
                      ctx.exception.reason_codes)

    def test_ocr_image_without_bytes_not_evaluated(self):
        image = _image_artifact()
        image.content_bytes = None
        binder = self._binder(image_screener=_ocr_screener(GOOD_OCR))
        binding = binder.create_binding(
            self._intent_with_image(image=image))
        verdict = \
            binding.record["verdicts"]["invoice_images"]["invoice-img"]
        self.assertEqual(verdict["status"], "not_evaluated")

    def test_ocr_no_readable_text_is_advisory(self):
        binder = self._binder(image_screener=_ocr_screener("  \n "))
        binding = binder.create_binding(self._intent_with_image())
        verdict = \
            binding.record["verdicts"]["invoice_images"]["invoice-img"]
        self.assertEqual(verdict["status"], "flagged")
        self.assertTrue(verdict["advisory"])
        self.assertTrue(binding.record["step_up"]["required"])

    def test_tesseract_extractor_availability_contract(self):
        extractor = TesseractTextExtractor()
        if not TesseractTextExtractor.available():
            # This sandbox has no tesseract binary and no
            # pytesseract: the extractor must say so, loudly.
            with self.assertRaises(OCRUnavailableError):
                extractor.extract_text(b"\x89PNG fake bytes")
        else:
            try:
                import io

                from PIL import Image
                buf = io.BytesIO()
                Image.new("RGB", (120, 40), "white").save(
                    buf, format="PNG")
                png = buf.getvalue()
            except ImportError:
                self.skipTest("Pillow unavailable for a probe image")
            self.assertIsInstance(extractor.extract_text(png), str)


# ---------------------------------------------------------------------------
# v2: YAML policy.
# ---------------------------------------------------------------------------

class PolicyTests(_V2BinderMixin, unittest.TestCase):

    def test_policy_defaults_match_v1_constants(self):
        policy = BindingPolicy()
        self.assertEqual(policy.ttl_seconds, 900)
        self.assertEqual(policy.amount_tolerance_minor, 0)
        self.assertEqual(policy.amount_tolerance_bps, 0)
        self.assertFalse(policy.require_image_verdict)
        self.assertFalse(policy.allow_unevaluated)
        self.assertFalse(policy.image_ocr_hard_block)
        self.assertEqual(policy.step_up_satisfied_by,
                         ("human_approval",))
        self.assertIsNone(policy.step_up_amount_minor_at_or_above)
        self.assertFalse(policy.step_up_on_image_unevaluated)

    def test_policy_from_dict_full_shape(self):
        policy = BindingPolicy.from_dict({"binding": {
            "ttl_seconds": 3600,
            "amount_tolerance": {"minor": 50, "bps": 25},
            "screening": {"require_image_verdict": True,
                          "allow_unevaluated": True},
            "image_ocr": {"hard_block": True},
            "step_up": {
                "satisfied_by": ["human_approval", "amount_cap"],
                "amount_minor_at_or_above": 100000,
                "on_image_unevaluated": True},
        }})
        self.assertEqual(policy.ttl_seconds, 3600)
        self.assertEqual(policy.amount_tolerance_minor, 50)
        self.assertEqual(policy.amount_tolerance_bps, 25)
        self.assertTrue(policy.require_image_verdict)
        self.assertTrue(policy.allow_unevaluated)
        self.assertTrue(policy.image_ocr_hard_block)
        self.assertEqual(policy.step_up_satisfied_by,
                         ("human_approval", "amount_cap"))
        self.assertEqual(policy.step_up_amount_minor_at_or_above,
                         100000)
        self.assertTrue(policy.step_up_on_image_unevaluated)

    def test_policy_from_yaml_text_and_file(self):
        text = (
            "binding:\n"
            "  ttl_seconds: 120\n"
            "  amount_tolerance:\n"
            "    minor: 10\n"
            "  step_up:\n"
            "    amount_minor_at_or_above: 5000\n")
        policy = BindingPolicy.from_yaml_text(text)
        self.assertEqual(policy.ttl_seconds, 120)
        self.assertEqual(policy.amount_tolerance_minor, 10)
        self.assertEqual(policy.step_up_amount_minor_at_or_above,
                         5000)
        with tempfile.NamedTemporaryFile(
                "w", suffix=".yaml", delete=False) as fh:
            fh.write(text)
            path = fh.name
        try:
            from_file = BindingPolicy.load_yaml_file(path)
        finally:
            os.unlink(path)
        self.assertEqual(from_file.ttl_seconds, 120)

    def test_policy_unknown_keys_rejected(self):
        with self.assertRaises(ValueError):
            BindingPolicy.from_dict({"binding": {"ttl_second": 5}})
        with self.assertRaises(ValueError):
            BindingPolicy.from_dict({"surprise": {}})
        with self.assertRaises(ValueError):
            BindingPolicy.from_dict(
                {"binding": {"step_up": {"satisfied": ["x"]}}})

    def test_policy_bad_values_rejected(self):
        with self.assertRaises(ValueError):
            BindingPolicy.from_dict(
                {"binding": {"ttl_seconds": "900"}})
        with self.assertRaises(ValueError):
            BindingPolicy.from_dict(
                {"binding": {"ttl_seconds": 0}})
        with self.assertRaises(ValueError):
            BindingPolicy.from_dict(
                {"binding": {"amount_tolerance": {"bps": 10001}}})
        with self.assertRaises(ValueError):
            BindingPolicy.from_dict(
                {"binding": {"step_up": {"satisfied_by": []}}})
        with self.assertRaises(ValueError):
            BindingPolicy.from_dict(
                {"binding": {"image_ocr": {"hard_block": "yes"}}})

    def test_policy_drives_binder_ttl_and_tolerance(self):
        policy = BindingPolicy.from_dict({"binding": {
            "ttl_seconds": 60,
            "amount_tolerance": {"minor": 100}}})
        binder = self._binder(policy=policy)
        binding = binder.create_binding(_intent())
        self.assertEqual(
            binding.record["expires_at"]
            - binding.record["issued_at"], 60)
        self.clock.advance(61)
        decision = binder.verify_at_settlement(binding, _executed())
        self.assertFalse(decision.allowed)
        self.assertIn(RC_BINDING_EXPIRED, decision.reason_codes)
        # Tolerance from policy: $25.50 settles against $25.00.
        binder2 = self._binder(policy=policy,
                               store=InMemoryBindingStore())
        binding2 = binder2.create_binding(_intent())
        decision2 = binder2.verify_at_settlement(
            binding2, _executed(amount="25.50"))
        self.assertTrue(decision2.allowed)


# ---------------------------------------------------------------------------
# v2: step-up block baked into the signed record.
# ---------------------------------------------------------------------------

class StepUpTests(_V2BinderMixin, unittest.TestCase):

    def test_clean_binding_step_up_not_required(self):
        binder = self._binder()
        binding = binder.create_binding(_intent())
        self.assertEqual(
            binding.record["step_up"],
            {"required": False, "triggers": [],
             "satisfied_by": ["human_approval"]})

    def test_amount_threshold_trigger_baked_in(self):
        policy = BindingPolicy.from_dict({"binding": {
            "step_up": {"amount_minor_at_or_above": 2000}}})
        binder = self._binder(policy=policy)
        binding = binder.create_binding(_intent())  # $25.00 = 2500
        step_up = binding.record["step_up"]
        self.assertTrue(step_up["required"])
        self.assertEqual(step_up["triggers"][0]["type"],
                         "amount_threshold")
        self.assertEqual(step_up["triggers"][0]["threshold_minor"],
                         2000)

    def test_step_up_on_image_unevaluated_policy(self):
        policy = BindingPolicy.from_dict({"binding": {
            "step_up": {"on_image_unevaluated": True}}})
        binder = self._binder(policy=policy)  # default stub screener
        binding = binder.create_binding(self._intent_with_image())
        trigger_types = [t["type"]
                         for t in binding.record["step_up"]["triggers"]]
        self.assertIn("invoice_image_unevaluated", trigger_types)
        self.assertTrue(binding.record["step_up"]["required"])

    def test_step_up_block_is_inside_the_signature(self):
        binder = self._binder(
            image_screener=_ocr_screener(SUBSTITUTED_OCR))
        binding = binder.create_binding(self._intent_with_image())
        self.assertTrue(binding.record["step_up"]["required"])
        forged = Binding.from_dict(copy.deepcopy(binding.to_dict()))
        forged.record["step_up"]["required"] = False
        forged.record["step_up"]["triggers"] = []
        self.assertFalse(forged.signature_valid())
        decision = binder.verify_at_settlement(forged, _executed())
        self.assertFalse(decision.allowed)
        self.assertIn(RC_SIGNATURE_INVALID, decision.reason_codes)


# ---------------------------------------------------------------------------
# v2: per-rail identifier canonicalization.
# ---------------------------------------------------------------------------

class CanonicalizationTests(_V2BinderMixin, unittest.TestCase):

    def test_opaque_policy_preserves_case_and_compares_exactly(self):
        binder = self._binder()
        intent = _intent(counterparty="SellerSvc_ABC", rail="opaque")
        binding = binder.create_binding(intent)
        self.assertEqual(binding.record["id_policy"], "opaque")
        self.assertEqual(binding.record["counterparty_canonical"],
                         "SellerSvc_ABC")
        # Case-folded lookalike is a different opaque id: blocks.
        decision = binder.verify_at_settlement(
            binding, _executed(counterparty="sellersvc_abc"))
        self.assertFalse(decision.allowed)
        self.assertIn(RC_COUNTERPARTY_MISMATCH,
                      decision.reason_codes)
        # Exact id settles.
        decision = binder.verify_at_settlement(
            binding, _executed(counterparty="SellerSvc_ABC"))
        self.assertTrue(decision.allowed)

    def test_unknown_rail_refused_at_creation(self):
        binder = self._binder()
        with self.assertRaises(BindingRefused) as ctx:
            binder.create_binding(_intent(rail="no-such-rail"))
        self.assertIn(RC_INVALID_INTENT, ctx.exception.reason_codes)

    def test_default_policy_recorded_on_binding(self):
        binder = self._binder()
        binding = binder.create_binding(_intent())
        self.assertEqual(binding.record["id_policy"], "default")
        self.assertEqual(binding.record["counterparty_canonical"],
                         "seller.example")


if __name__ == "__main__":
    unittest.main()
