import os
import random
from fractions import Fraction
from pathlib import Path

import pytest

import repscore
from repscore import resolve_and_score
from repscore.curve import curve, disagreement, mean, to_2dp, weighted_mean
from repscore.score import score
from repscore.tagmap.schema import Resolver, TagSchema

F = Fraction


def _rec(rater, ratee, value, dec=0, tag="trust"):
    return (rater, ratee, value, dec, tag)


def test_curve_neutral_and_extremes():
    assert curve([F(7)]) == [F(50)]
    assert curve([F(3), F(3), F(3)]) == [F(50)] * 3
    assert curve([F(1), F(9)]) == [F(25), F(75)]
    assert curve([F(i) for i in range(10)])[-1] == F(100) - F(50, 10)


def test_curve_hazen_ties():
    c = curve([F(10), F(10), F(90)])
    assert c[0] == c[1] == F(100) * (F(3, 2) - F(1, 2)) / 3
    assert c[2] == F(100) * (F(3) - F(1, 2)) / 3


def test_disagreement_is_pairwise_and_volume_free():
    assert disagreement([F(1), F(2)]) == 1
    assert disagreement([F(5), F(5)]) == 0
    assert disagreement([F(1), F(1), F(2)]) == F(2, 3)
    assert disagreement([F(1), F(2), F(3)]) == 1
    assert disagreement([F(9)]) == 0
    assert disagreement([F(1), F(2), F(3), F(4)]) == 1
    assert disagreement([F(1), F(1), F(1), F(2)]) == F(1, 2)


def test_weighted_mean_has_no_prior():
    assert weighted_mean([(F(1), F(100)), (F(1), F(0))]) == 50
    assert weighted_mean([(F(3), F(100)), (F(1), F(0))]) == 75
    assert weighted_mean([(F(1), F(100))]) == 100
    assert weighted_mean([(F(0), F(100)), (F(0), F(0))]) == 50


def test_mean_never_median_and_rounding():
    assert mean([F(5), F(5), F(99)]) == F(109, 3)
    assert to_2dp(F(109, 3)) == "36.33"
    assert to_2dp(F(5, 2)) == "2.50"
    assert to_2dp(F(2125, 1000)) == "2.12"
    assert to_2dp(F(2135, 1000)) == "2.14"


def test_no_prior_single_reviewer_shows_raw_view():
    recs = [_rec("A", "X", 90), _rec("A", "Y", 10)]
    by_tag, by_agent = score(recs)
    assert by_agent["X"]["band"] == "RANKED" and by_agent["X"]["comparative_reviewers"] == 1
    assert by_agent["X"]["score"] == "75.00"
    assert by_agent["Y"]["score"] == "25.00"
    assert by_tag[("X", "trust")]["score"] == "75.00"


def test_rows_carry_new_fields():
    recs = [_rec("A", "X", 90), _rec("A", "Y", 10)]
    r = score(recs)[1]["X"]
    assert set(r) == {"band", "score", "comparative_reviewers", "non_comparative_reviewers",
                      "reviewer_differentiation", "num_reviewers"}
    assert r["reviewer_differentiation"] == "100.00"
    assert r["num_reviewers"] == 1


def test_selfvote_dropped_noncomparative_separated():
    recs = [_rec("A", "A", 100),
            _rec("A", "X", 90), _rec("A", "Y", 10),
            _rec("B", "X", 100)]
    _, by_agent = score(recs)
    assert "A" not in by_agent
    assert by_agent["X"]["non_comparative_reviewers"] == 1
    assert by_agent["X"]["comparative_reviewers"] == 1
    _, ba2 = score([_rec("B", "Z", 100)])
    assert ba2["Z"]["band"] == "INSUFFICIENT_COMPARATIVE_DATA"
    assert ba2["Z"]["score"] is None and ba2["Z"]["num_reviewers"] == 1 and ba2["Z"]["reviewer_differentiation"] is None


def test_reviewer_differentiation_weights_the_views():
    recs = [_rec("A", "X", 100), _rec("A", "Y", 0),
            _rec("B", "X", 100), _rec("B", "Z", 100), _rec("B", "W", 0)]
    _, by_agent = score(recs)
    vA = curve([F(100), F(0)])[0]
    vB = curve([F(100), F(100), F(0)])[0]
    qB = disagreement([F(100), F(100), F(0)])
    expect = to_2dp(weighted_mean([(F(1), vA), (qB, vB)]))
    assert by_agent["X"]["score"] == expect
    assert by_agent["X"]["score"] != to_2dp(mean([vA, vB]))


