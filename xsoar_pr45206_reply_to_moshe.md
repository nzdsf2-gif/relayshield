# Draft reply — demisto/content PR #45206, to MosheEichler

**Status: DRAFT, pending founder approval. Not posted.**

Context: MosheEichler commented 2026-08-01T22:43:20Z saying comments are still unresolved, that the
changes may have been committed locally but not pushed, and gave as an example that "the first line
in the YAML file is still category instead of name or display."

That example is not correct at the PR head (`ecd5b9f01`) — verified through GitHub's own contents
API, not just a local clone. The file's first three lines are `name`, `display`, `category`. The
fixes were pushed in `1f9c0c49d` on 2026-07-30, four hours after the review. The threads simply
were never marked resolved, so each one still renders its original pre-fix hunk.

The reply below is deliberately scoped to only what Moshe raised.

---

## Reply text

Hi @MosheEichler — thanks for the nudge, and sorry for the confusion here.

The changes are pushed. They went up in `1f9c0c49d` on 30 July, and they're included in the merge
you made in `ecd5b9f`. Nothing is sitting locally on my side.

On the specific example — the YAML's first lines at the current head are:

```yaml
name: RelayShield
display: RelayShield
category: Data Enrichment & Threat Intelligence
```

`name` and `display` were moved above `category` as part of that commit.

I think I know what caused the mix-up, and it was my fault. I applied the review suggestions as a
normal commit rather than using the "Commit suggestion" button, so GitHub never auto-resolved any of
the threads. Because they're all still open, each one keeps displaying the original pre-fix snippet —
so scrolling the conversations shows the old code even though the file itself has changed. I've now
gone through and resolved the threads that are addressed, which should make the diff reflect reality.

If it's easier to confirm from the file directly rather than the threads, the head commit is
`ecd5b9f`.

The one item I still can't action myself is `check_docs_approved_label_job` — it needs the
`docs-approved` label added by a maintainer whenever the documentation looks right to you.

Happy to make any further changes.
