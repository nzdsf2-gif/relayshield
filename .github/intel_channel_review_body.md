This issue is auto-generated on the 1st of every month by
`.github/workflows/intel_channel_review.yml`. Review channel performance and
update `MONITORED_CHANNELS` in `relayshield_intel_monitor.py` before closing.

### Checklist

- [ ] Review channels with zero IOC hits in the last 30 days, consider replacing
- [ ] Check whether any channels went private or were deleted (Telethon join errors in the logs)
- [ ] Search for newly active criminal channels to add (sim swap, credential dumps, infostealers, crypto drainers)
- [ ] Verify the 4 confirmed-accessible channels are still live: `@exposed_vc`, `@logsmarket`, `@cloudsek_alerts`, `@vxunderground`
- [ ] Cross-check against `tools/triage_channels.py --pending` before adding anything by hand
- [ ] Update `MONITORED_CHANNELS` if needed, commit, and redeploy

### Resources

- [CloudWatch log groups](https://us-east-1.console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups)
- [relayshield_intel_monitor.py](../blob/main/relayshield_intel_monitor.py)
- [DynamoDB tables](https://us-east-1.console.aws.amazon.com/dynamodbv2/home?region=us-east-1#tables)