def test_tag_differentiation_weights_the_dimensions():
    recs = [_rec("R", "X", 100, tag="a"), _rec("R", "Y", 0, tag="a"),
            _rec("R", "X", 100, tag="b"), _rec("R", "Y", 100, tag="b"), _rec("R", "Z", 0, tag="b")]
    _, by_agent = score(recs)
    xa = curve([F(100), F(0)])[0]
    bviews = curve([F(100), F(100), F(0)]); xb = bviews[0]
    tq_a = disagreement([xa, curve([F(100), F(0)])[1]])
    tq_b = disagreement(list(bviews))
    assert tq_a != tq_b
    assert by_agent["X"]["score"] == to_2dp(weighted_mean([(tq_a, xa), (tq_b, xb)]))


def test_resolve_and_score_consolidates_tags():
    resolver = Resolver(TagSchema(clean_tags={"trust": ["trust", "trust_score"]}))
    raw = [("A", "X", 90, 0, "trust_score"), ("A", "Y", 10, 0, "trust")]
    by_tag, by_agent = resolve_and_score(raw, resolver)
    assert ("X", "trust") in by_tag and by_agent["X"]["band"] == "RANKED"
    bt, ba = repscore.score(list(repscore.resolve_records(raw, resolver)))
    assert ba == by_agent and bt == by_tag


def test_curve_exact_no_false_ties():
    big = 10 ** 30
    c = curve([F(big), F(big + 1), F(3 * big)])                   # float64 would tie the first two
    assert c[0] != c[1]


def test_agent_key_caip19_slash_form_flows_through():
    assert repscore.agent_key(8453, 123456789) == "eip155:8453/erc721:0x8004A169FB4a3325136EB29fA0ceB6D2e539a432/123456789"
    assert repscore.agent_key(1, "987654321").startswith("eip155:1/erc721:0x8004A169FB4a3325136EB29fA0ceB6D2e539a432/")
    assert repscore.agent_key(8453, 1) != repscore.agent_key(1, 1)
    k = repscore.agent_key(8453, 123456789)
    _, by_agent = score([("A", k, 90, 0, "trust"), ("A", "X", 10, 0, "trust")])
    assert k in by_agent and by_agent[k]["band"] == "RANKED"


def test_schema_stamp_deterministic():
    s1 = repscore.schema_stamp({"trust": ["a", "b"], "speed": ["c"]})
    s2 = repscore.schema_stamp({"speed": ["c"], "trust": ["a", "b"]})
    assert s1 == s2 and s1["repscore_version"] == repscore.__version__ and len(s1["tagmap_hash"]) == 64


def test_pending_and_empty_records_are_not_scored(tmp_path):
    import yaml
    (tmp_path / "tag_schema.yaml").write_text(yaml.safe_dump(
        {"clean_tags": {"trust": ["trust", "Trust Score"], "speed": ["speed"]}}))
    r = repscore.load_schema(tmp_path / "tag_schema.yaml")
    assert r.status("trust_score") == "member" and r.status("brand-new") == "pending"
    assert r.status("\n\t") == "empty"
    records = [("A", "X", 90, 0, "trust"), ("A", "Y", 10, 0, "Trust Score"),
               ("A", "X", 5, 0, "brand-new"), ("A", "Y", 99, 0, "brand-new"),
               ("A", "X", 1, 0, "x402"), ("B", "X", 7, 0, "get top 1 rank >"), ("B", "Y", 1, 0, "")]
    by_tag, by_agent = repscore.resolve_and_score(records, r)
    assert set(by_tag) == {("X", "trust"), ("Y", "trust")}
    assert by_agent["X"]["num_reviewers"] == 1 and "B" not in {k for k in by_agent}


def test_schema_rejects_alike_ids_and_bad_files(tmp_path):
    from repscore.tagmap.schema import Resolver, SchemaError, TagSchema
    with pytest.raises(SchemaError):
        Resolver(TagSchema(clean_tags={"trust": ["trust"], "Trust": ["other"]}))          # ids normalize alike
    with pytest.raises(SchemaError):
        repscore.load_schema(tmp_path / "missing.yaml")


def test_stamp_covers_the_map(tmp_path):
    import yaml
    (tmp_path / "tag_schema.yaml").write_text(yaml.safe_dump({"clean_tags": {"trust": ["trust"]}}))
    h0 = repscore.schema_stamp(repscore.load_schema(tmp_path / "tag_schema.yaml"))["tagmap_hash"]
    (tmp_path / "tag_schema.yaml").write_text(yaml.safe_dump({"clean_tags": {"trust": ["trust", "Trust Score"]}}))
    h1 = repscore.schema_stamp(repscore.load_schema(tmp_path / "tag_schema.yaml"))["tagmap_hash"]
    assert h0 != h1
    assert repscore.schema_stamp({"trust": ["trust"]})["tagmap_hash"] == h0


