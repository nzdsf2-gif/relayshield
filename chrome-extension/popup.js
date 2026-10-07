const input = document.getElementById("input");
const checkBtn = document.getElementById("check");
const emailFrom = document.getElementById("email-from");
const emailSubject = document.getElementById("email-subject");
const emailBody = document.getElementById("email-body");
const checkEmailBtn = document.getElementById("check-email");
const resultEl = document.getElementById("result");
const errorEl = document.getElementById("error");
const apiKeyLink = document.getElementById("apikey");
const shareGenericBtn = document.getElementById("share-generic");

apiKeyLink.href = `${RS_API_BASE}/developers?source=${RS_SOURCE}`;

// Decoupled from any specific check result -- somebody who just likes the
// extension has nothing to reference, and shouldn't have to run a check
// first to get something worth sending a friend.
shareGenericBtn.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(rsGenericShareText());
    const original = shareGenericBtn.textContent;
    shareGenericBtn.textContent = "Copied — paste it anywhere";
    setTimeout(() => { shareGenericBtn.textContent = original; }, 2000);
  } catch {
    shareGenericBtn.textContent = "Couldn't copy — try again";
  }
});

// Tabs. Two independent forms sharing one result/error area below them.
document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`panel-${btn.dataset.tab}`).classList.add("active");
    hide(resultEl);
    hide(errorEl);
  });
});

// If a context-menu check ran right before the popup opened, show it rather
// than an empty box -- the user just asked a question and the answer exists.
chrome.storage.session.get("rsLastResult", ({ rsLastResult }) => {
  if (rsLastResult && Date.now() - rsLastResult.checkedAt < 30_000) {
    input.value = rsLastResult.target;
    renderLinkOrWallet(rsLastResult);
  }
});

checkBtn.addEventListener("click", () => runLinkOrWalletCheck());
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) runLinkOrWalletCheck();
});
checkEmailBtn.addEventListener("click", () => runEmailCheck());

async function runLinkOrWalletCheck() {
  hide(resultEl);
  hide(errorEl);
  checkBtn.disabled = true;
  checkBtn.textContent = "Checking…";
  try {
    // v1.1: one composite call replaces the per-kind checks.
    const result = await rsCheckCounterparty(input.value);
    renderLinkOrWallet(result);
  } catch (err) {
    errorEl.textContent = err.message || String(err);
    show(errorEl);
  } finally {
    checkBtn.disabled = false;
    checkBtn.textContent = "Check";
  }
}

async function runEmailCheck() {
  hide(resultEl);
  hide(errorEl);
  checkEmailBtn.disabled = true;
  checkEmailBtn.textContent = "Checking…";
  try {
    const data = await rsCheckEmail({
      fromAddress: emailFrom.value.trim(),
      subject: emailSubject.value.trim(),
      bodyText: emailBody.value.trim(),
    });
    renderEmail(data);
  } catch (err) {
    errorEl.textContent = err.message || String(err);
    show(errorEl);
  } finally {
    checkEmailBtn.disabled = false;
    checkEmailBtn.textContent = "Check email";
  }
}

// One share button markup, reused by both render paths, and one delegated
// click handler below -- innerHTML is replaced wholesale on every check, so
// a listener bound to the button itself would be destroyed with it.
const SHARE_BTN_HTML = '<button class="share" data-share="1">Share this check</button>';

