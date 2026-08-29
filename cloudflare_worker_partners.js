// RelayShield Partner Center — partners.relayshield.net
//
// Published terms, decided 2026-08-29: 20% recurring for 12 months on the
// monitored subscription plans. See RelayShield_Strategy.md section 18 for why
// 20% and not 30 or 40, and for the conditions below.
//
// ATTRIBUTION. These links point at Stripe, not at our own landing pages, so
// the ?source= banner mechanism in relayshield_developer_signup.py does not
// apply here and no key needs registering for it. What each link carries:
//
//   client_reference_id=p_<code>   read by relayshield_stripe_webhook.py, which
//                                  writes referred_by onto the user record. This
//                                  is the one that actually pays the partner:
//                                  it survives the redirect, the card form and
//                                  the customer closing the tab.
//   utm_source / utm_campaign      for Stripe's own reporting only. Never rely
//                                  on these to pay anyone; Stripe does not
//                                  guarantee them through a checkout session.
//
// The p_ prefix is load-bearing. client_reference_id already carries the
// Telegram chat_id, and the webhook branches on it; without the prefix a
// referred customer is routed into the Telegram onboarding flow and dropped.

const COMMISSION_PCT = 20;
const COMMISSION_MONTHS = 12;
const CLAWBACK_DAYS = 60;

// Monthly links only. The annual links exist, but a partner sending someone to
// an annual plan is paid the same 20% of what is actually billed, and one list
// is easier to explain than two.
const PLANS = [
  { name: "Personal Shield",           price: "$14.99/mo",  monthly: 14.99,  link: "https://buy.stripe.com/14A8wQa6y1qB8KM2JF0Ny00" },
  { name: "Business Starter",          price: "$19.99/mo",  monthly: 19.99,  link: "https://buy.stripe.com/fZucN6ceGglv3qs9830Ny0a" },
  { name: "Business Starter + Domain", price: "$24.99/mo",  monthly: 24.99,  link: "https://buy.stripe.com/28EdRa2E61qB2mo3NJ0Ny0c" },
  { name: "Business Basic",            price: "$89.99/mo",  monthly: 89.99,  link: "https://buy.stripe.com/aFa8wQ3Iab1b8KM9830Ny03" },
  { name: "Business Shield",           price: "$139.99/mo", monthly: 139.99, link: "https://buy.stripe.com/8x24gA6Um2uF2mo9830Ny04" },
  { name: "Business Shield Pro",       price: "$299.99/mo", monthly: 299.99, link: "https://buy.stripe.com/3cIeVeceG8T3f9a4RN0Ny05" },
];

function planRows() {
  return PLANS.map((p, i) => {
    const perMonth = (p.monthly * COMMISSION_PCT) / 100;
    const perYear = perMonth * COMMISSION_MONTHS;
    return `<tr>
      <td class="plan">${p.name}</td>
      <td class="num">${p.price}</td>
      <td class="num pay">$${perMonth.toFixed(2)}/mo</td>
      <td class="num pay">$${perYear.toFixed(2)}</td>
      <td><button class="copy" data-i="${i}" type="button">Copy link</button></td>
    </tr>`;
  }).join("\n");
}

