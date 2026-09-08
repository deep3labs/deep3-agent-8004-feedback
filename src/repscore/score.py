from collections import defaultdict
from collections.abc import Iterable

from .curve import curve, decode, disagreement, mean, to_2dp, weighted_mean


def _row_ranked(score_frac, comparative_reviewers, nc, reviewer_differentiation_frac, num_reviewers):
    return {"band": "RANKED", "score": to_2dp(score_frac),
            "comparative_reviewers": comparative_reviewers, "non_comparative_reviewers": nc,
            "reviewer_differentiation": to_2dp(reviewer_differentiation_frac * 100),
            "num_reviewers": num_reviewers}


def _row_insufficient(nc):
    return {"band": "INSUFFICIENT_COMPARATIVE_DATA", "score": None,
            "comparative_reviewers": 0, "non_comparative_reviewers": nc,
            "reviewer_differentiation": None, "num_reviewers": nc}


def score(records: Iterable[tuple[str, str, int, int, str]]) -> tuple[dict, dict]:
    collapsed = defaultdict(list)
    for rater, ratee, value, decimals, tag in records:
        if rater == ratee:
            continue
        collapsed[(rater, ratee, tag)].append(decode(value, decimals))
    val = {key: mean(vs) for key, vs in collapsed.items()}

    by_rater_tag = defaultdict(dict)
    for (rater, ratee, tag), v in val.items():
        by_rater_tag[(rater, tag)][ratee] = v

    comp = defaultdict(dict)                            # (ratee, tag) -> {rater: (view, reviewer_differentiation)}
    nc_tag = defaultdict(set)
    for (rater, tag), ratee_vals in by_rater_tag.items():
        ratees = list(ratee_vals)
        vals = [ratee_vals[a] for a in ratees]
        if len(set(vals)) < 2:
            for a in ratees:
                nc_tag[(a, tag)].add(rater)
            continue
        rq = disagreement(vals)
        for a, view in zip(ratees, curve(vals), strict=True):
            comp[(a, tag)][rater] = (view, rq)

    tag_scores = defaultdict(dict)
    meta = {}
    keys = set(comp) | set(nc_tag)
    for (a, tag) in sorted(keys):
        contribs = comp.get((a, tag), {})
        nc = len(nc_tag.get((a, tag), ()))
        if contribs:
            tag_scores[tag][a] = weighted_mean((rq, view) for (view, rq) in contribs.values())
            meta[(a, tag)] = (len(contribs), nc, mean([rq for (_, rq) in contribs.values()]))
        else:
            meta[(a, tag)] = (0, nc, None)

    tag_differentiation = {tag: disagreement(list(scores.values())) for tag, scores in tag_scores.items()}

    by_tag = {}
    for (a, tag), (n_comp, nc, rq_mean) in meta.items():
        if n_comp >= 1:
            by_tag[(a, tag)] = _row_ranked(tag_scores[tag][a], n_comp, nc, rq_mean, n_comp + nc)
        elif nc >= 1:
            by_tag[(a, tag)] = _row_insufficient(nc)

    agent_tags = defaultdict(dict)
    for tag, scores in tag_scores.items():
        for a, s in scores.items():
            agent_tags[a][tag] = s

    comp_by_agent = defaultdict(lambda: defaultdict(list))
    for (a, _tag), contribs in comp.items():
        for rater, (_view, rq) in contribs.items():
            comp_by_agent[a][rater].append(rq)
    nc_by_agent = defaultdict(set)
    for (a, _tag), raters in nc_tag.items():
        nc_by_agent[a] |= raters

    by_agent = {}
    for a in sorted({a for (a, _t) in keys}):
        comp_qs = comp_by_agent.get(a, {})
        nc_only = nc_by_agent.get(a, set()) - set(comp_qs)
        n_comp = len(comp_qs)
        if n_comp >= 1:
            overall = weighted_mean((tag_differentiation[tag], s) for tag, s in agent_tags[a].items())
            rq_mean = mean([mean(rqs) for rqs in comp_qs.values()])
            num_reviewers = len(set(comp_qs) | nc_only)
            by_agent[a] = _row_ranked(overall, n_comp, len(nc_only), rq_mean, num_reviewers)
        elif nc_only:
            by_agent[a] = _row_insufficient(len(nc_only))
    return by_tag, by_agent
