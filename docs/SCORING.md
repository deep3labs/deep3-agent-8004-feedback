# ERC-8004 reputation scoring: methodology

`repscore` turns on-chain ERC-8004 feedback into per-agent reputation scores with **one deterministic
algorithm that adds no opinion of its own**. An agent's number is a function of reviewers' data alone. There is **no
neutral prior, no default value, and no operator-tunable constant in the scorer**; nothing pulls a score toward a chosen
number, and no threshold decides a review is "not good enough." Any third party reproduces every
published number bit-for-bit from the same inputs; `docs/CONTRACT.md` lists them under Reproducibility / provenance.

## Three operations, nothing else
1. **Normalize**: decode each on-chain value as `value / 10^decimals` in exact rational arithmetic;
   repeat ratings by one reviewer of the same agent and dimension (one curated concept reviewers rate on, identified by a `clean_tag` id) are averaged into one.
2. **Relativize**: within each reviewer's ratings in a dimension, replace values by their **rank** on
   0–100 (ties share the average rank; by construction an n-rating ballot's positions lie between
   50/n and 100 − 50/n inclusive).
   This is the only interpretation the scorer makes: a score means "where
   this agent placed among the peers a reviewer compared it against."
3. **Aggregate**: combine those ranked values, each one a reviewer's **view** of an agent, by **weighted means**. Every weight is self-derived from
   the data (below); the result always lies within the range of its inputs, because no prior is added.

## The two weights (both the same statistic)
Both levels use one objective statistic, **pairwise disagreement**: *the fraction of
pairs that differ* in a set of numbers, always in [0, 1] (all distinct → 1, all identical → 0):

- **Reviewer differentiation**, the per-reviewer weight, scales each reviewer's view by the disagreement of **that reviewer's own
  ratings**. A reviewer who rated two or more agents without repeating a rating counts fully; the weight falls with the share
  of their rating pairs that repeat, and one who marks every agent the same gets zero weight. It is a rate over pairs, so it
  is **volume-independent**: rating two agents differently scores 1.0.
- **Tag differentiation** weights each dimension in the overall score by the disagreement of **that dimension's
  per-agent scores** (distinctness is judged on the exact values, before rounding). A dimension whose per-agent scores
  are distinct (it discriminates) counts fully; one where every agent lands on the same score gets zero weight.

## Three levels
- **rating → view**: rank each reviewer's values within a `clean_tag`.
- **agent × clean_tag**: the reviewer-differentiation-weighted mean of that agent's views in the dimension.
- **agent overall**: the tag-differentiation-weighted mean of the agent's per-dimension scores.

In symbols, for a reviewer's ballot of $n$ ratings in one dimension, where $c_v$ is how many of the $n$ ratings equal value $v$, and an agent at average rank $r$ (ties share the average of their ranks):

$$
x = 100 \cdot \frac{r - \tfrac{1}{2}}{n}, \qquad d = 1 - \frac{\sum_v c_v (c_v - 1)}{n(n-1)}
$$

$$
\text{score}_{a,k} = \frac{\sum_i d_i \, x_i}{\sum_i d_i}, \qquad
\text{overall}_a = \frac{\sum_k W_k \, \text{score}_{a,k}}{\sum_k W_k}, \qquad
W_k = d\big(\{\text{score}_{a,k}\}_a\big)
$$

$x$ is the reviewer's view of the agent and $d_i$ that reviewer's differentiation; the $i$ sum runs over the agent's comparative reviewers in dimension $k$, the $k$ sum over the dimensions the agent has a score in, and $W_k$ is the same $d$ applied to the scores of every agent scored in dimension $k$. $d$ is defined as 0 for fewer than 2 values. If every $W_k$ is 0 the overall score is the plain mean of the per-dimension scores.

## What the scorer outputs
Two tables, one per agent and one per (agent × clean_tag), each row carrying a **band**, three plain reviewer
**counts** and, for RANKED rows, a **score** and a 0–100 rate; none of the counts or the rate is a probability
that the score is correct:
**comparative_reviewers** (distinct reviewers whose comparisons set the score), **non_comparative_reviewers**,
**reviewer_differentiation** (0–100, the mean over the comparative reviewers behind the score of each one's
differentiation; on a by-agent row a reviewer spanning several dimensions contributes the mean of their per-dimension
values, so breadth never counts twice), and **num_reviewers** (total distinct reviewers). On every row the two reviewer classes partition
`num_reviewers`; on a by-agent row a reviewer comparative in any of the agent's dimensions counts once, as comparative.

- **RANKED** (≥ 1 comparative reviewer): a 0–100 score. A score is published even when only one comparative reviewer
  stands behind it; there is no minimum gate, because any such threshold would be an injected opinion.
  A thin score is reported with `comparative_reviewers` and `num_reviewers` beside it; the consumer judges.
- **INSUFFICIENT_COMPARATIVE_DATA**: an agent with only non-comparative feedback (every reviewer rated
  it alone or gave all-equal values); no comparison exists to rank, so it is shown as a reviewer count
  with **no number**.
- **Absent**: none of its feedback was scoreable; no row at all.

RANKED and INSUFFICIENT rows are **not co-rankable**: sort/threshold the 0–100 axis only within RANKED.

A hypothetical illustration of the partition rule above, with one agent, two dimensions, two reviewers. Reviewer P rated the agent and at least one other agent with differing values in `accuracy` but gave every agent the same mark in `availability`; reviewer Q rated the agent alone, in `availability` only:

