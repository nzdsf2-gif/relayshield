const input = document.getElementById("input");
const checkBtn = document.getElementById("check");
const emailFrom = document.getElementById("email-from");
const emailSubject = document.getElementById("email-subject");
const emailBody = document.getElementById("email-body");
const checkEmailBtn = document.getElementById("check-email");
const resultEl = document.getElementById("result");
const errorEl = document.getElementById("error");
const apiKeyLink = document.getElementById("apikey");

apiKeyLink.href = `${RS_API_BASE}/developers?source=${RS_SOURCE}`;

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
    const result = await rsCheckAny(input.value);
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

function renderLinkOrWallet(result) {
  const labels = {
    high: "⚠️ Flagged",
    medium: "⚠️ Caution — recently registered",
    low: "Low risk",
    unknown: "Nothing known against it",
  };
  const label = labels[result.level] || result.level;
  const reasonsHtml = result.reasons.length
    ? `<ul>${result.reasons.map((r) => `<li>${escapeHtml(r)}</li>`).join("")}</ul>`
    : "";
  // Never renders as "safe": the ceiling on a clean result is "nothing known
  // against it", matching the API's own note field.
  const noteHtml = !result.reasons.length
    ? '<div class="note">Absence of flags is not proof of safety.</div>'
    : "";
  resultEl.innerHTML =
    `<div class="level ${result.level}">${label}</div>${reasonsHtml}${noteHtml}`;
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
    `<div class="level ${data.risk}">${label}</div>${flagsHtml}${linksHtml}${noteHtml}`;
  show(resultEl);
}

function show(el) { el.classList.add("show"); }
function hide(el) { el.classList.remove("show"); }

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}
