const input = document.getElementById("input");
const checkBtn = document.getElementById("check");
const resultEl = document.getElementById("result");
const errorEl = document.getElementById("error");
const apiKeyLink = document.getElementById("apikey");

apiKeyLink.href = `${RS_API_BASE}/developers?source=${RS_SOURCE}`;

// If a context-menu check ran right before the popup opened, show it rather
// than an empty box -- the user just asked a question and the answer exists.
chrome.storage.session.get("rsLastResult", ({ rsLastResult }) => {
  if (rsLastResult && Date.now() - rsLastResult.checkedAt < 30_000) {
    input.value = rsLastResult.target;
    render(rsLastResult);
  }
});

checkBtn.addEventListener("click", () => runCheck());
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) runCheck();
});

async function runCheck() {
  hide(resultEl);
  hide(errorEl);
  checkBtn.disabled = true;
  checkBtn.textContent = "Checking…";
  try {
    const result = await rsCheckAny(input.value);
    render(result);
  } catch (err) {
    errorEl.textContent = err.message || String(err);
    show(errorEl);
  } finally {
    checkBtn.disabled = false;
    checkBtn.textContent = "Check";
  }
}

function render(result) {
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

function show(el) { el.classList.add("show"); }
function hide(el) { el.classList.remove("show"); }

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}