| Row | band | comparative_reviewers | non_comparative_reviewers | num_reviewers |
|---|---|---|---|---|
| agent × `accuracy` | RANKED | 1 (P) | 0 | 1 |
| agent × `availability` | INSUFFICIENT_COMPARATIVE_DATA | 0 | 2 (P, Q) | 2 |
| agent overall | RANKED | 1 (P) | 1 (Q) | 2 |

P is non-comparative in one dimension and comparative in another, so the per-dimension non-comparative count in `availability` (2) exceeds the by-agent count (1); on the by-agent row P counts once, as comparative.

## What the scorer deliberately does not do
The scorer makes no judgment about a reviewer's trustworthiness, and a reviewer's contribution is never inflated by volume.
The only non-arbitrary bound in the scorer is that a
**comparison requires ≥ 2 agents rated with ≥ 2 distinct values**. That is arithmetic: you cannot
rank fewer.

## Accepted limitations
Scoring observational data is inherently imperfect; the scorer reports what the data supports and leaves the
flaws visible.
- **A single reviewer sets a single-reviewer agent's score**: it sits wherever that one ballot places it. There is
  no sybil *bound*, meaning nothing caps how much one actor using many wallets can move a score; sybil resistance is left to **transparency**: `comparative_reviewers` and
  `num_reviewers` expose thin or lopsided support (crude review-padding can show as a huge `num_reviewers` with a tiny
  `comparative_reviewers`), and the consumer decides. Requiring reviewers to post a deposit, or to prove they are
  human, at submission would bound it; both are outside this library.
- **Reviewer differentiation is noisier for very small ballots**: with only 2–4 ratings, one repeated value
  moves the rate a lot; smoothing it would require a prior, which the design rejects.
- **Scores are relative to happenstance peers**: an agent is ranked only against the other agents a
  reviewer happened to also rate, so compare scores built on very different peer sets with care.
- **Self-review is not excluded.** Raters are wallet addresses and ratees are agent identity strings (agentIds or CAIP-19 keys), so
  the literal `rater == ratee` guard cannot fire on data written that way. Detecting an agent's controller rating
  its own agentId would require resolving controller wallets to agentIds, which this library does not do.
- **Tag consolidation is not objective** and is out of scope for the no-injected-opinion claim: deciding which
  raw `tag1` values are one concept is editorial,
  human-in-the-loop, and carried in the map file itself; `tagmap_hash` covers that content. Whether a tag no dimension claims
  is awaiting a decision or has been ruled out is editorial too, and is not published. Either way it is left out
  entirely; scoring happens only under curated dimension ids.

## Determinism / auditability
All arithmetic is exact integer/rational (`fractions.Fraction`); the only rounding is the final
half-to-even to 2 decimals. `decode = value / 10^decimals` and every comparison is exact; a float
implementation would collide distinct on-chain values and publish different numbers. Every row
`scripts/run_score.py` writes carries `repscore_version` and `tagmap_hash` (the hash of the tag map's dimension ids
and spellings; exact form in `docs/CONTRACT.md`). They identify the run. Reproducing the row needs the tag map file,
the scorer that produced it, and the on-chain records; `docs/CONTRACT.md` lists them under Reproducibility / provenance.
There is no further stamp because there is no operator-tunable constant in the scorer.
One documented fallback: a dimension's weight is zero when it has fewer than two scored agents or every agent scored in it landed on the same score; if ALL of an agent's dimensions have zero weight, its overall score is the
plain mean of its per-dimension scores, still within the range of its inputs. Per-dimension scores never reach this case: a
reviewer weight is only computed from a ballot that already expressed a comparison, so it is always > 0.

## Provenance
The design was reached by removal, over several rounds of adversarial review of the alternatives. What was tried, and
why each was dropped:

- **A first version built on within-dimension percentiles, one identity one vote, the median across a reviewer's peers,
  and a minimum of two independent reviewers.** Superseded after adversarial review. Its tag-merging decisions survive in
  the maps Deep3 Labs publishes; its scoring arithmetic does not.
- **Dimension weights from percentile dispersion, damped by n/(n+10).** Dropped: the damping constant is a number chosen by
  hand, which the design forbids, and the arithmetic failed adversarial review.
- **A reviewer weight taken from the spread of the reviewer's own ballot, with no upper bound.** Dropped: a two-record
  ballot (the target plus one decoy) maximizes that weight, so a single fabricated reviewer could place a fresh agent at
  the top of the range.
- **A neutral prior, `(K × 50 + Σ views) / (K + S)` with K = 5 phantom reviews at 50 and S distinct reviewers.** It bounded
  any single reviewer's influence, and it was dropped for that very mechanism: the phantom reviews, and 50 as "neutral",
  are opinions injected into every score. In its place the reviewer counts are published, so thin support is visible.
- **Alternative reviewer-weight statistics, compared on a set of real reviewer archetypes: the with-replacement
  Gini plug-in, Shannon evenness, and smoothed variants.** Dropped: the plug-in caps a two-rating ballot at 0.5, evenness
  rewards coarse two-valued ballots at scale, and smoothing needs a constant. Pairwise disagreement kept every wanted
  property without a constant.
- **A minimum-reviewer threshold before a score is published.** Dropped: any value of the threshold is a choice with no
  principled defence ("why 2 and not 3?"), so scores are published from one comparative reviewer with the counts beside them.

What remains is normalize, relativize, and self-derived weighted aggregation, with the limitations accepted above.
