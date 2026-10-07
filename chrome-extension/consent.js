// First-run prominent disclosure for RelayShield Chrome extension.
// Records explicit consent in chrome.storage.local under "rsConsent".
// Bump CONSENT_VERSION when data practices change and re-prompt on update.

const CONSENT_VERSION = 1;

document.getElementById("agree").addEventListener("click", async () => {
  await chrome.storage.local.set({ rsConsent: { v: CONSENT_VERSION, ts: Date.now() } });
  window.close();
});

document.getElementById("decline").addEventListener("click", () => {
  document.getElementById("main").style.display = "none";
  document.getElementById("declined").style.display = "block";
});
