// Print the TI demo page the Worker ACTUALLY SERVES, for a token-authed request.
//
//   node tools/ti_demo_render.mjs > /tmp/ti.html
//
// WHY THIS EXISTS RATHER THAN A GREP OF THE SOURCE. The whole page is inside a
// template literal, so the Worker evaluates its escape sequences ONCE before a
// browser sees any of it -- and this repo has shipped a dead app three times on
// exactly that gap: a stray backtick, a constant declared in Worker scope and
// read from the page, and an escape eaten twice. `node --check` passed all
// three. Reading the SERVED bytes is the only check that answers "does this
// run", and it is the same reason tools/miniapp_render.mjs exists.
//
// The gate is failed-closed on env.DEMO_TOKEN, so the stub supplies one; the
// value is arbitrary and local, never the live secret.
import worker from "../cloudflare_worker_ti_demo.js";

const TOKEN = "render-only-not-the-live-secret";
const res = await worker.fetch(
  new Request(`https://ti.example/?token=${TOKEN}`),
  { DEMO_TOKEN: TOKEN },
);
if (res.status !== 200) {
  console.error(`the Worker answered ${res.status}, not 200`);
  console.error(await res.text());
  process.exit(1);
}
process.stdout.write(await res.text());
