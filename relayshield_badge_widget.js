/**
 * CryptoShield by RelayShield — Embeddable Security Badge Widget
 * Version 1.0.0
 *
 * Usage (one line, paste anywhere in your site's HTML):
 *   <script src="https://api.relayshield.net/badge.js?domain=yoursite.com"></script>
 *
 * Optional parameters:
 *   domain   — your protocol's domain (auto-detected if omitted)
 *   style    — "flat" (default) | "compact" | "dark"
 *   position — "inline" (default) | "fixed-bottom-right"
 *   href     — link target when badge is clicked (default: relayshield.net/badge)
 *
 * Example with options:
 *   <script src="https://api.relayshield.net/badge.js?domain=app.yourprotocol.xyz&style=compact&position=fixed-bottom-right"></script>
 */

(function () {
  "use strict";

  // ── Parse script tag parameters ──────────────────────────────────────────
  var scripts = document.querySelectorAll('script[src*="badge.js"]');
  var src     = scripts[scripts.length - 1].src;
  var url     = new URL(src);
  var params  = url.searchParams;

  var domain   = params.get("domain")   || window.location.hostname;
  var style    = params.get("style")    || "flat";
  var position = params.get("position") || "inline";
  var href     = params.get("href")     || "https://relayshield.net/badge?domain=" + encodeURIComponent(domain);

  // ── Badge API endpoint ───────────────────────────────────────────────────
  var API_BASE  = "https://api.relayshield.net";
  var BADGE_API = API_BASE + "/v1/badge?domain=" + encodeURIComponent(domain) + "&style=" + style;

  // ── Styles ───────────────────────────────────────────────────────────────
  var BADGE_ID       = "rs-crypto-shield-badge";
  var CONTAINER_ID   = "rs-badge-container";

  var FONT = "'Inter', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif";

  var COLOR = {
    LOW:      { bg: "#22c55e", text: "#fff", label: "Secured" },
    MEDIUM:   { bg: "#facc15", text: "#0a1628", label: "Monitoring" },
    HIGH:     { bg: "#f97316", text: "#fff", label: "At Risk" },
    CRITICAL: { bg: "#ef4444", text: "#fff", label: "Critical Risk" },
    UNKNOWN:  { bg: "#64748b", text: "#fff", label: "Scanning..." },
  };

  // ── Build badge HTML ─────────────────────────────────────────────────────
  function buildBadge(level, score) {
    var c      = COLOR[level] || COLOR.UNKNOWN;
    var label  = c.label;
    var scoreStr = score !== null ? " " + score + "/100" : "";

    if (style === "compact") {
      return (
        '<a id="' + BADGE_ID + '" href="' + href + '" target="_blank" rel="noopener" ' +
        'style="display:inline-flex;align-items:center;gap:6px;text-decoration:none;' +
        'background:#0a1628;border-radius:20px;padding:4px 10px 4px 6px;' +
        'border:1px solid #1e3a5f;font-family:' + FONT + ';font-size:11px;">' +
        '<span style="font-size:13px;">🛡</span>' +
        '<span style="color:#00B5A5;font-weight:700;">RS</span>' +
        '<span style="background:' + c.bg + ';color:' + c.text + ';border-radius:10px;' +
        'padding:1px 7px;font-weight:700;font-size:10px;">' + label + '</span>' +
        '</a>'
      );
    }

    // flat (default)
    return (
      '<a id="' + BADGE_ID + '" href="' + href + '" target="_blank" rel="noopener" ' +
      'style="display:inline-flex;align-items:center;gap:0;text-decoration:none;' +
      'border-radius:6px;overflow:hidden;font-family:' + FONT + ';font-size:12px;' +
      'box-shadow:0 1px 3px rgba(0,0,0,0.3);">' +

      // Left: RS branding
      '<span style="background:#0a1628;color:#fff;padding:5px 10px;' +
      'display:flex;align-items:center;gap:5px;">' +
      '<span>🛡</span>' +
      '<span style="color:#00B5A5;font-weight:700;">CryptoShield</span>' +
      '</span>' +

      // Right: risk level
      '<span style="background:' + c.bg + ';color:' + c.text + ';' +
      'padding:5px 10px;font-weight:700;">' +
      label + scoreStr +
      '</span>' +

      '</a>'
    );
  }

  // ── Fetch score and inject badge ─────────────────────────────────────────
  function injectBadge() {
    var container = document.createElement("div");
    container.id  = CONTAINER_ID;

    if (position === "fixed-bottom-right") {
      container.style.cssText = (
        "position:fixed;bottom:20px;right:20px;z-index:9999;" +
        "display:flex;flex-direction:column;align-items:flex-end;gap:6px;"
      );
      document.body.appendChild(container);
    } else {
      // Inline — insert after the script tag
      var scriptEl = scripts[scripts.length - 1];
      scriptEl.parentNode.insertBefore(container, scriptEl.nextSibling);
    }

    // Show loading state immediately
    container.innerHTML = buildBadge("UNKNOWN", null);

    // Fetch real score
    fetch(BADGE_API + "&callback=1")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var level = data.risk_level || "UNKNOWN";
        var score = data.risk_score || null;
        container.innerHTML = buildBadge(level, score);
      })
      .catch(function () {
        // Keep loading state on error — don't show error badge publicly
      });
  }

  // ── Entry point ──────────────────────────────────────────────────────────
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", injectBadge);
  } else {
    injectBadge();
  }

})();