export default {
  async fetch(request) {
    const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Partner Center — RelayShield</title>
  <meta name="description" content="Refer RelayShield and earn ${COMMISSION_PCT}% recurring commission for ${COMMISSION_MONTHS} months on every monitored plan you bring in.">
  <style>
    :root { --ink:#0f172a; --body:#1e293b; --muted:#64748b; --line:#e2e8f0; --accent:#00B5A5; --bg:#ffffff; --panel:#f8fafc; }
    * { box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; max-width: 880px; margin: 0 auto; padding: 40px 24px 80px; color: var(--body); line-height: 1.65; background: var(--bg); }
    a { color: var(--accent); }
    .back { display:inline-block; margin-bottom:28px; font-size:14px; color:var(--accent); text-decoration:none; }
    h1 { font-size:32px; font-weight:700; color:var(--ink); margin:0 0 8px; letter-spacing:-0.5px; }
    .lede { font-size:18px; color:var(--muted); margin:0 0 36px; }
    h2 { font-size:19px; font-weight:600; color:var(--ink); margin:44px 0 12px; }
    .headline { background:var(--panel); border:1px solid var(--line); border-left:4px solid var(--accent); border-radius:8px; padding:22px 24px; margin-bottom:8px; }
    .headline .big { font-size:26px; font-weight:700; color:var(--ink); }
    .headline .sub { color:var(--muted); font-size:15px; margin-top:4px; }
    label { display:block; font-weight:600; color:var(--ink); font-size:14px; margin-bottom:6px; }
    input[type=text] { width:100%; padding:11px 13px; font-size:15px; border:1px solid var(--line); border-radius:7px; font-family:inherit; }
    input[type=text]:focus { outline:none; border-color:var(--accent); }
    .hint { font-size:13px; color:var(--muted); margin-top:6px; }
    table { width:100%; border-collapse:collapse; margin-top:14px; font-size:14px; }
    th { text-align:left; font-weight:600; color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:0.4px; border-bottom:1px solid var(--line); padding:8px 10px 8px 0; }
    td { padding:11px 10px 11px 0; border-bottom:1px solid var(--line); vertical-align:middle; }
    td.plan { font-weight:600; color:var(--ink); }
    td.num { white-space:nowrap; }
    td.pay { color:var(--accent); font-weight:600; }
    button.copy { background:var(--bg); border:1px solid var(--line); border-radius:6px; padding:6px 12px; font-size:13px; cursor:pointer; color:var(--body); font-family:inherit; white-space:nowrap; }
    button.copy:hover:not(:disabled) { border-color:var(--accent); color:var(--accent); }
    button.copy:disabled { opacity:.45; cursor:not-allowed; }
    button.copy.done { border-color:var(--accent); color:var(--accent); }
    ul { padding-left:20px; }
    li { margin-bottom:9px; }
    .terms li strong { color:var(--ink); }
    .note { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px 18px; font-size:14px; color:var(--muted); }
    footer { margin-top:56px; padding-top:20px; border-top:1px solid var(--line); font-size:13px; color:#94a3b8; }
    @media (max-width:640px) {
      body { padding:28px 16px 60px; }
      h1 { font-size:26px; }
      table, thead, tbody, th, td, tr { display:block; }
      thead { display:none; }
      tr { border:1px solid var(--line); border-radius:8px; padding:12px; margin-bottom:12px; }
      td { border:none; padding:3px 0; }
      td.plan { font-size:16px; margin-bottom:4px; }
      td.pay::before { content:"You earn: "; color:var(--muted); font-weight:400; }
    }
  </style>
</head>
<body>
  <a href="https://relayshield.net" class="back">&larr; RelayShield</a>
  <h1>Partner Center</h1>
  <p class="lede">Refer a business to RelayShield and get paid every month they stay.</p>

  <div class="headline">
    <div class="big">${COMMISSION_PCT}% recurring, for ${COMMISSION_MONTHS} months</div>
    <div class="sub">On every monitored subscription plan you refer. Paid monthly, for as long as the customer stays subscribed, up to ${COMMISSION_MONTHS} months.</div>
  </div>

  <h2>Get your links</h2>
  <p>Enter the partner code we issued you. Every link below is then tagged with it, and any subscription that starts from one of those links is credited to you automatically.</p>

  <label for="code">Your partner code</label>
  <input type="text" id="code" placeholder="e.g. acme-consulting" autocomplete="off" spellcheck="false">
  <p class="hint">Letters, numbers and hyphens. If you do not have one yet, email <a href="mailto:partners@relayshield.net">partners@relayshield.net</a> and we will issue one.</p>

  <table>
    <thead>
      <tr><th>Plan</th><th>Price</th><th>You earn</th><th>Over ${COMMISSION_MONTHS} months</th><th></th></tr>
    </thead>
    <tbody>
${planRows()}
    </tbody>
  </table>

  <h2>What qualifies</h2>
  <ul class="terms">
    <li><strong>The monitored subscription plans only</strong> — the six listed above, monthly or annual. Commission is ${COMMISSION_PCT}% of what the customer is actually billed.</li>
    <li><strong>Not</strong> pay-as-you-go API calls, x402 micropayments, or the Threat Intelligence subscription. Those have no churn history yet, so we are not pricing a commission against them.</li>
  </ul>

  <h2>Terms, in full</h2>
  <ul class="terms">
    <li><strong>${COMMISSION_MONTHS} months per customer.</strong> Commission runs for ${COMMISSION_MONTHS} monthly payments from that customer's first, then stops. It is not lifetime.</li>
    <li><strong>${CLAWBACK_DAYS}-day clawback.</strong> If a referred customer refunds or charges back within ${CLAWBACK_DAYS} days, the commission on that payment is reversed.</li>
    <li><strong>No self-referrals.</strong> A partner code used on your own subscription, or one for a business you control, does not earn commission.</li>
    <li><strong>Payment.</strong> Monthly, in arrears, once your balance passes $50. We will confirm your preferred method when we issue your code.</li>
    <li><strong>Attribution is by link.</strong> The customer must reach checkout through one of your tagged links. We cannot credit a referral after the fact from a name alone.</li>
  </ul>

  <h2>Who this suits</h2>
  <p>Accountants, IT consultants, bookkeepers, POS and Square resellers, and small MSPs — anyone already advising small businesses on the systems a SIM swap or a credential leak would reach first.</p>

  <div class="note">
    <strong>Running a managed service and want to own the customer relationship?</strong> That is a different arrangement, with different economics, and it is worth a conversation rather than a form. Email <a href="mailto:partners@relayshield.net">partners@relayshield.net</a>.
  </div>

  <footer>&copy; 2026 RelayShield. Commission terms may change for new partners; the terms in force when your code was issued continue to apply to customers already referred under it.</footer>

  <script>
    var PLANS = ${JSON.stringify(PLANS.map(p => ({ name: p.name, link: p.link })))};
    var input = document.getElementById("code");

    // Same character class the issuing side uses. Anything else is silently
    // dropped rather than rejected, so a partner pasting "Acme Consulting"
    // still gets a usable code instead of an error they have to decode.
    function clean(v) {
      return v.toLowerCase().replace(/[^a-z0-9-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 64);
    }

    function buildLink(base, code) {
      var u = new URL(base);
      u.searchParams.set("client_reference_id", "p_" + code);
      u.searchParams.set("utm_source", "relayshield-partner");
      u.searchParams.set("utm_campaign", code);
      return u.toString();
    }

    function refresh() {
      var code = clean(input.value);
      var buttons = document.querySelectorAll("button.copy");
      for (var i = 0; i < buttons.length; i++) {
        buttons[i].disabled = !code;
        buttons[i].textContent = "Copy link";
        buttons[i].classList.remove("done");
      }
    }

    input.addEventListener("input", refresh);

    document.addEventListener("click", function (e) {
      var btn = e.target.closest ? e.target.closest("button.copy") : null;
      if (!btn || btn.disabled) return;
      var code = clean(input.value);
      if (!code) return;
      var link = buildLink(PLANS[+btn.dataset.i].link, code);

      function done() {
        btn.textContent = "Copied";
        btn.classList.add("done");
        setTimeout(function () {
          btn.textContent = "Copy link";
          btn.classList.remove("done");
        }, 2000);
      }

      // navigator.clipboard needs a secure context and can still be refused by
      // permissions policy. Fall back to prompt() rather than leaving the
      // partner with a button that silently does nothing.
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(link).then(done, function () { window.prompt("Copy your link:", link); });
      } else {
        window.prompt("Copy your link:", link);
      }
    });

    refresh();
  </script>
</body>
</html>`;

    return new Response(html, {
      headers: {
        "Content-Type": "text/html;charset=UTF-8",
        "Cache-Control": "public, max-age=3600",
      },
    });
  },
};
