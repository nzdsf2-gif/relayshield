# Preparing for Tabletop Exercise 1

**Purpose.** The tabletop (`tabletop_exercise_1.md`) tests whether the plan works with only the documents. Several of its
questions also need facts about the account that live in AWS, not in a document. Gather those first, so the exercise finds
gaps in the plan and not gaps in your memory. Anything you find missing is a fix to make, not something to write into this
public repository.

**Time:** about 90 minutes in total, once. Do it before you speak with the participants if you like, so you can brief them.

## Step 1. Read, in this order (30 minutes)

1. `relayshield_incident_response_plan.md`, sections 2, 3, 5, 6 and 8.
2. `docs/security/incident_playbooks.md`, PB-1 and PB-2 in full, the rest skimmed.
3. `docs/security/forensics_plan.md`, sections 1, 3 and 4.

## Step 2. Run the inventory (10 minutes)

`sh tools/ir_prep_inventory.sh` prints the facts below. Keep the output private.

## Step 3. For each inject, know the answer before the day

| Inject | You must be able to say, without looking it up | Where the answer is |
|---|---|---|
| 1. Report of a leaked key | The severity you would assign, and why. That evidence is captured BEFORE the key is disabled. The first action | plan section 2; forensics plan section 1; PB-1 step 0 |
| 2. Whose key is it? | How to find the owner of a key id from the key id alone. What each user and key in your account can do | PB-1 step 2; inventory section 1 and 2 |
| 3. Foreign IP in CloudTrail | The exact capture command and what it saves. Where the copy goes. How far back CloudTrail can look, and whether anything reaches further | forensics plan sections 2 to 4; inventory section 3 |
| 4. Code changed | How you would tell live code from git. Which functions the rollback workflow can roll back and what you do for the rest. How to stop a function without deleting it | PB-2; inventory section 7 |
| 5. Customer records read | Whether notification is required for what was read (is it ciphertext, and could the key have been used). The deadline. The first call and the question you ask | plan section 6; PB-4 step 2; counsel |
| 6. Customer reports a strange message | How you decide it is related. Who writes the reply and the rule that it never names a vendor | plan section 6; the CLAUDE.md rule on third-party attribution |
| 7. You cannot be reached | What the backup contact does, and does not do. Who can act in AWS when you cannot | plan section 3; this is the one question the documents probably cannot yet answer, which is itself the finding |
| 8. Review | Where the review is written and what it must contain | plan section 5.5 |

## Step 4. Practise the two commands (20 minutes)

1. Run `tools/ir_capture_evidence.py` against a harmless target and verify the hashes (the commands are in the session
   where this was set up and in `forensics_plan.md` section 3).
2. Read PB-1 step 4 until you can say what the session-revoking deny policy does. It is the step people most often get wrong.

## Step 5. Test the responder role (10 minutes, not yet done)

The read-only role needs MFA to be assumed. Confirm you can actually assume it, with your normal sign-in, once. If you cannot,
that is a finding: access that exists on paper and fails in an incident is not pre-provisioned.

## Step 6. Before you set the date

- The attorney has signed the role acknowledgment, and the backup contact has agreed to their role.
- Both have the private contact sheet.
- Each has read inject 5 or inject 7, which is the part that concerns them, and nothing else.
