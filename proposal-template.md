# Proposal template

Most proposals are ignored because they talk about the freelancer. This one talks about the job. Keep it under 150
words. Never open with "Dear Hiring Manager" or "I am excited about this opportunity."

---

## The template

> [ONE SENTENCE PROVING YOU READ THE POST — restate their actual problem,
> including a specific detail only someone who read it would mention.]
>
> [ONE OR TWO SENTENCES ON HOW YOU'D DO IT — name the approach concretely.
> "I'd write a Python script that walks the export, normalizes the date
> columns, and flags rows where a value is missing rather than defaulting it
> to zero."]
>
> [ONE LINE OF RELEVANT PROOF — the closest thing you've actually built.]
>
> [ONE SPECIFIC QUESTION about their data or requirements. This gets replies
> more than anything else in the message.]
>
> Happy to do a small paid test first if that's easier.
>
> — Ricky

---

## Worked example

Job post: "Need someone to clean up 4 years of sales exports. Dates are in three different formats and some rows are
duplicated."

> Three date formats across four years of exports usually means the source
> system changed twice — the duplicates are often the same order re-exported
> under a new ID rather than true duplicates.
>
> I'd write a Python script that normalizes all three date formats, then
> de-duplicates on a composite key rather than row equality so you don't lose
> legitimate repeat orders. You'd get the cleaned file plus the script, so you
> can re-run it on future exports yourself.
>
> I build parsers and data tooling — inconsistent formats are most of what I
> work on.
>
> Quick question: are the duplicate rows byte-identical, or do they differ in
> one or two fields? That changes the approach.
>
> Happy to do a small paid test first if that's easier.

---

## Rules

1. Apply within the first hour. Response rate collapses after that.
2. Bid on jobs with a verified payment method and prior hires only.
3. Skip anything with 50+ proposals already.
4. Ask a question every time. It converts a bid into a conversation.
5. Never lower your quality to match a low rate — the review is the asset.
