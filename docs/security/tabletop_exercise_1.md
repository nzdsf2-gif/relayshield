# Tabletop Exercise 1: leaked AWS access key

| | |
|---|---|
| **Status** | **NOT HELD, and deliberately waiting until both participants have been spoken to.** This is the script and the record form. The practice "Run simulations" is met only by a dated record below that a person actually filled in |
| **Length** | About 45 minutes |
| **Part of** | `relayshield_incident_response_plan.md` v1.1, section 9; WAFR SEC 10 |

## What a tabletop is

Nobody touches AWS. One person reads the scenario aloud, one step at a time. The Incident Commander says what they would do,
who they would call and which playbook they would open. A scribe writes down every hesitation, every "I don't know where
that is" and every place the plan was wrong. The findings are the point. A tabletop with no findings was not run properly.

## People

| Role | Who | Does |
|---|---|---|
| Incident Commander | Andrew Gibbs | answers as he would in a real incident |
| Facilitator | any person, or Claude in chat, but a person must be present | reads the injects, holds the clock, does not answer for the Commander |
| Scribe | the backup contact | writes the timeline and the findings |
| Legal counsel | the attorney named in the private contact sheet | joins for injects 5 and 6, or is phoned in the exercise |

CONFIRM both are willing to take these roles, and that counsel has signed the role acknowledgment, before the date is set.

## Rules

Use only the documents that exist: the incident plan, `docs/security/incident_playbooks.md`, `docs/security/forensics_plan.md`.
Do not open AWS to look something up. If the answer is not in the documents, that is a finding. Say what you would do, not what
you know the answer to be.

## The scenario and injects

Read one inject, stop, let the Commander respond, write it down, then read the next.

1. **Monday 09:10.** A security researcher emails relayshieldadmin: an AWS access key beginning AKIA was in a public GitHub
   repository for three days. They give the key id and the repo. *Questions: Severity? Which playbook? What is the first action?
   Is it capture first or contain first?*
2. **09:25.** You confirm the key belongs to an IAM user used by a deploy script. *Question: how do you find which user, and what
   can that user do? Where is that written down?*
3. **09:40.** CloudTrail shows the key calling `ListBuckets` and `GetObject` from an IP in another country, nine hours ago. *Questions:
   what evidence do you save before disabling the key? What do you run? Where does it go?*
4. **10:00.** The key also called `UpdateFunctionCode` on one Lambda yesterday. *Questions: how do you tell whether the live code is
   what is in git? What do you roll back to?*
5. **10:30.** One of the S3 objects read contains customer records. *Questions: is notification required? Within what time? Who do you
   call first and what do you ask them?* (Legal counsel joins here.)
6. **11:00.** A customer emails: "I got a strange message pretending to be you." *Questions: related or not? What do you tell them?
   Who writes it and where does the wording come from?*
7. **11:20.** You cannot reach Andrew's phone. *Question: what does the backup contact do and not do? Who can act in AWS?*
8. **End.** *Question: what would you write in the post-incident review? What would you change in the plan?*

## Success criteria

The exercise passes if, using only the documents: the Commander captured evidence before containing, disabled the key and revoked
sessions, found the changed Lambda and rolled it back, made a notification decision with a deadline, and reached counsel. Failing
a criterion is a finding, not a failed exercise.

## RECORD (fill in after the exercise; one copy per exercise, kept under `docs/security/`)

| Field | Entry |
|---|---|
| Date and start/end time | |
| Participants and roles | |
| Facilitator | |
| Documents used | |
| Did the Commander capture before containing? | |
| Time to first correct action (minutes) | |
| Notification decision made, and the deadline stated | |
| Findings (each one: what was missing or wrong) | |
| Plan or playbook changes made because of the findings (file and commit) | |
| Findings still open, with owner and date | |
| Signed (Incident Commander) | |

## After

1. Fix every finding in the plan or playbooks in the same week, and cite the commit in the record.
2. Hold the next exercise within 12 months, with a different scenario (Lambda code replaced; Stripe or Twilio compromise).
3. Tick the WAFR practice only after the record above is filled in and committed.