function renderLinkOrWallet(result) {
  const labels = {
    high: "⚠️ Flagged",
    medium: "⚠️ Caution — recently registered",
    low: "Low risk",
    unknown: "Nothing known against it",
  };
  const label = labels[result.level] || result.level;
  // v1.1: the composite endpoint returns a 0-100 risk score alongside the
  // level -- surface it so a "caution" with score 55 reads differently from
  // one with score 95.
  const scoreHtml = typeof result.score === "number"
    ? `<div class="note">Composite risk score: ${result.score}/100</div>`
    : "";
  const reasonsHtml = result.reasons.length
    ? `<ul>${result.reasons.map((r) => `<li>${escapeHtml(r)}</li>`).join("")}</ul>`
    : "";
  // Never renders as "safe": the ceiling on a clean result is "nothing known
  // against it", matching the API's own note field.
  const noteHtml = !result.reasons.length
    ? '<div class="note">Absence of flags is not proof of safety.</div>'
    : "";
  // A URL like a Jupiter/Solscan/Etherscan page carries the actual on-chain
  // address in its own path -- say so explicitly, even on a clean result, so
  // "nothing known against it" reads as "checked both", not "only checked
  // the domain and never looked at the token."
  const embeddedHtml = result.embeddedAddress
    ? `<div class="note">Also checked the ${result.embeddedChain.toUpperCase()} address in this URL: ${escapeHtml(result.embeddedAddress)}</div>`
    : "";
  resultEl.innerHTML =
    `<div class="level ${result.level}">${label}</div>${scoreHtml}${reasonsHtml}${noteHtml}${embeddedHtml}${SHARE_BTN_HTML}`;
  // The link/address itself is already public (it's what was just pasted or
  // right-clicked), so it's fine to include in what gets shared -- unlike an
  // email's content below, which is never put in a share message.
  resultEl.dataset.shareText = rsShareText(result.target);
  show(resultEl);
}

function renderEmail(data) {
  // /v1/email-check's own floor is "low", never "unknown" -- a different
  // scoring model from the link/wallet endpoints, matched here rather than
  // forced into the same three labels those use.
  const labels = { high: "⚠️ Likely phishing", medium: "⚠️ Some red flags", low: "No strong signals found" };
  const label = labels[data.risk] || data.risk;
  const flagsHtml = (data.flags || []).length
    ? `<ul>${data.flags.map((f) => `<li>${escapeHtml(f)}</li>`).join("")}</ul>`
    : "";
  const flaggedLinks = (data.links || []).filter((l) => l.flagged);
  const linksHtml = flaggedLinks.length
    ? `<div class="note">${flaggedLinks.length} link(s) in the body are separately flagged.</div>`
    : "";
  const noteHtml = !(data.flags || []).length
    ? '<div class="note">Absence of flags is not proof this email is safe.</div>'
    : "";
  resultEl.innerHTML =
    `<div class="level ${data.risk}">${label}</div>${flagsHtml}${linksHtml}${noteHtml}${SHARE_BTN_HTML}`;
  // Never include the pasted sender/subject/body in a share message -- that
  // content is the user's own inbox, not something to copy into a message to
  // a friend on their behalf.
  resultEl.dataset.shareText = rsShareText("a suspicious email");
  show(resultEl);
}

// Delegated: bound once to the container, works for every re-render.
resultEl.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-share]");
  if (!btn) return;
  try {
    await navigator.clipboard.writeText(resultEl.dataset.shareText || "");
    const original = btn.textContent;
    btn.textContent = "Copied — paste it anywhere";
    setTimeout(() => { btn.textContent = original; }, 2000);
  } catch (err) {
    btn.textContent = "Couldn't copy — select and copy manually";
  }
});

function show(el) { el.classList.add("show"); }
function hide(el) { el.classList.remove("show"); }

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

// Block all checks until the user has accepted the first-run data notice.
chrome.storage.local.get("rsConsent", ({ rsConsent }) => {
  if (rsConsent) return;
  const gate = document.createElement("div");
  gate.style.cssText = "position:fixed;inset:0;background:#17212b;z-index:50;padding:32px 24px;display:flex;flex-direction:column;justify-content:center;gap:12px;";
  gate.innerHTML =
    '<h1 style="font-size:16px;margin:0;">One quick step first</h1>' +
    '<p style="font-size:13px;color:#9aa7b0;margin:0;">RelayShield needs your agreement on how checked links, selections, and pasted email text are used before it can run any checks.</p>' +
    '<button id="rs-open-consent" style="padding:10px;border:0;border-radius:8px;background:#3b82f6;color:#fff;font-size:14px;font-weight:600;cursor:pointer;">Review the data notice</button>';
  document.body.appendChild(gate);
  document.getElementById("rs-open-consent").addEventListener("click", () => {
    chrome.tabs.create({ url: chrome.runtime.getURL("consent.html") });
  });
});