def test_by_agent_reviewer_differentiation_is_the_mean_of_each_reviewers_per_dimension_values():
    recs = [_rec("A", "X", 100, tag="a"), _rec("A", "Y", 0, tag="a"),
            _rec("A", "X", 100, tag="b"), _rec("A", "Y", 100, tag="b"), _rec("A", "Z", 0, tag="b"),
            _rec("B", "X", 100, tag="a"), _rec("B", "Y", 100, tag="a"), _rec("B", "W", 0, tag="a")]
    by_tag, by_agent = score(recs)
    assert by_tag[("X", "a")]["reviewer_differentiation"] == to_2dp(mean([F(1), F(2, 3)]) * 100)
    assert by_tag[("X", "b")]["reviewer_differentiation"] == to_2dp(F(2, 3) * 100)
    assert by_agent["X"]["reviewer_differentiation"] == to_2dp(mean([mean([F(1), F(2, 3)]), F(2, 3)]) * 100) == "75.00"
    assert by_agent["X"]["comparative_reviewers"] == 2 and by_agent["X"]["num_reviewers"] == 2
    for rejected in ["77.78",    # mean over the 3 (reviewer, dimension) PAIRS
                     "66.67",    # min of each reviewer's per-dimension values   (also 'last seen' here)
                     "83.33",    # max of each reviewer's per-dimension values   (also 'first seen' here)
                     "63.33"]:   # differentiation of each reviewer's ballots POOLED across dimensions
        assert by_agent["X"]["reviewer_differentiation"] != rejected
    assert score(list(reversed(recs)))[1]["X"] == by_agent["X"]


def test_by_agent_reviewer_counts_partition_the_reviewers():
    recs = [_rec("A", "X", 100, tag="a"), _rec("A", "Y", 0, tag="a"),
            _rec("A", "X", 50, tag="b"),
            _rec("B", "X", 10, tag="b"), _rec("B", "Y", 90, tag="b"),
            _rec("C", "X", 70, tag="a"),
            _rec("D", "X", 80, tag="b")]
    by_tag, by_agent = score(recs)
    r = by_agent["X"]
    assert (r["comparative_reviewers"], r["non_comparative_reviewers"], r["num_reviewers"]) == (2, 2, 4)
    assert by_tag[("X", "a")]["comparative_reviewers"] == 1 and by_tag[("X", "a")]["non_comparative_reviewers"] == 1
    assert by_tag[("X", "b")]["comparative_reviewers"] == 1 and by_tag[("X", "b")]["non_comparative_reviewers"] == 2
    for row in list(by_agent.values()) + list(by_tag.values()):
        assert row["comparative_reviewers"] + row["non_comparative_reviewers"] == row["num_reviewers"]
    assert r["reviewer_differentiation"] == "100.00"
    assert score(list(reversed(recs))) == (by_tag, by_agent)


def test_curve_sort_based_ranking_equals_the_pairwise_definition():
    def reference(values):
        n = len(values)
        return [Fraction(100) * (Fraction(sum(1 for u in values if u < v) + sum(1 for u in values if u <= v) + 1, 2)
                                 - Fraction(1, 2)) / n for v in values]
    rng = random.Random(8004)
    for n in list(range(12)) + [37, 60, 101]:
        for _ in range(6):
            vals = [Fraction(rng.randint(-6, 6), rng.choice([1, 2, 4])) for _ in range(n)]
            assert curve(vals) == reference(vals), vals
    big = [Fraction(10 ** 30), Fraction(10 ** 30 + 1), Fraction(3 * 10 ** 30), Fraction(10 ** 30)]
    assert curve(big) == reference(big)


def test_map_on_disk_loads_and_stamps():
    """The map at config/ loads, resolves, and stamps — the live one when it has been copied into place,
    otherwise the tracked example, so the suite runs from a bare clone."""
    config = Path(__file__).resolve().parent.parent / "config"
    schema = config / "tag_schema.yaml"
    r = repscore.load_schema(schema if schema.is_file() else config / "tag_schema.yaml.example")
    assert r.clean_tag_ids()
    assert r.resolve("reputation") == ("trust", False)
    s = repscore.schema_stamp(r)
    assert len(s["tagmap_hash"]) == 64 and s["repscore_version"] == repscore.__version__


