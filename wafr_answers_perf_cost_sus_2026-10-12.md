# Well-Architected review: PERFORMANCE (PERF 1-5), COST (COST 1-11), SUSTAINABILITY (SUS 1-6)

Workload: RelayShield API, Production, us-east-1, account 239677749008, Framework lens.
Written 2026-10-12. 22 questions. Evidence is the account read from `tools/wafr_evidence.sh` and
`tools/lambda_errors_by_function.sh`, plus the repository.

**Same rules as the Reliability sheet.** TICK what is listed under TICK. Leave the rest. If a
practice is genuinely irrelevant (no VPN, no block storage, no GPUs), use the console's
**"Mark best practice(s) that don't apply to this workload"** drop-down and name it under
NOT APPLICABLE below, instead of leaving it unticked, which would count against you. Notes text is
kept under 2,084 characters, the console limit. PERF 1's practice names are taken from your
screenshot; the others are the Framework lens as I know it, so match by meaning where wording
differs.

**Do not tick anything to make a risk go away.** The FTR reviewer asks for evidence behind each tick.

## Things to do before you tick the ones marked CONDITIONAL

| Tick only after | Command | Unlocks |
|---|---|---|
| a budget exists | `AWS_PROFILE=relayshield sh tools/create_cost_budget.sh --apply` | COST 1 budgets, COST 1 monitor, and the budget sentence in the COST 1 Notes |
| the SIM swap monitor is on four hours | `AWS_PROFILE=relayshield sh tools/set_sim_swap_monitor_schedule.sh --apply` | the "moved to four-hourly" sentences in COST 1, COST 5 and SUS 3, and the SUS 3 scheduled-jobs tick |

**Until each of those two is run, delete the sentence that depends on it.** They describe a change that
has not happened yet, and the reviewer will check. Everything else below is true today.

---

# PERFORMANCE EFFICIENCY

## PERF 1. How do you select the appropriate cloud resources and architecture patterns for your workload?

**TICK**
- Learn about and understand available cloud services and features
- Evaluate how trade-offs impact customers and architecture efficiency
- Use guidance from your cloud provider or an appropriate partner to learn about architecture
  patterns and best practices
- Factor cost into architectural decisions
- Use a data-driven approach for architectural choices

**LEAVE UNTICKED**
- Use policies and reference architectures
- Use benchmarking to drive architectural decisions

**Notes**
> Architecture is serverless (Lambda, API Gateway, DynamoDB on-demand, EventBridge schedules) chosen
> for pay-per-use at low volume. Trade-offs are recorded per control (fail-open versus fail-closed,
> cache lifetimes, per-key and per-source limits). Cost is an explicit design input: expensive upstream
> calls sit behind caches, budgets and quotas. Decisions are driven by measured counts (for example the
> SIM swap monitor cadence and the VirusTotal budget were both set from log data). Guidance comes from
> the AWS Partner programme, Marketplace technical review and this Well-Architected review. There is no
> written internal reference architecture and no benchmarking yet.

## PERF 2. How do you select and use compute resources in your workload?

**TICK**
- Evaluate the available compute options. *Lambda for the API and monitors, Cloudflare Workers for
  static and edge pages, a hosted Space for the MCP server.*
- Collect compute-related metrics. *CloudWatch Lambda metrics, read per function.*
- Use the available elasticity of resources. *Lambda scales per request; subject to the concurrency
  quota, see REL 1.*

**LEAVE UNTICKED**
- Understand the available compute configuration and features. *Memory and architecture have not been
  evaluated: all 61 functions are x86_64.*
- Determine the required configuration by right-sizing. *No right-sizing exercise.*
- Re-evaluate compute needs based on metrics

**Notes**
> 61 Lambda functions at 128 MB to 1,024 MB with timeouts from 3 to 900 seconds; all x86_64. Memory
> and timeouts were set when each function was created and have not been right-sized against
> measured duration. Graviton (arm64) has not been evaluated. The account concurrency quota (10) is
> the binding constraint today and a raise is requested. A right-sizing pass and an arm64 trial on the
> highest-volume functions are planned after the quota is raised.

## PERF 3. How do you store, manage, and access data in your workload?

**TICK**
- Evaluate available configuration options for data store. *DynamoDB on-demand, TTL, point-in-time
  recovery on state tables.*
- Implement strategies to improve query performance in data store. *Hot paths are key lookups, not
  scans.*
- Implement data access patterns that utilize caching. *Cache tables for breach, URL, secret-scan and
  taxonomy lookups, plus per-container caches, each with an expiry.*

**LEAVE UNTICKED**
- Collect and record data store performance metrics. *Only default DynamoDB metrics, not reviewed.*

