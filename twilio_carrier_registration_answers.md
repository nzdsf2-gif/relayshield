# Twilio carrier registration: field-by-field answers

Form: `https://twlo.my.salesforce-sites.com/countrycarrier/SN_CarrierRegistration_VFP`
(host is `twlo`, Twilio's ticker, verified 200 on 2026-08-07)

**UNBLOCKED 2026-08-08.** Both content gaps are fixed and live. Use the `*.relayshield.net`
subdomains below, **not** the Google Docs, which are older Termly boilerplate and actively hurt this
application. Everything is ready except the three screenshots.

---

## Ready to paste

**Twilio Account SID**
`ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
Verified as an exact match for the SID `relayshield-sim-swap-monitor` authenticates with, so the
approval lands on the account that actually makes the calls.

**Requested Products**
Select `Lookup - SIM Swap` only. Do not add the others; each extra product widens the review.

**Are you an ISV reselling this service to your customers?**
`Yes`. SIM swap detection is resold two ways: as a metered API endpoint
(`/v1/metered/sim-swap`, a priced dimension on the AWS Marketplace listing) and inside the
Crypto Shield Mobile consumer app. Answering "No" here would be inaccurate and is the kind of thing
that unravels later.

**Company Description**
> RelayShield is a security intelligence API. We detect identity and credential exposure for
> businesses and consumers: breached and infostealer-harvested credentials, exposed OAuth tokens,
> lookalike domains, and SIM swap activity. Customers integrate our REST API directly or through
> AWS Marketplace. We also publish Crypto Shield Mobile, a consumer app that monitors an individual's
> exposure and warns them before an account takeover.

**Company Website URL**
`https://relayshield.net`

**Data Access/Stored Location**
> No. All data returned by Twilio is processed and stored solely in the United States, in AWS
> region us-east-1 (Northern Virginia). No Twilio results are transferred to, accessed from, or
> stored in any location outside the United States.

(Verified: every RelayShield Lambda, DynamoDB table and secret is in `us-east-1`.)

**Website URL or Application**
`https://relayshield.net`

**Use Case Description**
> Account takeover prevention. A SIM swap is a common precursor to account takeover, because it
> lets an attacker receive the victim's SMS one-time passcodes.
>
> Where the number is collected: the end user enters their own mobile number during onboarding, in
> the Crypto Shield Mobile app or on our web signup. It is optional, and the screen states plainly
> that it is used to monitor for SIM swap activity. The user must agree to our Terms of Service and
> Privacy Policy before onboarding completes.
>
> When the API request is made: on a recurring schedule for numbers the user has explicitly enrolled
> in monitoring, and never for a number that has not been enrolled. We do not look up numbers
> supplied by third parties about other people.
>
> How the data is used: we compare the SIM swap result against the previously stored state for that
> user's own number. If a swap is detected we alert that user directly so they can contact their
> carrier and stop relying on SMS 2FA. Results are used only to notify the number's own owner and
> are never sold, shared or used for marketing, scoring or advertising.

**Disclosure / Consent Statement(s)**
> Presented during onboarding, before any lookup occurs, next to the phone number field:
>
> "Enter the phone number you use for exchange logins to enable monitoring." The field is marked
> optional.
>
> The user must then accept, on the same screen: "By continuing, you agree to our Terms of Service
> and Privacy Policy." Both are linked. The Privacy Policy states that an enrolled mobile number is
> checked periodically with our telecommunications provider for SIM swap and carrier change activity,
> for the sole purpose of alerting that user.

**User Experience Screenshots** DONE 2026-08-08

Upload `RelayShield_SIMSwap_UserExperience_Screenshots.pdf` in the repo root. Two pages, both real
`adb exec-out screencap` captures from Crypto Shield Mobile v1.5.0 running on the `Pixel_7_API_37`
emulator with the `OnboardingScreen.tsx` link fix in place, so the consent links in the shot resolve.
Regenerate with `build_twilio_exhibit.py` if the screens change.

Fonts are embedded deliberately. The first build used ReportLab's default base-14 Helvetica, which is
not embedded, and rendered as tofu boxes under `pdftocairo` while looking correct in macOS Preview.
Do not swap the faces back to `"Helvetica"`.

Notes for the remaining screenshot, if Twilio asks for the alert itself: there is no real SIM swap
alert to capture, because detection has never produced a verdict. Send a real alert to your own
number and screenshot that rather than mocking one up.

**Upload image files, not source.** This field takes `.png` or `.jpg` screenshots of the running app.
`OnboardingScreen.tsx` is named below only as the screen to photograph, it is not a file to upload.
A Salesforce file input greys out or rejects unknown extensions, so a `.tsx` will not attach.

If the control is still greyed out with image files, fill every required field first, including
`Company Legal Name` above. Salesforce Visualforce forms commonly disable attachments until
validation passes, and the "Complete this field" error is live on that section right now.

Three shots, from the onboarding flow in `crypto-shield-app/src/screens/OnboardingScreen.tsx`:
1. The phone number step, showing the field marked optional and the explanatory copy.
2. The consent line with the Terms and Privacy links visible.
3. A SIM swap alert as the end user receives it, showing what the data is used for.

**Two honesty constraints on these shots.**

Shot 2 must come from a build containing the `OnboardingScreen.tsx:383,385` link fix. The installed
release still points at the 404 URLs, so a screenshot of the shipped app would show a reviewer two
dead consent links. Screenshot a local build; that is the build that ships.

Shot 3 has no real instance to capture, because SIM swap detection has never produced a verdict. Send
yourself a real alert through the normal alert path and screenshot that. Do not mock one up. A
fabricated alert in a carrier compliance file is not worth the risk.

---

## The legal URLs, updated 2026-08-08

Use these three. All verified 200 with the new SIM swap language live.

**Terms & Conditions URL**
`https://terms.relayshield.net`

**Privacy Policy URL**
`https://privacy.relayshield.net`

**Disclosure / Consent Location (URL)**
`https://privacy.relayshield.net`

There is a dedicated **section 4, SIM Swap Monitoring**, written specifically for this review. It
states in plain language that an enrolled number is sent to Twilio as our telecommunications data
provider, that nothing else about the user is sent, that the result is used only to alert the number's
own owner, and that consent can be withdrawn at any time. There is also an explicit statement that we
never acquire numbers from public databases, data brokers, marketing partners or affiliate programs.

The Terms now carry **section 1a**, which requires the enroller to own or control the number and
forbids looking up anyone else's.

### Do NOT use the Google Docs

The two published Google Docs are an older Termly template, last updated April 2026. The privacy one
says we may collect information from "public databases, marketing partners, social media platforms".
That reads to a carrier reviewer as "this company acquires phone numbers it was not given", which is
the exact opposite of the use case in this application. They are now unreferenced by any live surface.

---

## The four fields asked about on 2026-08-08

**Countries**
`United States` only. Do not add others. Each country carries its own carrier consent rules, which is
what the form's own note means by "Depending upon country". Our privacy policy now commits to
US-only processing and storage, so adding an EU or UK country pulls in disclosure obligations we have
not drafted. Countries can be added later by a follow-up request once approved. Adding them now
widens the review for coverage nobody is using.

**Estimated monthly usage volume**
`Approximately 5,000 to 8,000 lookups per month at launch, growing to roughly 35,000 per month within
12 months.`

The number is driven by cadence, not customer count. The monitor runs on EventBridge rule
`relayshield-sim-swap-monitor-schedule`, verified live at `rate(1 hour)`, so each enrolled number is
about **730 lookups per month**. Eight to twelve enrolled numbers at launch gives the range above.
Show that arithmetic if they ask, it is the honest answer and it explains an otherwise odd number.

**Anticipated launch date**
`2026-10-01`. The code is written and deployed; the feature is blocked only on this approval. October
leaves room for a multi-week carrier review plus the Crypto Shield Mobile v1.5.0 release, and is a
date we will not blow through. Do not promise sooner.

**End Customer - Company Information**

`Company Legal Name` is a **required** field and its subtitle is "Twilio Account to enable". That
subtitle is the whole answer: this section is not a free-text description of our customers, it is
Twilio asking **which Twilio account to switch SIM Swap on for**. It appears because we answered
`Yes` to the ISV reselling question, and Twilio's reseller model assumes each end customer holds
their own Twilio account.

We do not have that model. Every SIM swap call goes through our own single account SID.

```
Company Legal Name:        RelayShield LLC
Twilio Account to enable:  ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

That is truthful: the account to be enabled is ours. `RelayShield LLC` is the exact registered name,
Massachusetts, approved April 2026.

It cannot be left blank. "Complete this field" is a required-field validator, so the only ways past
it are to fill it or to remove what triggered the section, which means changing the ISV answer to
`No`. Do not do that. ISV `Yes` is accurate, because SIM swap is a priced dimension on the AWS
Marketplace listing, and changing a prior answer to dodge a later field is exactly the sort of thing
that unravels on review.

If a longer description field also appears in that section, use:

> RelayShield sells self-serve, so there is no separate reseller end customer holding its own Twilio
> account. The end customer today is the individual consumer using Crypto Shield Mobile,
> RelayShield's own published app, who enrolls their own mobile number during onboarding and is the
> only person the result is disclosed to. SIM swap is also offered as a priced dimension on our AWS
> Marketplace API listing, where the subscribing business may enroll only numbers belonging to its
> own consenting users.

## Two content gaps, both FIXED 2026-08-08

Neither blocks the form technically, but both are things a carrier-approval reviewer reads closely.

**1. No disclosure that the number goes to a telecoms provider.**
The privacy policy mentions SIM swap once, and only as a description of what the product protects
against. It never says the user's mobile number is transmitted to or checked with a
telecommunications or communications provider for SIM swap and carrier status. That specific
disclosure is what Twilio's consent question is testing for. The third-party section covers
collecting *from* public databases and marketing partners, and names service providers only for
analytics and advertising.

Add a short paragraph, roughly:

> If you enrol a mobile number for SIM swap monitoring, we periodically check that number with our
> telecommunications data provider to determine whether the SIM or carrier associated with it has
> recently changed. We share only the number itself, solely for this purpose. The result is used
> only to alert you, is never sold or shared, and you can withdraw consent at any time by removing
> the number or contacting us.

**2. A boilerplate clause that contradicts the use case.**
The privacy policy currently says phone numbers may be obtained "from other sources, such as public
databases, joint marketing partners, affiliate programs, and data providers ... for purposes of
targeted advertising and event promotion."

That is generic template text, but on a carrier-approval review it reads as "this company acquires
phone numbers it was not given and uses them for marketing", which is close to the opposite of the
use case above. It sits directly against the strongest argument in the application, that you only
ever look up a number its own owner enrolled. Worth narrowing or removing the phone-number half of
that clause before submitting.

---

## Separate live defect, part-fixed 2026-08-08

Crypto Shield Mobile's onboarding linked Terms and Privacy to `https://relayshield.net/terms` and
`https://relayshield.net/privacy`. **Both 404.**

Repointed at source to the working subdomains in `OnboardingScreen.tsx:383,385`. That ships with the
next Crypto Shield Mobile release, so **the currently installed app still has the dead links.** The
Twilio screenshots will show the fixed build, which is accurate for what ships, and the consent URL
given on the form works today regardless.

Same dead links were found and fixed in `cloudflare_worker_pricing.js` (redeployed, live now) and
`signup.html` (not currently served anywhere).

A redirect worker `relayshield-legal-redirect` is deployed on routes `relayshield.net/terms*` and
`relayshield.net/privacy*`. **It does not fire.** The routes are registered on the zone and the
worker is deployed, but the apex still returns Carrd's 404. The pre-existing
`relayshield.net/developers*` route fails the same way, so this is systemic to the apex and not a
mistake in this worker. Evidence that the apex is not served by our Cloudflare edge: subdomain
responses carry `report-to`, `nel` and `alt-svc` headers and the apex carries none of them, while the
apex 404 carries a `last-modified` from the Carrd origin. Most likely the apex DNS record is not
proxied through our zone. Fixing it means orange-clouding the apex record in the Cloudflare
dashboard, which needs the founder and risks the marketing site, so it was not attempted. The worker
is harmless where it sits and will start working the day that changes.
