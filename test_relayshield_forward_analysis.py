"""Tests for the shared forward-analysis core.

The properties under test are the ones that would produce a WRONG STATEMENT TO
A USER if they regressed, not the ones that are merely convenient:

  * WhatsApp must never claim a sender. There is none in the payload, and a
    reply that implies one was checked is worse than no reply.
  * Telegram's hidden_user must not be treated as identifiable. A display name
    is a string the sender chose; using it as a lookup key, or wording the
    reply as though it identified anyone, is the same error in a subtler form.
  * A below-threshold operator hit must produce SILENCE, not softer wording.
    The table is a lead list built from a loose @mention regex, and a hedged
    accusation about a named third party is still an accusation.
  * A lookup that ERRORED must never render as "not found".
  * Names from the platform are attacker-controlled and must be escaped, or a
    display name containing an underscore takes the whole verdict down with a
    Telegram 400.

Imports the module directly: it holds no platform SDK and builds its boto3
handle lazily, so importing it costs nothing and every test here injects its
own lookup rather than touching AWS.

    python3 -m unittest test_relayshield_forward_analysis -v
"""

import unittest

import relayshield_forward_analysis as fwd


def _tg(origin: dict) -> dict:
    return {"message_id": 1, "text": "hello", "forward_origin": origin}


class TestTelegramParsing(unittest.TestCase):

    def test_not_a_forward_returns_none(self):
        self.assertIsNone(fwd.parse_telegram_forward({"text": "hello"}))
        self.assertIsNone(fwd.parse_telegram_forward({}))

    def test_user_origin_is_identifiable(self):
        o = fwd.parse_telegram_forward(_tg({
            "type": "user",
            "date": 1735689600,
            "sender_user": {"id": 42, "first_name": "Alice", "last_name": "Ng",
                            "username": "AliceNg"},
        }))
        self.assertEqual(o.origin_type, fwd.ORIGIN_USER)
        self.assertEqual(o.sender_id, "42")
        # Normalised to the form relayshield_operator_identities is keyed on.
        self.assertEqual(o.sender_username, "aliceng")
        self.assertEqual(o.sender_display_name, "Alice Ng")
        self.assertTrue(o.sender_identifiable)
        self.assertEqual(o.attribution, fwd.ATTR_SENDER_KNOWN)

    def test_hidden_user_is_not_identifiable(self):
        """Forward privacy on. Telegram gives a display name and nothing else."""
        o = fwd.parse_telegram_forward(_tg({
            "type": "hidden_user", "date": 1, "sender_user_name": "Alice",
        }))
        self.assertEqual(o.sender_display_name, "Alice")
        self.assertIsNone(o.sender_id)
        # The name must NOT be promoted into the lookup-key field.
        self.assertIsNone(o.sender_username)
        self.assertFalse(o.sender_identifiable)
        self.assertEqual(o.attribution, fwd.ATTR_SENDER_HIDDEN)

    def test_channel_origin(self):
        o = fwd.parse_telegram_forward(_tg({
            "type": "channel", "date": 1, "message_id": 7,
            "chat": {"id": -100, "title": "Airdrop News", "username": "airdropnews"},
        }))
        self.assertEqual(o.attribution, fwd.ATTR_CHANNEL)
        self.assertEqual(o.origin_title, "Airdrop News")
        self.assertFalse(o.sender_identifiable)

    def test_unknown_origin_type_is_still_a_forward(self):
        """A type Telegram adds later must not silently stop being a forward."""
        o = fwd.parse_telegram_forward(_tg({"type": "something_new", "date": 1}))
        self.assertIsNotNone(o)
        self.assertEqual(o.origin_type, fwd.ORIGIN_UNATTRIBUTED)
        self.assertFalse(o.sender_identifiable)

    def test_legacy_pre_bot_api_7_fields(self):
        o = fwd.parse_telegram_forward({
            "text": "x",
            "forward_from": {"id": 9, "first_name": "Bob", "username": "bobbb"},
            "forward_date": 123,
        })
        self.assertEqual(o.sender_username, "bobbb")
        self.assertTrue(o.sender_identifiable)

    def test_junk_username_is_not_a_lookup_key(self):
        """A username that is not username-shaped must not become a query key."""
        o = fwd.parse_telegram_forward(_tg({
            "type": "user", "date": 1,
            "sender_user": {"id": 1, "first_name": "X", "username": "a b c"},
        }))
        self.assertIsNone(o.sender_username)