**Notes**
> 57 DynamoDB tables, all on-demand. Hot request paths use key lookups; caches front the paid and
> rate-limited upstreams (breach, URL reputation, secret-scan) with TTLs. A few scheduled jobs scan
> small tables. DynamoDB latency and throttle metrics are not yet alarmed or reviewed.

## PERF 4. How do you select and configure networking resources in your workload?

**TICK**
- Understand how networking impacts performance. *Measured: a mobile client over a cold Lambda needed a
  12-second deadline, not the 4 seconds inherited from a bot widget.*
- Leverage load-balancing and encryption offloading. *API Gateway terminates TLS.*

**LEAVE UNTICKED**
- Evaluate available networking features
- Choose network protocols to improve performance
- Choose location based on network requirements. *Single Region, not analysed against client
  locations.*
- Optimize network configuration based on metrics

**NOT APPLICABLE** (use the drop-down)
- Choose appropriately sized dedicated connectivity or VPN for hybrid workloads. *No hybrid
  connectivity; no Lambda function is VPC-attached.*

**Notes**
> No VPC, so there is no private network to size or tune. Public traffic enters through API Gateway
> (TLS terminated there) and Cloudflare for static pages. Network effects were measured on the mobile
> path and the timeout was raised accordingly. Endpoint type, protocol and Region choice have not been
> evaluated against client geography.

## PERF 5. How do your organizational practices and culture contribute to performance efficiency in your workload?

**TICK**
- Keep your workload and services up-to-date. *36 functions run Python 3.14; dependency audit runs on
  every push.*

**LEAVE UNTICKED**
- Establish key performance indicators (KPIs) to measure workload health and performance
- Use monitoring solutions to understand the areas where performance is most critical
- Define a process to improve workload performance
- Load test your workload
- Use automation to proactively remediate performance-related issues

**Notes**
> Runtimes and dependencies are kept current. Performance KPIs, tracing, load testing and a
> performance-improvement process do not exist yet. The first findings from measurement were a 20%
> function error rate on the public API and 427 throttles in seven days, both being addressed under the
> Reliability pillar. A baseline load test is planned once the concurrency quota is raised.

---

# COST OPTIMIZATION

## COST 1. How do you implement cloud financial management?

**TICK**
- Implement cost awareness in your organizational processes. *Cost is checked before a change ships:
  caps, budgets and exclusions were added after measured spend.*

**TICK AFTER `tools/create_cost_budget.sh --apply`  (CONDITIONAL)**
- Establish cloud budgets and forecasts
- Monitor cost proactively. *The cost anomaly monitor already exists; the budget adds a threshold.*

**LEAVE UNTICKED**
- Establish a cost optimization function
- Establish a partnership between finance and technology
- Report and notify on cost optimization
- Keep up-to-date with new service releases

**Notes**
> AWS spend is currently very small (free tier and credits cover most services), so the material cost
> risk is third-party usage: telephony lookups, a shared reputation API key and similar. Those are
> controlled in the application with per-key, per-source and daily budgets, and a recent review moved
> the highest-cost scheduled job from hourly to four-hourly after measuring it. [ONLY AFTER THE BUDGET EXISTS:] A monthly AWS cost
> budget with email alerts and a cost anomaly monitor are in place. Cost ownership is a single
> founder rather than a function.

## COST 2. How do you govern usage?

**TICK**
- Implement an account structure. *Production is separate from a pre-audit account.*
- Implement groups and roles. *CI deploys through an OIDC role; per-function roles are being adopted.*
- Implement cost controls. *Application-level quotas, an API usage plan with a monthly quota, and a
  hard account concurrency limit.*

**LEAVE UNTICKED**
- Develop policies based on your organization requirements
- Implement goals and targets
- Track project lifecycle

**Notes**
> Cost controls are application-level (per-key hourly caps, per-source daily quotas, a daily budget on
> the shared reputation key, the free tier excluded from per-call-cost endpoints, an API usage plan of
> 50,000 requests a month). There is no written cost policy or target yet.

## COST 3. How do you monitor usage and cost?

**TICK**
- Configure billing and cost management tools. *Cost Explorer and a cost anomaly monitor are enabled.*

**LEAVE UNTICKED**
- Configure detailed information sources. *No Cost and Usage Report.*
- Add organization information to cost and usage. *Tags exist but are inconsistent: `Project` and
  `project` both appear.*
- Allocate costs based on workload metrics

**Notes**
> Cost Explorer works and one anomaly monitor exists. Resource tags are inconsistent (Name, Project,
> project, purpose) and not activated as cost allocation tags. Cost per customer or per endpoint is
> not yet allocated. Standardising tag keys and activating them is planned.

