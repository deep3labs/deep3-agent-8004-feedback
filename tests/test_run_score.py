import os
from pathlib import Path

import pytest
import run_score

REPO = Path(__file__).resolve().parents[1]
# The live map is not tracked here; a clone has only the example. Prefer a real map when one has been
# copied into place, and fall back to the example so the suite runs from a bare clone.
SCHEMA = REPO / "config" / "tag_schema.yaml"
if not SCHEMA.is_file():
    SCHEMA = REPO / "config" / "tag_schema.yaml.example"


def test_run_score_reader_accepts_quoted_crlf_bom_feedback_csv(tmp_path):
    body = ('"rater","ratee","value","decimals","tag1"\r\n'
            '"0xA",1,100,0,"speed"\r\n"0xa",1,"90",0,"speed"\r\n"0xB",2,"1000000000000000000",18,"speed"\r\n'
            '"0xB",2,80,0,"Agent handles the, quoted ""sentence"" well."\r\n')
    fb = tmp_path / "fb.csv"
    fb.write_bytes(b"\xef\xbb\xbf" + body.encode())
    assert list(run_score.load_feedback(fb)) == [
        ("0xA", "1", 100, 0, "speed"),
        ("0xa", "1", 90, 0, "speed"),
        ("0xB", "2", 1000000000000000000, 18, "speed"),
        ("0xB", "2", 80, 0, 'Agent handles the, quoted "sentence" well.'),
    ]


def test_reader_rejects_malformed_inputs(tmp_path):
    cases = {"dup.csv": ("rater,ratee,value,decimals,tag1,value\nA,X,90,0,trust,1\n", "duplicate column"),
             "neg.csv": ("rater,ratee,value,decimals,tag1\nA,X,90,-3,trust\n", "out of range"),
             "big.csv": ("rater,ratee,value,decimals,tag1\nA,X,90,50000000,trust\n", "out of range")}
    for name, (body, msg) in cases.items():
        p = tmp_path / name
        p.write_text(body)
        with pytest.raises(SystemExit, match=msg):
            list(run_score.load_feedback(p))


def test_out_guards(tmp_path):
    fb = tmp_path / "scores_by_agent.csv"
    fb.write_text("rater,ratee,value,decimals,tag1\nA,X,90,0,trust\nA,Y,10,0,trust\n")
    with pytest.raises(SystemExit, match="not a file"):
        list(run_score.load_feedback(tmp_path))
    if os.geteuid() != 0:
        locked = tmp_path / "locked.csv"
        locked.write_text("rater,ratee,value,decimals,tag1\n")
        locked.chmod(0)
        with pytest.raises(SystemExit, match="ermission"):
            list(run_score.load_feedback(locked))
        ro = tmp_path / "ro"
        ro.mkdir()
        ro.chmod(0o555)
        fb2 = tmp_path / "fb.csv"
        fb2.write_text("rater,ratee,value,decimals,tag1\nA,X,90,0,trust\nA,Y,10,0,trust\n")
        with pytest.raises(SystemExit, match="ermission"):
            run_score.main([str(fb2), "--schema", str(SCHEMA), "--out", str(ro / "sub")])
        ro.chmod(0o755)
    latin = tmp_path / "latin.csv"
    latin.write_bytes(b"rater,ratee,value,decimals,tag1\nA,\xff\xfe,90,0,trust\n")
    with pytest.raises(SystemExit, match="latin.csv"):
        list(run_score.load_feedback(latin))
    wide = tmp_path / "wide.csv"
    wide.write_text("rater,ratee,value,decimals,tag1\nA," + "x" * 140000 + ",90,0,trust\n")
    with pytest.raises(SystemExit, match="field larger"):
        list(run_score.load_feedback(wide))
    loop = tmp_path / "loop"
    loop.symlink_to(loop)
    with pytest.raises(SystemExit):
        run_score.main([str(loop), "--schema", str(SCHEMA), "--out", str(tmp_path / "o")])
    with pytest.raises(SystemExit, match="overwrite the input"):
        run_score.main([str(fb), "--schema", str(SCHEMA), "--out", str(tmp_path)])
    clash = tmp_path / "afile"
    clash.write_text("x")
    with pytest.raises(SystemExit, match="not a directory"):
        run_score.write_outputs({}, {}, clash, {"repscore_version": "0", "tagmap_hash": "0"})
    dangling = tmp_path / "dangling"
    dangling.symlink_to(tmp_path / "missing")
    with pytest.raises(SystemExit, match="not a directory"):
        run_score.write_outputs({}, {}, dangling, {"repscore_version": "0", "tagmap_hash": "0"})


def test_schema_errors_exit_named(tmp_path):
    with pytest.raises(SystemExit, match="not a file"):
        run_score.main([str(tmp_path / "x.csv"), "--schema", str(tmp_path), "--out", str(tmp_path / "o")])


def test_harness_writes_the_documented_files(tmp_path):
    run_score.main([str(REPO / "data" / "feedback_sample.csv"), "--schema", str(SCHEMA), "--out", str(tmp_path)])
    agent = (tmp_path / "scores_by_agent.csv").read_text().splitlines()
    tag = (tmp_path / "scores_by_agent_tag.csv").read_text().splitlines()
    fields = "band,score,comparative_reviewers,non_comparative_reviewers,reviewer_differentiation,num_reviewers"
    assert agent[0] == f"agent,{fields},repscore_version,tagmap_hash"
    assert tag[0] == f"agent,clean_tag,{fields},repscore_version,tagmap_hash"
    assert all(line.split(",")[1] == "RANKED" for line in agent[1:])
    assert all(len(line.split(",")[-1]) == 64 for line in agent[1:])
    insufficient = ["A,X,90,0,trust", "B,X,90,0,trust"]
    (tmp_path / "alone.csv").write_text("rater,ratee,value,decimals,tag1\n" + "\n".join(insufficient) + "\n")
    run_score.main([str(tmp_path / "alone.csv"), "--schema", str(SCHEMA), "--out", str(tmp_path / "o2")])
    row = (tmp_path / "o2" / "scores_by_agent.csv").read_text().splitlines()[1].split(",")
    assert row[1] == "INSUFFICIENT_COMPARATIVE_DATA" and row[2] == "N/A" and row[5] == "N/A"