class TestWhatsAppParsing(unittest.TestCase):

    def test_not_a_forward_returns_none(self):
        self.assertIsNone(fwd.parse_whatsapp_forward({"Body": "hello"}))
        self.assertIsNone(fwd.parse_whatsapp_forward({}))

    def test_forwarded_true(self):
        o = fwd.parse_whatsapp_forward({"Forwarded": "true"})
        self.assertEqual(o.platform, fwd.PLATFORM_WHATSAPP)
        self.assertFalse(o.frequently_forwarded)

    def test_the_string_false_is_false(self):
        """Twilio sends STRINGS. A truthiness test on "false" would be True."""
        self.assertIsNone(fwd.parse_whatsapp_forward({"Forwarded": "false"}))

    def test_case_insensitive(self):
        self.assertIsNotNone(fwd.parse_whatsapp_forward({"Forwarded": "True"}))

    def test_frequently_forwarded_alone_still_counts(self):
        o = fwd.parse_whatsapp_forward({"FrequentlyForwarded": "true"})
        self.assertIsNotNone(o)
        self.assertTrue(o.frequently_forwarded)

    def test_cloud_api_shape(self):
        o = fwd.parse_whatsapp_forward({"context": {"frequently_forwarded": True}})
        self.assertIsNotNone(o)
        self.assertTrue(o.frequently_forwarded)

    def test_whatsapp_never_carries_a_sender(self):
        """The core invariant. No WhatsApp payload can produce a sender."""
        for params in ({"Forwarded": "true"},
                       {"FrequentlyForwarded": "true"},
                       {"Forwarded": "true", "From": "whatsapp:+15551234567",
                        "ProfileName": "Alice"}):
            o = fwd.parse_whatsapp_forward(params)
            self.assertIsNone(o.sender_id)
            self.assertIsNone(o.sender_username)
            self.assertIsNone(o.sender_display_name)
            self.assertFalse(o.sender_identifiable)
            self.assertEqual(o.attribution, fwd.ATTR_PLATFORM_BLIND)


class TestAnalyze(unittest.TestCase):

    def _known_sender(self, username="scammer1"):
        return fwd.ForwardOrigin(
            platform=fwd.PLATFORM_TELEGRAM, origin_type=fwd.ORIGIN_USER,
            sender_id="1", sender_username=username, sender_display_name="A",
        )

    def test_no_lookup_runs_for_whatsapp(self):
        calls = []
        o = fwd.parse_whatsapp_forward({"Forwarded": "true"})
        f = fwd.analyze_forward(o, operator_lookup=lambda h: calls.append(h))
        self.assertEqual(calls, [])
        self.assertFalse(f.sender_checked)
        self.assertEqual(f.leads, [])

    def test_no_lookup_runs_for_hidden_user(self):
        calls = []
        o = fwd.ForwardOrigin(platform=fwd.PLATFORM_TELEGRAM,
                              origin_type=fwd.ORIGIN_HIDDEN_USER,
                              sender_display_name="Alice")
        fwd.analyze_forward(o, operator_lookup=lambda h: calls.append(h))
        self.assertEqual(calls, [])

    def test_lookup_uses_the_normalised_handle(self):
        seen = []

        def lookup(handle):
            seen.append(handle)
            return None

        fwd.analyze_forward(self._known_sender("scammer1"), operator_lookup=lookup)
        self.assertEqual(seen, ["scammer1"])

    def test_below_threshold_hit_is_silent(self):
        """A single sighting in a single channel says NOTHING to the user.

        This is the A8 corroboration rule applied at the point of consumption.
        The table really does contain ordinary English words caught by a loose
        @mention regex; one of those must never become an accusation.
        """
        row = {"sightings": 1, "channels": {"chan_a"}, "categories": {"phaas"}}
        f = fwd.analyze_forward(self._known_sender(), operator_lookup=lambda h: row)
        self.assertTrue(f.sender_checked)
        self.assertEqual(f.leads, [])
        self.assertNotIn("phaas", fwd.render_forward_note(f))

    def test_one_channel_many_sightings_is_still_silent(self):
        """Repetition inside ONE channel is not corroboration."""
        row = {"sightings": 9, "channels": {"chan_a"}, "categories": set()}
        f = fwd.analyze_forward(self._known_sender(), operator_lookup=lambda h: row)
        self.assertEqual(f.leads, [])

    def test_corroborated_hit_surfaces_as_a_lead(self):
        row = {"sightings": 4, "channels": {"chan_a", "chan_b"},
               "categories": {"phaas", "ransomware"}}
        f = fwd.analyze_forward(self._known_sender(), operator_lookup=lambda h: row)
        self.assertEqual(len(f.leads), 1)
        self.assertEqual(f.leads[0].sightings, 4)
        self.assertEqual(f.leads[0].channels, 2)
        note = fwd.render_forward_note(f)
        self.assertIn("lead, not proof", note)

    def test_failed_lookup_does_not_read_as_clean(self):
        """An errored check is not a passed check."""
        def boom(handle):
            raise RuntimeError("DynamoDB unavailable")

        f = fwd.analyze_forward(self._known_sender(), operator_lookup=boom)
        self.assertTrue(f.lookup_failed)
        self.assertFalse(f.sender_checked)
        note = fwd.render_forward_note(f)
        self.assertNotIn("has not come up", note)


