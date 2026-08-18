# Draft reply to Miha Ambroz (n8n)

> Status: verified 2026-07-28. Rendered and measured on n8n 2.32.5 (current release at time of writing).
> Zero collisions, no clipped text, no node warnings. No placeholders remain. Ready to review and send.
> Scope: presentation only — that is what the audit rejected. Do not volunteer runtime/usability detail
> he did not raise.
> Attach: canvas screenshot + About-dialog screenshot showing 2.32.5. Optionally
> n8n_shadow_ai_gate_diagram.png for the structure overview.

---

**Subject:** Re: Template submission — Shadow AI & Vendor Approval Gate

Hi Miha,

Thank you for the direct feedback, and I'm sorry for the review burden. You were right to call it out, and I want to be specific about what went wrong rather than just apologise.

You told me more than once that the overlap was because I wasn't on the latest n8n. I treated that as context for the rejection rather than as the change you were asking me to make. I was authoring and checking these templates on n8n 2.26.6. The canvas looked correct to me every time, so each resubmission was made in good faith — but it was good faith on top of an environment you had already told me was the problem. That's my error, not an ambiguity in your feedback.

The second mistake compounded it. On the previous resubmission I "fixed" the overlap by editing the sticky note's height and position values in the workflow JSON and reasoning about the geometry, instead of importing the template into a current n8n and looking at the rendered canvas. So I was correcting coordinates against a mental model rather than against what your reviewers actually see. That is why the same problem survived three submissions.

What I've changed:

- I installed n8n 2.32.5, imported the template into a clean instance, and measured the actual rendered canvas. That immediately surfaced 10 real collisions that my previous method reported as clean — 8 of them between node **name labels**, which render outside the node box and bleed into the node beneath, and one where the webhook's label block (333px wide, far wider than its 96px icon) ran straight through the gap I'd left for the sticky note. That is what you were seeing, and it is invisible if you only look at node coordinates.
- I rebuilt the layout using the measured clearances rather than assumed ones: 240px between rows and the sticky note moved well clear of the widest label block. Re-measured on 2.32.5, the workflow now reports **zero collisions**, with a 37px tightest vertical gap and 80px tightest horizontal gap.
- I also found the overview sticky note was clipping its last line by 6px, so the final setup instruction was cut off in the render. Its height is corrected and the full text now displays.
- It remains the only sticky note in the workflow — no per-section grouping notes layered behind node clusters.
- Checking on 2.32.5 also surfaced two nodes rendering with error markers on import, from a misconfigured resource type on the Notion nodes. Those are corrected, so the template now imports with a completely clean canvas — no overlapping elements and no node warnings anywhere in the workflow.
- I've attached the workflow structure so you can see the shape I'm submitting up front: a webhook, one branch on `request_type`, seven checks, two result gates, five shared outputs.

Going forward I won't submit anything that I haven't first rendered and visually checked on the current release. If it still isn't right, I'd rather you tell me once and I fix it properly than have your team catch the same thing a fourth time.

On reaching out to Jon — understood, that was the wrong channel and it won't happen again. I'll keep everything in the standard review queue.

I appreciate you taking the time to spell this out instead of just closing the account.

Best regards,
Andrew Gibbs
RelayShield

---

## Notes for Andrew (not part of the email)

- Keep it short. He is not looking for a long explanation, he's looking for evidence the feedback landed.
- The Jon paragraph is optional — cut it if you'd rather not draw attention back to it, but leaving it in
  reads as accountable rather than defensive.
- Attach the canvas screenshots. The specific thing that rebuilds trust here is showing the render, since
  "I checked and it looks fine" is exactly what failed the last three times.
