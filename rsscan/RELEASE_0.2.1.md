# rsscan 0.2.1 — release runbook

**Internal. Not shipped in the sdist (excluded like PUBLISHING.md).**

## What is in 0.2.1

Three detection patterns, taking the set from 31 to 34. All three were found the same way: by
something *other than rsscan* catching a credential rsscan had missed.

| Pattern | Severity | How it was found |
|---|---|---|
| `relayshield_key` — `rs_(live\|demo)_[a-f0-9]{32,}` | CRITICAL | A live internal key reached public commit `43ba820`. **GitGuardian** caught it. rsscan scanned the same commit and passed |
| `slack_webhook` — `hooks.slack.com/services/T…/B…/…` | HIGH | **GitHub push protection** blocked the push. rsscan had `xoxb`/`xoxp` but not the webhook URL, which is a different shape |
| `zapier_webhook` — `hooks.zapier.com/hooks/(catch\|standard)/…` | HIGH | Found on an internal key record while auditing the above |

**The one that matters is `relayshield_key`.** A secret scanner that does not detect its own
vendor's credentials is the first thing a security audience tests, and until this release ours did
not. Worth saying plainly in the release notes rather than burying it in a changelog line.

**Also fixed: `action.yml` and `orb/rsscan.yml` pinned `rsscan==0.1.3`.** They were never bumped for
0.2.0, so every GitHub Action and CircleCI orb user has been running 0.1.3 — without `--deps`, and
without any pattern added since. Both now pin `0.2.1`. **Check this on every future release**; the
version lives in four places and only `pyproject.toml` is obvious.

## 0. Before building

Patterns are a generated mirror. Never hand-edit `rsscan/patterns.py`.

```bash
cd "/Users/andrewgibbs/Side SaaS Hustle"
python3 tools/sync_patterns.py --check      # must print "in sync"
cd rsscan && python3 -m pytest test_verify.py -q   # or: python3 test_verify.py
```

Then confirm the new patterns actually fire, rather than trusting the diff:

```bash
cd "/Users/andrewgibbs/Side SaaS Hustle"
printf 'k = "rs_live_%s"\n' "$(python3 -c "print('a1b2c3d4'*6)")" > _canary.py
git add _canary.py && rsscan; echo "expect non-zero: $?"
git reset _canary.py && rm -f _canary.py
```

## 1. Build

```bash
cd "/Users/andrewgibbs/Side SaaS Hustle/rsscan"
rm -rf dist build *.egg-info
python3 -m pip install --quiet --upgrade build twine
python3 -m build
python3 -m twine check dist/*
```

Expect `dist/rsscan-0.2.1-py3-none-any.whl` and `dist/rsscan-0.2.1.tar.gz`, both PASSED.

Confirm the runbooks did not get bundled:

```bash
tar -tzf dist/rsscan-0.2.1.tar.gz | grep -E "RELEASE|PUBLISHING" || echo "correctly excluded"
```

## 2. Upload

**Do not paste the PyPI token into chat.** Use one of:

**Trusted Publishing (recommended).** Removes the token permanently. PyPI → `rsscan` → Manage →
Publishing → add a GitHub publisher for `RelayShield/rsscan`, workflow `release.yml`. Then releases
happen on tag push with no secret anywhere.

**Or from your machine, this once:**

```bash
cd "/Users/andrewgibbs/Side SaaS Hustle/rsscan"
python3 -m twine upload dist/rsscan-0.2.1*
# username: __token__
# password: paste the pypi-… token at the prompt, it is not echoed
```

## 3. Verify the upload

```bash
sleep 30
curl -s https://pypi.org/pypi/rsscan/json | python3 -c "import json,sys;print(json.load(sys.stdin)['info']['version'])"
# expect: 0.2.1
```

Then install it clean and check the pattern count, because that is the claim the README makes:

```bash
python3 -m venv /tmp/rsv && /tmp/rsv/bin/pip install --quiet rsscan==0.2.1
/tmp/rsv/bin/python -c "from rsscan.patterns import NHI_PATTERNS as p; print(len(p), 'patterns'); print('relayshield_key' in [x[0] for x in p])"
# expect: 34 patterns / True
rm -rf /tmp/rsv
```

## 4. Tag, and the three other catalogs

The pre-commit config, the Action and the Docker image all pin a version, so a PyPI upload alone
leaves them on the old one.

```bash
cd "/Users/andrewgibbs/Side SaaS Hustle/rsscan"
git tag -a v0.2.1 -m "rsscan 0.2.1 — RelayShield key, Slack and Zapier webhook detection"
git push origin v0.2.1
```

| Catalog | Action |
|---|---|
| **GitHub Action** | The `v0.2.1` tag is what `uses: RelayShield/rsscan@v0.2.1` resolves. Also move the floating `v0` tag if you maintain one |
| **Docker Hub** | `docker build -t relayshield/rsscan:0.2.1 -t relayshield/rsscan:latest . && docker push relayshield/rsscan:0.2.1 && docker push relayshield/rsscan:latest` |
| **CircleCI orb** | `circleci orb publish orb/rsscan.yml relayshield/rsscan@0.2.1` |
| **GitLab CI/CD Catalog** | Tag the mirror; the component reads its version from the tag |
| **Artifact Hub** | Re-reads `artifacthub-repo.yml` from the repo, no action needed |

## 5. Gate on this before the Blue Team Village post

`btv_rsscan_post.md` points people at the tool and quotes the pattern count. **Do not post until
0.2.1 is on PyPI and the `v0.2.1` tag exists**, or the post advertises detection that is not in the
package people install. That is the same "announced before it existed" trap this project has hit
before, and this audience checks.