class TestRendering(unittest.TestCase):

    def test_whatsapp_note_says_it_cannot_identify_the_sender(self):
        """The honest-limits sentence is the whole point of the WA branch."""
        o = fwd.parse_whatsapp_forward({"Forwarded": "true"})
        note = fwd.render_forward_note(fwd.analyze_forward(o, operator_lookup=lambda h: None))
        self.assertIn("not who originally", note)
        self.assertIn("no account for me to check", note)

    def test_whatsapp_note_never_claims_a_check_happened(self):
        o = fwd.parse_whatsapp_forward({"Forwarded": "true"})
        note = fwd.render_forward_note(fwd.analyze_forward(o, operator_lookup=lambda h: None))
        self.assertNotIn("has not come up in the criminal channels", note)

    def test_frequently_forwarded_is_called_out(self):
        o = fwd.parse_whatsapp_forward({"FrequentlyForwarded": "true"})
        note = fwd.render_forward_note(fwd.analyze_forward(o))
        self.assertIn("frequently forwarded", note)

    def test_clean_telegram_sender_is_not_reported_as_safe(self):
        o = fwd.ForwardOrigin(platform=fwd.PLATFORM_TELEGRAM,
                              origin_type=fwd.ORIGIN_USER,
                              sender_id="1", sender_username="alice",
                              sender_display_name="Alice")
        note = fwd.render_forward_note(fwd.analyze_forward(o, operator_lookup=lambda h: None))
        self.assertIn("not a clean bill of health", note)

    def test_markdown_is_escaped_in_platform_supplied_names(self):
        """A username with an underscore must not break Telegram's parser.

        Unescaped, `@john_doe` leaves an unclosed italic entity, Telegram
        answers 400, and the ENTIRE reply is dropped -- verdict included. That
        is a denial of the answer the user needed, triggerable by the scammer
        simply choosing their own display name.
        """
        o = fwd.ForwardOrigin(platform=fwd.PLATFORM_TELEGRAM,
                              origin_type=fwd.ORIGIN_USER,
                              sender_id="1", sender_username="john_doe",
                              sender_display_name="John *Doe* [x]")
        note = fwd.render_forward_note(fwd.analyze_forward(o, operator_lookup=lambda h: None))
        self.assertIn("john\\_doe", note)
        self.assertIn("\\*Doe\\*", note)
        self.assertIn("\\[x]", note)

    def test_platform_command_vocabulary(self):
        tg = fwd.render_forward_note(fwd.analyze_forward(
            fwd.ForwardOrigin(platform=fwd.PLATFORM_TELEGRAM,
                              origin_type=fwd.ORIGIN_HIDDEN_USER)))
        wa = fwd.render_forward_note(fwd.analyze_forward(
            fwd.parse_whatsapp_forward({"Forwarded": "true"})))
        self.assertIn("/scan", tg)
        self.assertIn("*SCAN*", wa)
        self.assertNotIn("/scan", wa)


