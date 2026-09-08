"""Score a feedback dataset (a CSV file) with a tag map.

Writes scores_by_agent.csv + scores_by_agent_tag.csv, every row stamped {repscore_version, tagmap_hash}.
"""
import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import repscore
from repscore.tagmap.schema import SchemaError

COLUMNS = ["band", "score", "comparative_reviewers", "non_comparative_reviewers",
           "reviewer_differentiation", "num_reviewers"]


def load_feedback(path):
    if not Path(path).exists():
        raise SystemExit(f"{path}: no such file")
    if not Path(path).is_file():
        raise SystemExit(f"{path}: not a file")
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, restval="")
            reader.fieldnames = [c.strip() for c in reader.fieldnames or []]
            if len(set(reader.fieldnames)) != len(reader.fieldnames):
                raise SystemExit(f"{path}: duplicate column names in header")
            missing = [c for c in ("rater", "ratee", "value", "decimals", "tag1") if c not in reader.fieldnames]
            if missing:
                raise SystemExit(f"{path}: missing column(s): {', '.join(missing)}")
            for r in reader:
                try:
                    value, decimals = int(r["value"].strip()), int(r["decimals"].strip())
                except ValueError:
                    raise SystemExit(f"{path}: line {reader.line_num}: value/decimals missing or non-integer") from None
                if not 0 <= decimals <= 255:
                    raise SystemExit(f"{path}: line {reader.line_num}: decimals out of range (0-255)")
                yield (r["rater"].strip(), r["ratee"].strip(), value, decimals, r["tag1"])
    except (OSError, UnicodeDecodeError, csv.Error) as e:
        raise SystemExit(f"{path}: {getattr(e, 'strerror', None) or e}") from None


def _cells(row):
    return ["N/A" if row[c] is None else row[c] for c in COLUMNS]


def write_outputs(by_tag, by_agent, outdir, stamp) -> Path:
    outdir = Path(outdir)
    if (outdir.exists() or outdir.is_symlink()) and not outdir.is_dir():
        raise SystemExit(f"{outdir}: exists and is not a directory")
    outdir.mkdir(parents=True, exist_ok=True)
    rv, th = stamp["repscore_version"], stamp["tagmap_hash"]
    with open(outdir / "scores_by_agent.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["agent", *COLUMNS, "repscore_version", "tagmap_hash"])
        for a in sorted(by_agent):
            w.writerow([a, *_cells(by_agent[a]), rv, th])
    with open(outdir / "scores_by_agent_tag.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["agent", "clean_tag", *COLUMNS, "repscore_version", "tagmap_hash"])
        for (a, tag) in sorted(by_tag):
            w.writerow([a, tag, *_cells(by_tag[(a, tag)]), rv, th])
    return outdir


def main(argv=None):
    ap = argparse.ArgumentParser(prog="run_score", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("feedback")
    ap.add_argument("--schema", required=True)
    ap.add_argument("--out", default="data")
    args = ap.parse_args(argv)
    try:
        feedback = Path(args.feedback).resolve()
        for name in ("scores_by_agent.csv", "scores_by_agent_tag.csv"):
            if (Path(args.out) / name).resolve() == feedback:
                raise SystemExit(f"--out {args.out} would overwrite the input {args.feedback}")
        resolver = repscore.load_schema(args.schema)
        by_tag, by_agent = repscore.resolve_and_score(load_feedback(args.feedback), resolver)
        stamp = repscore.schema_stamp(resolver)
        out = write_outputs(by_tag, by_agent, args.out, stamp)
    except (SchemaError, OSError, RuntimeError) as e:
        raise SystemExit(str(e)) from None

    bands = Counter(r["band"] for r in by_agent.values())
    print(f"scored {len(by_agent)} agents {dict(bands)} | {len(by_tag)} agent-tag rows "
          f"| repscore {stamp['repscore_version']} | tagmap {stamp['tagmap_hash'][:12]} -> {out}")


if __name__ == "__main__":
    main()