def test_input_hardening(tmp_path):
    from repscore.tagmap.schema import SchemaError
    with pytest.raises(ValueError):
        repscore.agent_key(1, "2/erc721:0xEVIL/9")
    with pytest.raises(SchemaError, match="not a file"):
        repscore.load_schema(tmp_path)
    (tmp_path / "tag_schema.yaml").write_text("clean_tags:\n  a: [x]\n  a: [y]\n")
    with pytest.raises(SchemaError, match=r"tag_schema\.yaml.*duplicate mapping key"):
        repscore.load_schema(tmp_path / "tag_schema.yaml")
    (tmp_path / "broken.yaml").write_text("clean_tags: [unclosed\n")
    with pytest.raises(SchemaError, match=r"broken\.yaml"):
        repscore.load_schema(tmp_path / "broken.yaml")
    (tmp_path / "utf16.yaml").write_bytes("clean_tags:\n  a: [a]\n".encode("utf-16"))
    with pytest.raises(SchemaError, match=r"utf16\.yaml"):
        repscore.load_schema(tmp_path / "utf16.yaml")
    (tmp_path / "badtag.yaml").write_text('clean_tags:\n  a: [!!int "0b12"]\n')
    with pytest.raises(SchemaError, match=r"badtag\.yaml"):
        repscore.load_schema(tmp_path / "badtag.yaml")
    if os.geteuid() != 0:
        locked = tmp_path / "locked.yaml"
        locked.write_text("clean_tags:\n  a: [a]\n")
        locked.chmod(0)
        with pytest.raises(SchemaError, match=r"locked\.yaml"):
            repscore.load_schema(locked)
    intkey = tmp_path / "intkey.yaml"
    intkey.write_text("1: x\nclean_tags:\n  a: [a]\n")
    with pytest.raises(SchemaError, match=r"intkey\.yaml"):
        repscore.load_schema(intkey)
    merged = tmp_path / "merged.yaml"
    merged.write_text("clean_tags:\n  base: &m [alpha]\n  <<: {other: [beta]}\n")
    assert repscore.load_schema(merged).clean_tag_ids() == {"base", "other"}
    override = tmp_path / "override.yaml"
    override.write_text("clean_tags:\n  <<: {a: [x]}\n  a: [y]\n")
    assert repscore.load_schema(override).resolve("y") == ("a", False)


def test_repeat_ratings_by_one_reviewer_average_before_ranking():
    _, by_agent = repscore.score([("A", "X", 100, 0, "t"), ("A", "X", 0, 0, "t"), ("A", "Y", 60, 0, "t")])
    assert by_agent["X"]["score"] == "25.00" and by_agent["Y"]["score"] == "75.00"


def test_overall_is_the_plain_mean_when_every_dimension_weight_is_zero():
    records = [("A", "X", 9, 0, "a"), ("A", "Y", 1, 0, "a"), ("B", "X", 1, 0, "b"), ("B", "Z", 9, 0, "b")]
    _, by_agent = repscore.score(records)
    # mean of 75.00 and 25.00: both dimension weights are 1 here, and equal weights give the plain mean
    assert by_agent["X"]["score"] == "50.00"


def test_decode_applies_decimals_inside_scoring():
    _, by_agent = repscore.score([("A", "X", 850, 1, "t"), ("A", "Y", 90, 0, "t")])   # 85.0 < 90
    assert by_agent["X"]["score"] == "25.00" and by_agent["Y"]["score"] == "75.00"


def test_stamp_matches_the_documented_canonical_form():
    import hashlib
    import json
    canonical = json.dumps({"clean_tags": {"t": ["T!"]}}, sort_keys=True, separators=(",", ":"))
    stamp = repscore.schema_stamp({"t": ["T!"]})
    assert stamp["tagmap_hash"] == hashlib.sha256(canonical.encode()).hexdigest()


def test_a_resolver_needs_only_resolve():
    class Only:
        def resolve(self, tag1):
            return ("trust", False)

    by_tag, by_agent = repscore.resolve_and_score([("A", "X", 9, 0, "anything"), ("A", "Y", 1, 0, "anything")], Only())
    assert set(by_tag) == {("X", "trust"), ("Y", "trust")} and by_agent["X"]["band"] == "RANKED"
    assert set(by_tag[("X", "trust")]) == {"band", "score", "comparative_reviewers", "non_comparative_reviewers",
                                           "reviewer_differentiation", "num_reviewers"}
