/**
 * Print the page the Mini App Worker ACTUALLY SERVES, by running the Worker.
 *
 *   node tools/miniapp_render.mjs              the page
 *   node tools/miniapp_render.mjs --module     just the <script type="module"> body
 *   node tools/miniapp_render.mjs --widget     the imported widget module
 *
 * WHY THIS EXISTS, AND IT IS THE MOST IMPORTANT FILE IN THE MINI APP TEST SETUP.
 *
 * The page lives inside a TEMPLATE LITERAL in cloudflare_worker_miniapp.js, so
 * the Worker evaluates its escape sequences once before a browser ever sees it.
 * Reading the source and stripping a couple of escapes by hand -- which is what
 * every check here did until 2026-09-11 -- produces text that NO ONE EVER RUNS.
 *
 * It shipped a dead app. A regex written `/^(?:https?:\/\/...` served as
 * `/^(?:https?://...`, which ends the regex literal at the second slash, so the
 * browser threw "Invalid regular expression: missing )" while parsing the
 * module. The module never ran, no handler was ever registered, and the app
 * rendered as static HTML with dead tabs and a dead button. Every check in the
 * repo passed, because every check read the source.
 *
 * A detector whose extractor does not match what is deployed cannot detect
 * anything. This is the extractor that matches: it runs the Worker.
 */
import { pathToFileURL } from "node:url";
import { writeFileSync, copyFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
// Copied to .mjs so node treats it as a module whatever any package.json says.
const dir = mkdtempSync(join(tmpdir(), "rs-render-"));
const copy = join(dir, "worker.mjs");
copyFileSync(join(root, "cloudflare_worker_miniapp.js"), copy);

const worker = await import(pathToFileURL(copy).href);
const want = process.argv[2] || "";

const path = want === "--widget" ? "/relayshield-widget.js" : "/";
const res = await worker.default.fetch(
  new Request("https://app.relayshield.net" + path), {}, {});
const text = await res.text();

if (want === "--module") {
  const m = text.match(/<script type="module">([\s\S]*?)<\/script>/);
  if (!m) { console.error("no module script in the served page"); process.exit(1); }
  process.stdout.write(m[1]);
} else {
  process.stdout.write(text);
}
