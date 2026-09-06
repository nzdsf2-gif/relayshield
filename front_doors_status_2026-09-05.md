# Front doors: every FD, current status, 2026-09-05

Snapshot. `FRONT_DOORS.md` in the repo is the maintained version; this is the
one-page read. Twelve doors, four live, one dead, two founder-side and one
command away, four not started.

## The table

| ID | Front door | Status | Next action | Whose |
|---|---|---|---|---|
| FD-1 | GitHub Marketplace Action (rsscan) | **DONE** 2026-09-02, v0.2.1, badge live | none | done |
| FD-2 | pre-commit.com hooks index | **DEAD AS SCOPED** | none, and do not reopen | closed |
| FD-3a | mcp.so | **SKIPPED**, now $39 paid | none | closed |
| FD-3b | Smithery listing (see FD-11) | Not listed | one file in `~/mcp-live` | founder |
| FD-3c | `modelcontextprotocol/servers` | Not started | **read its contribution rules first** | unscoped |
| FD-4 | Splunkbase app | Not started, 3-5 days | none yet | later |
| FD-5 | OpenCTI connector | Not started, 2-3 days | none yet | later |
| FD-6 | Chrome Web Store extension | Not started, 1 week | none yet | later |
| FD-7 | Slack App Directory | Not started, 1 week | none yet | later |
| FD-8 | Official MCP registry | **LISTED since 2026-05-10, record stale and unattributed** | one `mcp-publisher` run | founder |
| FD-9 | Glama | **LISTED**, verified 2026-09-03 | fixed by the same FD-8 publish | founder |
| FD-10 | PyPI project page | **OPEN, now attributed in the file** | ships with the next PyPI release | founder |
| FD-11 | Smithery | Not listed | `mcp_registry/smithery.yaml` is written and unshipped | founder |
| FD-12 | Anthropic plugin directory | **ROUTE OPEN, ARTEFACT BUILT** | gated on the pin fix | both |

## The one that is actually urgent

**FD-8, FD-9, FD-10 and the `mcp<2` pin are one release, and the pin is not a
tidy-up.** `relayshield-mcp` on PyPI declares `mcp` with no upper bound, so a
fresh install resolves mcp 2.x and the server dies at import. That is reproduced,
not inferred. Every new user today gets a broken server that reports as
"disconnected".

The order matters and it is not the order the front-door numbering suggests:

1. Fix the pin so it is bounded at `<2`.
2. Bump the package version, build, **upload to PyPI**.
3. Verify with `python3 tools/mcp_selftest.py --pypi`, which installs what a new
   user gets rather than what we have in a venv.
4. Only then publish the registry record, so it names a version that exists and
   works.

`tools/fd8_prepare_republish.py --dir ~/mcp-live` prepares steps 1 and the record
edits. Two bugs in it were found and fixed on 2026-09-05 by running it against
the real directory: it was writing a version DOWNGRADE (0.2.9 over a local
0.2.11), and its pin matcher was too narrow and reported "not found" on a package
that plainly has the dependency. Re-run it after merging.

**One thing to check by hand.** The script found no `mcp` dependency in
`~/mcp-live` in any of the four shapes it now searches. Either the declaration
lives somewhere unusual, or it is generated. The script now prints the real
dependency block when it fails to match, so re-running it will show the syntax.
Whatever the shape, the published metadata is what decides, and `--pypi` is the
check that reads it.

## FD-12, the new one

Added today. `anthropics/claude-plugins-official` accepts third-party
submissions, in its own README's words, via
<https://clau.de/plugin-directory-submission>. The bar is stated as "quality and
security standards" without enumeration.

The artefact exists: this repo is a marketplace, the plugin holds the agent-bait
skill, and both manifests pass `claude plugin validate`. The full install was run
end to end rather than assumed.

**It is gated on the pin.** The version worth submitting bundles the MCP server
so that installing the plugin wires up the server too, and bundling a server that
dies at import would fail on first use for every reviewer.

**Installing it needs the marketplace on GitHub's default branch.** The
`owner/repo` form clones the default branch, so `nzdsf2-gif/relayshield` resolves
only once `main` carries `.claude-plugin/marketplace.json`. Until then, the local
path works and needs no push.

## FD-3c is unscoped on purpose

`modelcontextprotocol/servers` is the highest-value MCP listing left, and nobody
has read its contribution rules. That is the FD-2 lesson: a day was spent writing
a submission for a curated page whose own last section said the PR would be
closed without comment. Read the destination, then scope it.

## Ranking, if you only do some of them

1. **The pin plus FD-8/9/10.** One release, and it fixes a live breakage rather
   than adding a listing.
2. **FD-12.** Free, the route is confirmed open, and it reaches developers at the
   moment they are deciding to trust something.
3. **FD-11 Smithery.** One file, already written.
4. **FD-3c**, after its rules are read.
5. FD-4 through FD-7 are days each and should wait until the free listings are
   live and measured.