## COST 4. How do you decommission resources?

**TICK**
- Enforce data retention policies. *Row-level TTL on cache and telemetry tables; 54 of 62 log groups
  retain 90 days.*

**LEAVE UNTICKED**
- Track resources over their life time
- Implement a decommissioning process
- Decommission resources
- Decommission resources automatically

**Notes**
> Data retention is automated through TTL and log retention; eight log groups still have no retention
> period set. There is no resource inventory or decommissioning process. A scheduled function that has
> failed on every run for at least a week, and an unrelated legacy deployment bucket, have been
> identified for review.

## COST 5. How do you evaluate cost when you select services?

**TICK**
- Identify organization requirements for cost. *Pay-per-use at low volume.*
- Select software with cost effective licensing. *Open-source runtime and libraries.*
- Select components of this workload to optimize cost in line with organization priorities
- Perform cost analysis for different usage over time. *The SIM swap monitor cadence was costed at
  hourly and four-hourly against the enrolled-user count.*

**LEAVE UNTICKED**
- Analyze all components of the workload
- Perform a thorough analysis of each component

**Notes**
> Serverless, on-demand services were chosen so cost tracks use. Third-party per-call costs are analysed
> case by case when they surface (for example a scheduled lookup job was found to run six times more
> often than documented and was moved to four-hourly). A systematic per-component cost analysis has not
> been done.

## COST 6. How do you meet cost targets when you select resource type, size and number?

**TICK**
- Select resource type, size, and number automatically based on metrics. *Lambda and DynamoDB
  on-demand scale without selection.*

**LEAVE UNTICKED**
- Perform cost modeling
- Select resource type, size, and number based on data. *Lambda memory has not been tuned against
  duration.*

**Notes**
> Compute and database capacity are not provisioned, so there is nothing to over-provision. Lambda
> memory settings have not been tuned against measured duration and cost, and arm64 has not been
> evaluated. No cost model exists.

## COST 7. How do you use pricing models to reduce cost?

**LEAVE UNTICKED**
- Perform pricing model analysis
- Implement regions based on cost
- Select third-party agreements with cost-efficient terms
- Implement pricing models for all components of this workload

**Notes**
> All components run on-demand, which suits current low volume, and no Savings Plans or reserved
> capacity are in use. A pricing-model analysis has not been done and will be when monthly spend is
> large enough to justify it. Single Region (us-east-1).

## COST 8. How do you plan for data transfer charges?

**TICK**
- Select components to optimize data transfer cost. *No VPC and no NAT gateway, so no NAT data
  processing charges.*
- Implement services to reduce data transfer costs. *Static pages are served from Cloudflare.*

**LEAVE UNTICKED**
- Perform data transfer modeling

**Notes**
> Single Region with no cross-Region replication, no NAT gateway and no VPC endpoints needed. Static
> sites are served from a CDN. Data transfer has not been modelled.

## COST 9. How do you manage demand, and supply resources?

**TICK**
- Perform an analysis on the workload demand. *Seven-day invocation, error and throttle analysis, and
  per-source usage analysis.*
- Implement a buffer or throttle to manage demand. *Usage plan, per-key and per-source caps, budgets.*
- Supply resources dynamically. *Serverless; constrained by the concurrency quota, see REL 1.*

**Notes**
> Demand is throttled in layers: API Gateway usage plan, per-key hourly and per-source daily caps,
> and a daily budget on the shared upstream key. Supply is dynamic but capped by the account
> concurrency quota of 10, for which a raise to 1,000 has been requested.

## COST 10. How do you evaluate new services?

**TICK**
- Review and analyze this workload regularly. *Daily drift check, weekly metrics report, and this
  review.*

**LEAVE UNTICKED**
- Develop a workload review process

**Notes**
> The workload is reviewed continuously through a daily deployed-versus-source drift check, a weekly
> metrics report and read-only diagnostic scripts per failure class. A formal architecture review
> cadence is not defined.

## COST 11. How do you evaluate the cost of effort?

**TICK**
- Perform automations for operations. *CI deploys, drift detection, scheduled jobs, diagnostic
  scripts.*

**Notes**
> Deployments, drift detection and routine operations are automated through GitHub Actions and
> scheduled Lambda jobs. Read-only diagnostic scripts are committed for each failure class so
> investigations are repeatable.

---

# SUSTAINABILITY

## SUS 1. How do you select Regions to support your sustainability goals?

**LEAVE UNTICKED**
- Choose Region based on both business requirements and sustainability goals

