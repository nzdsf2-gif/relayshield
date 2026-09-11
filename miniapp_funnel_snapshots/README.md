Baselines written by `tools/miniapp_funnel.py --snapshot <label>`.

**Commit them.** A baseline that exists on one machine is not a baseline, and
the container these tools were written in is reclaimed.

One file per route, named `before-<route id>.json`, where the id comes from
`miniapp_routes.json`. The tool refuses to overwrite an existing one: a baseline
replaced after the submission has already run turns the before-and-after into a
comparison of a number with itself, which reads as "the channel did nothing".
