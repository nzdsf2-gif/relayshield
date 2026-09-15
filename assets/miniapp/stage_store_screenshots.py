#!/usr/bin/env python3
"""Build the four staged HTML files a catalogue screenshot is taken from.

WHY THIS EXISTS AT ALL, and it is the rule this repo keeps paying for: the
SOURCE and the SERVED text are different documents. Screenshotting the Worker
source is not possible and screenshotting a phone is not reproducible, so these
are rendered from `tools/miniapp_render.mjs` -- the bytes a browser actually
receives -- and driven by a classic script appended after the page's own module.

WHY A CLASSIC SCRIPT AND WHY IT POLLS. The page code is a MODULE, so it is
deferred and runs after any classic script in the document however late that
script appears. `window.__rsBoot` is the module's own heartbeat (set directly
after its import, for the boot watchdog), so waiting on it is waiting on the
real thing rather than on a timer that happens to be long enough.

NOTHING HERE FABRICATES A VERDICT. api.relayshield.net is egress-blocked from
this container, and a canned "flagged" card would be a claim about our own
product that nobody can check and that goes stale the day the verdict changes --
which is the same reason the in-app example runs a real check instead of
rendering a picture of one. Every state staged below is produced by the page's
own client-side code with no network call at all:

  01  the Check tab as it opens
  02  the off-chain refusal, from offChainReason(), which is pure and local
  03  the Watching tab, whose tier copy and buy button are static markup
  04  Spot the fake, whose pairs are built in the page

Usage: python3 assets/miniapp/stage_store_screenshots.py <served-page.html> <outdir>
"""
import sys, pathlib, re

BOOT = """
<script>
/* Classic, and appended last on purpose. A module that fails to parse never
   runs its own staging code, so the driver has to live outside it. */
(function () {
  var TARGET = "__STAGE__";
  function ready(fn) {
    if (window.__rsBoot) return fn();
    setTimeout(function () { ready(fn); }, 25);
  }
  function click(id) { var e = document.getElementById(id); if (e) e.click(); }
  ready(function () {
    if (TARGET === "refusal") {
      var box = document.getElementById("in");
      box.value = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e";
      click("go");
    } else if (TARGET === "watch") {
      click("tab-watch");
    } else if (TARGET === "learn") {
      click("tab-learn");
    }
    document.documentElement.setAttribute("data-staged", TARGET);
  });
})();
</script>
"""

STAGES = ["check", "refusal", "watch", "learn"]


def main() -> int:
    page = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
    out = pathlib.Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)

    # The SDK script is fetched from telegram.org, which is unreachable here and
    # would be a slow failure rather than a fast one. The page already runs
    # without the SDK -- `tg` is guarded at every use -- so dropping the tag
    # stages the same code path a browser with a blocked CDN would take, rather
    # than a different one.
    page = re.sub(r'<script src="https://telegram\.org[^"]*"></script>', "", page)

    if "</body>" not in page:
        raise SystemExit("the served page has no </body>; re-point this script")

    for stage in STAGES:
        staged = page.replace("</body>", BOOT.replace("__STAGE__", stage) + "</body>")
        path = out / f"stage_{stage}.html"
        path.write_text(staged, encoding="utf-8")
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
