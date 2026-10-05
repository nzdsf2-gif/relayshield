// The WORDS for a free exposure check, kept as a pure function with no React
// Native imports so test_cs_mobile_free_check.py can EXECUTE it under node.
//
// THE RULES THIS FILE EXISTS TO HOLD, each pinned by a test:
//   1. It never says an email is safe. "nothing_known" is the ceiling, because
//      two lookups returning nothing is an absence of evidence.
//   2. A check that did not complete is never worded as a clean one.
//   3. What WAS found is always stated, even when the other half failed.
//   4. "Already used" is a normal state with a way forward, not an error.
import type { FreeExposureResult } from "../api/relayshield";

export type Tone = "found" | "nothing" | "incomplete" | "used";

export interface ExposureView {
  tone: Tone;
  title: string;
  lines: string[];       // facts, one per row
  actions: string[];     // what to do about it (empty when there is nothing to do)
  note: string;          // small print under the card
  cta: string | null;    // the button that leads to the trial, or null
  canRetry: boolean;
}

const SOURCES = "Sources: Have I Been Pwned breach records and Hudson Rock infostealer logs.";

function plural(n: number, one: string, many: string): string {
  return n === 1 ? one : many;
}

function monthYear(iso: string | null | undefined): string {
  if (!iso) return "";
  const m = /^(\d{4})-(\d{2})/.exec(iso);
  return m ? `${m[1]}-${m[2]}` : "";
}

export function exposureView(r: FreeExposureResult): ExposureView {
  if (r.already_used) {
    return {
      tone: "used",
      title: "You've used your free check",
      lines: ["Each install gets one free exposure check."],
      actions: [],
      note: "",
      cta: "Start 7-day free trial",
      canRetry: false,
    };
  }

  const b = r.breach;
  const s = r.infostealer;
  const lines: string[] = [];
  const actions: string[] = [];

  if (b?.checked && (b.count ?? 0) > 0) {
    const n = b.count as number;
    lines.push(`Found in ${n} known data ${plural(n, "breach", "breaches")}.`);
    if (b.names?.length) {
      const more = n - b.names.length;
      lines.push(`${b.names.join(", ")}${more > 0 ? ` and ${more} more` : ""}.`);
    }
    if (b.password_exposed) {
      lines.push("A password tied to this address was exposed in at least one of them.");
    } else if (b.exposed_data?.length) {
      lines.push(`Exposed data: ${b.exposed_data.join(", ")}.`);
    }
  }
  if (s?.checked && s.found) {
    const n = s.count ?? 0;
    const when = monthYear(s.newest);
    lines.push(
      `Found in ${n} infostealer ${plural(n, "log", "logs")}${when ? ` (latest ${when})` : ""}. ` +
      "Malware on a device stole saved logins that included this address.",
    );
  }

  const anyFinding = lines.length > 0;

  if (anyFinding) {
    actions.push("Change the password on any account that used this email, and anywhere you reused it.");
    actions.push("Use a different password for every exchange and wallet account.");
    actions.push("Turn on authenticator-app 2FA, not SMS, for exchange logins.");
    if (s?.checked && s.found) {
      actions.push("Treat the infected device as compromised: scan it, then change passwords from a clean one.");
    }
  }

  // A half-finished check says what it found AND says it is not finished.
  if (r.complete === false || r.level === "incomplete") {
    const missing = [
      b && !b.checked ? "the breach lookup" : "",
      s && !s.checked ? "the infostealer lookup" : "",
    ].filter(Boolean).join(" and ");
    return {
      tone: "incomplete",
      title: anyFinding ? "Partial result: something turned up" : "We couldn't finish this check",
      lines: [
        ...lines,
        `${missing ? missing.charAt(0).toUpperCase() + missing.slice(1) : "A lookup"} didn't complete. ` +
        "Your free check was not used.",
      ],
      actions,
      note: SOURCES,
      cta: null,
      canRetry: true,
    };
  }

  if (anyFinding) {
    return {
      tone: "found",
      title: "Your email turned up",
      lines,
      actions,
      note: SOURCES,
      cta: "Watch this email for new leaks, free for 7 days",
      canRetry: false,
    };
  }

  return {
    tone: "nothing",
    title: "Nothing known against this email",
    lines: [
      "It doesn't appear in the breach records or infostealer logs we checked today.",
      "That is not proof it's safe. New leaks surface every week.",
    ],
    actions: [],
    note: SOURCES,
    cta: "Get alerted if that changes, free for 7 days",
    canRetry: false,
  };
}
