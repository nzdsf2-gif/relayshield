/**
 * relayshield-legal-redirect
 *
 * The apex relayshield.net is served by Carrd, which 404s every sub-path. The real
 * Terms of Service and Privacy Policy live on their own Workers at terms.relayshield.net
 * and privacy.relayshield.net. Crypto Shield Mobile's onboarding consent screen, the
 * pricing page footer and several older docs link to relayshield.net/terms and
 * /privacy, which meant users tapping a consent link landed on a dead page.
 *
 * A Worker route on the apex runs before the Carrd origin, so this redirects those
 * paths to the canonical subdomains. Same trick as relayshield.net/developers*.
 *
 * Routes: relayshield.net/terms*, relayshield.net/privacy*
 */

const DESTINATIONS = [
  { prefix: "/terms", target: "https://terms.relayshield.net/" },
  { prefix: "/privacy", target: "https://privacy.relayshield.net/" },
];

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const path = url.pathname.toLowerCase().replace(/\/+$/, "") || "/";

    for (const { prefix, target } of DESTINATIONS) {
      if (path === prefix || path.startsWith(prefix + "/") || path.startsWith(prefix + ".")) {
        const destination = new URL(target);
        destination.search = url.search;
        return Response.redirect(destination.toString(), 301);
      }
    }

    // Nothing we own. Let the request fall through to the Carrd origin.
    return fetch(request);
  },
};