**Notes**
> Single Region, us-east-1, chosen for service availability and proximity to customers. Regional
> carbon intensity has not been compared. Sustainability is not yet a Region-selection input.

## SUS 2. How do you align cloud resources to your demand?

**TICK**
- Scale infrastructure to continually match demand. *Serverless and on-demand; nothing idles.*

**LEAVE UNTICKED**
- Align SLAs with sustainability goals. *No SLAs defined.*
- Stop the creation and maintenance of unused assets
- Optimize geographic placement of workloads based on their networking requirements

**Notes**
> There are no always-on servers: Lambda, API Gateway and on-demand DynamoDB use capacity only while
> serving requests. Unused assets have been identified (a scheduled function failing on every run and a
> legacy deployment bucket) and are scheduled for review.

## SUS 3. How do you take advantage of software and architecture patterns to support your sustainability goals?

**TICK**
- Optimize software and architecture for asynchronous and scheduled jobs. *Batch work runs on
  EventBridge schedules; an hourly job was moved to four-hourly (CONDITIONAL, see the table).*
- Use software patterns and architectures that best support data access and storage patterns. *Key
  lookups, caches and TTL expiry.*

**LEAVE UNTICKED**
- Remove or refactor workload components with low or no use
- Optimize areas of code that consume the most time or resources

**Notes**
> Background work is scheduled rather than polled, and caches avoid repeating expensive upstream calls.
> A review of scheduled-job frequency found one running six times more often than needed, now corrected.
> Low-use components have not been systematically reviewed and code has not been profiled.

## SUS 4. How do you take advantage of data management policies and patterns to support your sustainability goals?

**TICK**
- Use technologies that support data access and storage patterns
- Use policies to manage the lifecycle of your datasets. *TTL and log retention; gaps noted.*
- Back up data only when difficult to recreate. *Point-in-time recovery is enabled only on tables that
  hold customer state or irreplaceable evidence; caches are excluded.*
- Minimize data movement across networks. *Single Region.*
- Remove unnecessary or redundant data. *TTL-based expiry.*

**LEAVE UNTICKED**
- Implement a data classification policy. *Not written.*

**NOT APPLICABLE** (use the drop-down)
- Use shared file systems or storage to access common data
- Use elasticity and automation to expand block storage or file system. *No block or file storage.*

**Notes**
> Datasets have lifecycle rules where they are ephemeral (TTL on caches and telemetry, 90-day log
> retention on 54 of 62 groups) and backups are deliberately limited to data that cannot be regenerated.
> Eight log groups and four of five S3 buckets have no lifecycle rule. There is no written data
> classification scheme.

## SUS 5. How do your hardware management and usage practices support your sustainability goals?

**TICK**
- Use the minimum amount of hardware to meet your needs. *No dedicated or always-on hardware.*
- Use managed services

**LEAVE UNTICKED**
- Use instance types with the least impact. *All functions are x86_64; Graviton not adopted.*

**NOT APPLICABLE** (use the drop-down)
- Optimize your use of hardware-based compute accelerators. *No accelerators.*

**Notes**
> All compute is managed serverless. Functions run on x86_64; arm64 (lower energy per request) has not
> been evaluated and is on the improvement list alongside right-sizing.

## SUS 6. How do your organizational processes support your sustainability goals?

**TICK**
- Keep your workload up-to-date. *Current runtimes; dependency audit on every push.*
- Increase utilization of build environments. *Shared, ephemeral CI runners; deploys rebuild only the
  functions a push changed.*

**LEAVE UNTICKED**
- Adopt methods that can rapidly introduce sustainability improvements

**NOT APPLICABLE** (use the drop-down)
- Use managed device farms for testing. *No device farm; the mobile app is tested on developer devices.*

**Notes**
> Dependencies and runtimes are kept current and CI is ephemeral and change-scoped. There is no explicit
> sustainability review step in the change process.

---

## What these 22 answers expose, in the order worth fixing

1. **Budget** (`tools/create_cost_budget.sh --apply`): unlocks two COST 1 ticks. Cheap, 2 minutes.
2. **Failing scheduled job** (`tools/grant_gas_monitor_kms.sh`): removes a COST 4 / SUS 2 finding and 2,021
   errors a week.
3. **Tag standardisation** (`Project` vs `project`): unlocks COST 3.
4. **Log retention on the 8 groups with none**, and a lifecycle rule on the config-logs bucket: SUS 4, COST 4.
5. **arm64 and right-sizing trial** on the busiest functions: PERF 2, COST 6, SUS 5. Needs the concurrency
   quota raised first so a trial does not throttle production.
6. **A load test and tracing**: PERF 5 and REL 7. Also blocked on the quota.
