/**
 * Load the SERVED Mini App page the way a browser does, and click things.
 *
 *   node tools/miniapp_smoke.mjs
 *
 * This is the check that would have caught the 2026-09-11 outage before it
 * shipped, and no other check in the repo could have.
 *
 * THE FAILURE IT EXISTS FOR. A regex written `/^(?:https?:\/\/...` inside the
 * PAGE template literal is served as `/^(?:https?://...`, because the Worker
 * evaluates the escape once. The second slash ENDS the regex literal, so the
 * browser throws "Invalid regular expression: missing )" while parsing the
 * module. The module never runs. No handler is ever registered. The app renders
 * perfectly as static HTML with dead tabs and a dead button -- which on a phone,
 * with no console, is indistinguishable from a CSS bug or a stale cache.
 *
 * Every check in the repo passed, because they all read the SOURCE. This one
 * runs the Worker, takes the module it actually serves, evaluates it against a
 * minimal DOM, and fires the handlers a user presses.
 *
 * The DOM stub is deliberately dumb: it records listeners and swallows layout.
 * It is not a browser and cannot judge whether anything LOOKS right. It answers
 * one question -- does the code a browser receives run, and do the controls
 * respond -- which is the question that was open for a whole round trip.
 */
import { execFileSync } from "node:child_process";
import { writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const root = resolve(import.meta.dirname, "..");
const page = execFileSync("node", [join(root, "tools/miniapp_render.mjs")],
                          { encoding: "utf8", maxBuffer: 32 * 1024 * 1024 });
const mod = execFileSync("node", [join(root, "tools/miniapp_render.mjs"), "--module"],
                         { encoding: "utf8", maxBuffer: 32 * 1024 * 1024 });

const ids = [...new Set([...page.matchAll(/id="([a-z0-9-]+)"/g)].map((m) => m[1]))];
const listeners = {};
const el = (id) => ({
  id, textContent: "", value: "", hidden: false, disabled: false,
  dataset: {}, style: {}, className: "", childElementCount: 0, children: [],
  classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
  setAttribute() {}, getAttribute: () => null,
  addEventListener(ev, fn) { (listeners[id] ||= {})[ev] = fn; },
  appendChild(c) { this.children.push(c); this.childElementCount++; },
  getContext: () => new Proxy({}, { get: () => () => {} }),
  querySelectorAll: () => [],
});
const reg = Object.fromEntries(ids.map((i) => [i, el(i)]));

globalThis.document = {
  getElementById: (id) => reg[id] || null,
  createElement: (t) => el("created-" + t),
  createTextNode: (t) => ({ nodeValue: t }),
  querySelectorAll: () => [], addEventListener() {},
};
globalThis.window = {
  Telegram: { WebApp: {
    ready() {}, expand() {}, initDataUnsafe: { start_param: "" }, initData: "",
    HapticFeedback: { notificationOccurred() {} },
    openInvoice() {}, addToHomeScreen() {}, openTelegramLink() {},
  } },
  addEventListener() {},
};
globalThis.location = { search: "" };
globalThis.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
Object.defineProperty(globalThis, "navigator",
  { value: { clipboard: { writeText: async () => {} } }, configurable: true });
globalThis.setTimeout = () => 0;
globalThis.fetch = async () => ({ json: async () => ({ ok: false }) });

// The widget is served by the Worker; stub it so this tests the PAGE.
const src = mod.replace('import { check } from "/relayshield-widget.js";',
  'const check = async () => ({ level: "unknown", target: "x", reasons: [] });');
const dir = mkdtempSync(join(tmpdir(), "rs-smoke-"));
const file = join(dir, "page.mjs");
writeFileSync(file, src);

let failed = 0;
try {
  await import(pathToFileURL(file).href);
  console.log("ok    the served module evaluated");
} catch (e) {
  console.log("FAIL  the served module threw while loading: " + e.message);
  console.log("      A browser would register NO handlers. The app renders as");
  console.log("      static HTML with dead tabs and dead buttons.");
  process.exit(1);
}

if (globalThis.window.__rsBoot !== true) {
  console.log("FAIL  the boot heartbeat was never set");
  failed++;
} else {
  console.log("ok    boot heartbeat set");
}

for (const id of ["tab-check", "tab-watch", "tab-learn", "try-bad", "go", "watch", "share",
                  "watch-buy"]) {
  const fn = listeners[id] && listeners[id].click;
  if (!fn) { console.log("FAIL  no click listener registered: " + id); failed++; continue; }
  try { fn(); console.log("ok    " + id); }
  catch (e) { console.log("FAIL  " + id + " threw: " + e.message); failed++; }
}

console.log(failed ? "\n" + failed + " FAILURE(S)" : "\nthe served page runs and every control responds");
process.exit(failed ? 1 : 0);
