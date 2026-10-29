# Availability target and load test plan

**STATUS: DRAFT, written 2026-10-29 by Claude. The target is a proposal; the load test has NOT been run.** Covers WAFR
Reliability: *Architect your product to meet availability targets and uptime SLAs* and *Test scalability and performance
requirements*.

## 1. Availability target (PROPOSAL, internal objective, not a customer SLA)

| Surface | Objective | How it is measured |
|---|---|---|
| Public API (`api.relayshield.net`, API Gateway to `relayshield-api`) | 99.5% of requests succeed per calendar month (about 3.6 hours of full outage equivalent) | 1 minus (API Gateway 5XX / Count), on the `relayshield-service-health` dashboard |
| Customer alerts (watchlists, breach monitor) | an alert is produced within one scheduled cycle of the event | scheduled function error alarms |

Why 99.5% and not higher: single Region, no failover, and the API has had init outages (2026-10-05 and 2026-10-11). Promising
more than the architecture can deliver is the failure this practice exists to prevent. **No customer-facing SLA is offered or
implied.** The AWS Marketplace and website copy must not quote this number until it has run for a quarter.
**The current error rate is NOT KNOWN by function**; the 16 percent in the 2026-10-11 evidence was across all functions and
included at least one dead scheduled job. Split it first: `tools/lambda_errors_by_function.sh`.

## 2. Load test plan (not run)

Goal: find the rate at which `relayshield-api` starts to throttle or slow, and confirm the reserved concurrency and stage
throttle values are sensible. Today's observed load is roughly 0.1 requests per second on average, so the test is about
headroom, not current demand.

- **Endpoint:** one that makes NO third-party calls. The shared VirusTotal budget (`relayshield_vt_budget.py`) and other
  paid lookups must not be consumed by a load test. VERIFY in the handler that the chosen route has no outbound call before
  running; this plan does not pick the route because that was not checked.
- **Key:** a dedicated test key on a usage plan, never a customer key, so test traffic is separable in the logs.
- **Profile:** ramp 1, 5, 10, 20 requests per second, three minutes each, from one machine. Stop at the first step where
  5XX exceeds 1 percent, p99 latency exceeds 5 seconds, or any new alarm fires.
- **Timing:** off-peak, with the dashboard open, owner present.
- **Record:** requests per second reached, p50 and p99 latency, error rate, throttles, and the concurrency peak, in section 3.
- **Needs first:** reserved concurrency and the stage throttle applied (`tools/wafr_hardening.py`,
  `tools/wafr_observability.py`), so the test measures the configuration that will actually run.

## 3. Results (append, never edit)

| Date | Peak rps | p99 ms | Error % | Throttles | Notes |
|---|---|---|---|---|---|
| (not run) | | | | | |
