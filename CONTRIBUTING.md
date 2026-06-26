# Contributing & sourcing standards

This database lives or dies on accuracy. Every entry must be verifiable by a
reader who follows the links. Please follow these rules.

## The one hard rule

**No claim without a source.** If you can't cite it, don't publish it. Mark the
field `"verified": false` and leave `sources` empty until a citation exists.

## Acceptable sources

Ranked roughly by strength:

1. **Primary records** — Hansard (parliamentary debate/votes), AEC disclosure
   returns, the candidate's own published platform, official APH profiles, court
   or AEC eligibility rulings.
2. **Direct statements** — the candidate's official website, verified social
   media, recorded interviews, media releases.
3. **Reputable reporting** — established news outlets, used to point back to a
   primary statement or vote.

Avoid: anonymous claims, unverified screenshots, opinion pieces presented as
fact, or anything you can't link to.

## What we record — and what we don't

- **Do** record: stated policy positions, recorded votes, public statements of
  faith, disclosed donations (AEC), and Section 44 eligibility status.
- **Don't** record: ethnicity, ancestry, national origin, or heritage; inferred
  private beliefs; or any aggregate "loyalty"/ideology score. We summarise what
  someone has said or done and let readers judge.

### The two sensitive fields

- **Citizenship** is recorded *only* as Section 44 constitutional eligibility —
  e.g. "Confirmed sole citizen" or "Renounced UK citizenship on 2017-08-01 per
  AEC". It is never a heritage flag.
- **Foreign policy** records actual positions and votes (including foreign aid
  and Middle East policy). State the position and link the source; do not grade
  it.

## Adding a candidate

1. Copy `data/candidate.template.json`.
2. Give it a unique `id` slug (e.g. `jane-smith-wills`).
3. Fill only the fields you can source. Set `"verified": true` on a position
   *only* when its `summary` is fully supported by the listed `sources`.
4. Validate against `data/schema.json` before committing.
5. Update `last_updated`.

## Corrections

Found something wrong or stale? Open an issue with a better source, or submit a
change that swaps in the correct citation. Corrections backed by a stronger
source always win.