class TestQuickstart(unittest.TestCase):
    """The three hints the founder asked for, pinned.

    The first version of this card shipped with the forward hint only: no
    screenshot hint at all, and nothing about messages from known contacts.
    A capability users are never told about does not exist, so these assertions
    are on the copy itself rather than on any behaviour behind it.
    """

    def test_forwarding_is_the_first_action_on_both(self):
        for platform in (fwd.PLATFORM_TELEGRAM, fwd.PLATFORM_WHATSAPP):
            text = fwd.quickstart_text(platform)
            self.assertIn("Forward me anything that looks off", text)
            self.assertLess(text.index("Forward me anything"),
                            text.index("screenshot"))

    def test_screenshot_hint_is_present_on_both(self):
        for platform in (fwd.PLATFORM_TELEGRAM, fwd.PLATFORM_WHATSAPP):
            text = fwd.quickstart_text(platform)
            self.assertIn("screenshot of a suspicious text", text)

    def test_contacts_hint_is_present_on_both(self):
        """A hijacked contact is the case the user is least able to judge."""
        for platform in (fwd.PLATFORM_TELEGRAM, fwd.PLATFORM_WHATSAPP):
            text = fwd.quickstart_text(platform)
            self.assertIn("in your contacts", text)
            self.assertIn("still shows up as your friend", text)

    def test_telegram_names_the_bot(self):
        """Escaped, because send_message parses Markdown and a lone _ opens an
        italic entity that never closes -- a 400 that drops the whole card."""
        self.assertIn("@relayshield\\_bot", fwd.quickstart_text(fwd.PLATFORM_TELEGRAM))

    def test_both_say_HOW_to_forward(self):
        """"Forward me" is not an instruction if the reader does not know the
        gesture or the destination. Telegram needs the handle to search for;
        WhatsApp has no handle, so it needs the gesture and "this chat"."""
        tg = fwd.quickstart_text(fwd.PLATFORM_TELEGRAM)
        self.assertIn("choose *Forward*", tg)
        self.assertIn("@relayshield\\_bot", tg)
        wa = fwd.quickstart_text(fwd.PLATFORM_WHATSAPP)
        self.assertIn("Press and hold", wa)
        self.assertIn("tap *Forward*", wa)

    def test_whatsapp_quickstart_states_the_limit(self):
        text = fwd.quickstart_text(fwd.PLATFORM_WHATSAPP)
        self.assertIn("does not tell me who originally sent", text)

    def test_telegram_quickstart_does_not_overclaim(self):
        """It may promise a sender check, but only with the privacy caveat."""
        text = fwd.quickstart_text(fwd.PLATFORM_TELEGRAM)
        self.assertIn("forward privacy", text)


class TestHelpCardsCarryTheHints(unittest.TestCase):
    """The hints must be on the surfaces users actually open, not only behind
    /quickstart. Reads the handler sources as text rather than importing them:
    both pull in boto3, and a copy assertion that only runs where boto3 is
    installed is a copy assertion that stops running."""

    def _src(self, name):
        """Source with adjacent string literals JOINED.

        Python concatenates `"a " \n "b"` at compile time, so a phrase wrapped
        across two source lines never appears in the raw text as one string --
        "in your contacts" really is in the WhatsApp help and a naive
        assertIn still failed on it. Collapsing the `" ... "` join here makes
        these assertions test the copy the user sees rather than the line
        wrapping the author happened to choose.
        """
        import re
        from pathlib import Path
        raw = Path(__file__).with_name(name).read_text()
        return re.sub(r'"\s*\n\s*"', "", raw)

    def test_telegram_quick_start_card_has_both_hints(self):
        src = self._src("relayshield_telegram_webhook.py")
        self.assertIn("Forward anything that looks off to @relayshield", src)
        self.assertIn("Paste a screenshot of a suspicious text", src)

    def test_telegram_cards_name_the_bot_escaped(self):
        """All three Telegram surfaces name the handle, and every one of them
        escapes the underscore. One unescaped occurrence is a 400 on that card."""
        src = self._src("relayshield_telegram_webhook.py")
        self.assertGreaterEqual(src.count("@relayshield\\\\_bot"), 3)

    # Asserted as CONCEPTS, not exact sentences. The first version pinned literal
    # copy, so every wording change broke it -- and one such break sat unnoticed
    # through a whole commit. What must not regress is that the surface offers a
    # route needing NO command, not the specific phrasing of it.

    def test_whatsapp_help_offers_a_no_command_route(self):
        src = self._src("relayshield_whatsapp_webhook.py")
        self.assertIn("looks off", src)
        self.assertIn("screenshot of a suspicious text", src)
        self.assertIn("in your contacts", src)

    def test_whatsapp_help_sends_the_hint_before_the_menu(self):
        """HELP used to send ONLY the Twilio menu card, which made every word of
        msg_help() unreachable -- it is shown only by HELPTEXT, behind a button
        on the last menu page. The hint must go first, because the card's own
        text lives in Twilio and cannot be edited from this repo."""
        src = self._src("relayshield_whatsapp_webhook.py")
        block = src[src.index('if body == "HELP":'):]
        block = block[:block.index('return "help_sent"')]
        self.assertIn("paste_hint", block)
        self.assertLess(block.index("paste_hint"), block.index("send_wa_menu"))

    def test_paste_hint_leads_with_pasting_on_both(self):
        """Pasting needs no gesture and no saved contact; forwarding needs both.
        Whichever is named first is the one users will actually try."""
        for platform in (fwd.PLATFORM_TELEGRAM, fwd.PLATFORM_WHATSAPP):
            hint = fwd.paste_hint(platform)
            self.assertIn("paste", hint.lower())
            self.assertIn("do not need a command", hint)


if __name__ == "__main__":
    unittest.main()
