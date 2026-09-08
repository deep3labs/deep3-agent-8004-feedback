# Changelog

## 1.0.0 (2026-08-26): first public release

- The `repscore` scorer: exact rational arithmetic, ranking inside each reviewer, pairwise-disagreement weights, and the two provenance stamps `repscore_version` and `tagmap_hash` on every row.
- An example of the tag map at `config/tag_schema.yaml.example`; the map is the only scoring input besides the feedback records.
- The scoring harness `scripts/run_score.py` and a ten-agent sample dataset at `data/feedback_sample.csv`.
- Documentation: README, `docs/GUIDE.md`, `docs/SCORING.md`, `docs/CONTRACT.md`.
