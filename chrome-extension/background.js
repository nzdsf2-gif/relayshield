importScripts("api.js");

const MENU_LINK = "relayshield-check-link";
const MENU_SELECTION = "relayshield-check-selection";

chrome.runtime.onInstalled.addListener(async (details) => {
  chrome.contextMenus.create({
    id: MENU_LINK,
    title: "Check this link with RelayShield",
    contexts: ["link"],
  });
  chrome.contextMenus.create({
    id: MENU_SELECTION,
    title: "Check this with RelayShield",
    contexts: ["selection"],
  });

  // Self-reported install telemetry. Fire-and-forget: a failed ping must
  // never break the install flow. No PII — we send only the event type and
  // extension version, no user identifier.
  if (details.reason === "install") {
    // Prominent disclosure: first-run consent screen per July 2026 store rules.
    const { rsConsent } = await chrome.storage.local.get("rsConsent");
    if (!rsConsent) chrome.tabs.create({ url: chrome.runtime.getURL("consent.html") });
    try {
      await fetch("https://api.relayshield.net/v1/telemetry", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          event_type: "chrome_install",
          version: chrome.runtime.getManifest().version,
        }),
      });
    } catch {}
  }
});

chrome.contextMenus.onClicked.addListener(async (info) => {
  const raw = info.menuItemId === MENU_LINK ? info.linkUrl : info.selectionText;
  if (!raw) return;
  await runCheck(raw);
});

async function runCheck(raw) {
  const { rsConsent } = await chrome.storage.local.get("rsConsent");
  if (!rsConsent) {
    notify("RelayShield needs your OK first",
      "Open the RelayShield popup and accept the data notice to start checking.");
    return;
  }
  let result;
  try {
    // v1.1: the right-click check runs through the composite endpoint -- one
    // call, riskiest signal wins.
    result = await rsCheckCounterparty(raw);
  } catch (err) {
    notify("Could not check that", err.message || String(err));
    return;
  }

  // Stored so the popup shows the last result if opened right after a
  // context-menu check -- a context menu has no surface of its own to
  // render a verdict into beyond a system notification.
  await chrome.storage.session.set({
    rsLastResult: { ...result, checkedAt: Date.now() },
  });

  const levelLabel = {
    high: "⚠️ FLAGGED",
    medium: "⚠️ Caution",
    low: "Low risk",
    unknown: "Nothing known against it",
  }[result.level] || result.level;

  const bodyLines = result.reasons.length
    ? result.reasons.join("\n")
    : "No flags in RelayShield's corpus, Safe Browsing, or (for links) domain age. Absence of evidence is not proof of safety.";

  notify(`${levelLabel}: ${truncate(result.target, 60)}`, bodyLines);
}

function notify(title, message) {
  chrome.notifications.create({
    type: "basic",
    iconUrl: "icons/icon128.png",
    title,
    message,
    priority: 1,
  });
}

function truncate(s, n) {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}
