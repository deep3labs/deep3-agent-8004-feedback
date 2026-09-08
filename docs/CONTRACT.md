# Calling `repscore` from another repo

This repo is a **pip-installable library another repo imports** to turn ERC-8004 feedback into
reputation scores. The scoring logic is a **pure library** in `src/repscore/`; the scoring harness `scripts/run_score.py` is **not** in the wheel.
Install from a local checkout or straight from GitHub. A tag map is a separate input the caller chooses, and no tag
map is packaged in the wheel; Reproducibility / provenance below covers the three sources.

## Layout
```
src/                             pure, importable: the only thing packaged into the wheel
  repscore/                        the scorer + the front-door facade
    tagmap/                        the read-only tag1 -> clean_tag resolver kernel (normalize, schema)
scripts/                         in-repo I/O harness: not in the wheel, not imported by consumers
  run_score.py                     full-scale scoring run (feedback dataset in -> score tables out)
config/tag_schema.yaml.example   an example tag map, a scoring input
```
`src/` performs **no I/O on import**, and bare `import repscore` pulls no third-party package (`pyyaml`+`pydantic`
load only with the resolver kernel). The only I/O in any call path is `repscore.load_schema(path)`
reading the map at the path it is given. A `tests/test_layering.py`
AST guard fails the test run if a file in `src/` imports one of a fixed list of I/O, network and tooling modules.

## How the other repo consumes it
```bash
pip install -e /path/to/deep3-agent-8004-feedback  # editable, for local dev
pip install    /path/to/deep3-agent-8004-feedback  # from a local checkout
pip install "git+https://github.com/deep3labs/deep3-agent-8004-feedback.git"
```
Then `import repscore`. The **distribution** is `agent-8004feedback` (what you install); the **import**
is `repscore` (`tagmap` is an internal subpackage, `repscore.tagmap`, and is not a top-level name). The
library's install dependencies are `pyyaml`+`pydantic` (needed by `load_schema`).

## Front door (the whole public surface)
```python
resolver          = repscore.load_schema("tag_schema.yaml")            # tag1 -> clean_tag resolver
by_tag, by_agent  = repscore.resolve_and_score(raw_records, resolver)  # raw records -> scores
stamp             = repscore.schema_stamp(resolver)                    # {repscore_version, tagmap_hash}
repscore.__version__                                                   # the algorithm version
```
Also importable: `repscore.score(resolved_records)` (skip resolution), `repscore.resolve_records(raw_records,
resolver)` (resolution only), and the identity helpers `agent_key` / `ERC8004_IDENTITY_REGISTRY` (below). The resolver is **duck-typed**:
`resolve_records` and `resolve_and_score` call only `resolver.resolve(tag1)`, so a consumer may inject
any object whose `.resolve(tag1)` returns `(clean_tag: str, unclaimed: bool)`.

## Data contract
**Input.** A raw record is a 5-tuple:
```
(rater: str, ratee: str, value: int, decimals: int, tag1: str)
```
`value`/`decimals` decode exactly to `value / 10**decimals`; `rater` is the reviewer's wallet address; `ratee` is the
rated agent's identity string (the numeric agentId, or the CAIP-19 key below). `tag1` is the raw feedback label. Repeat ratings by one rater of the same (ratee, clean_tag) are
averaged after resolution, before scoring; two spellings of one dimension collapse together. **Only records whose `tag1` the map claims are scored**: an unclaimed `tag1`, or one whose normalized key is empty
(first 64 chars, NFKC, casefold, keep `[a-z0-9]`), is dropped before scoring, so a new tag appears in the output only after it has been put in the map. An unclaimed tag
has either not been decided yet or been ruled out; the map does not distinguish the two. (A literal `rater == ratee` guard exists, and it cannot fire while raters are
wallet addresses and ratees are agent identity strings; real self-review detection would require linking the
wallet that controls an agent to that agent's agentId, which this library does not do.)

**Output.** `by_agent: {agent: row}` and `by_tag: {(agent, clean_tag): row}`, where a row is:
```
{ "band": "RANKED" | "INSUFFICIENT_COMPARATIVE_DATA",   # no scoreable feedback -> no row at all
  "score": "<0..100, 2dp string>" | None,     # None unless band == RANKED
  "comparative_reviewers": int,                # distinct reviewers whose comparisons set the score
  "non_comparative_reviewers": int,            # distinct reviewers who rated it alone / all-equal; on by_agent rows, in EVERY dimension they
                                               # rated it in; a reviewer comparative anywhere counts once, as comparative, so the two counts sum to num_reviewers
                                               # (hence a per-dimension row's non_comparative_reviewers can exceed the by_agent row's: the same reviewer can be
                                               # non-comparative in one dimension and comparative in another)
  "reviewer_differentiation": "<0..100, 2dp string>" | None,  # a RATE: mean over the comparative reviewers of each one's differentiation; on by_agent rows a
                                               # reviewer spanning several dimensions contributes the mean of their per-dimension values (None if not RANKED)
  "num_reviewers": int }                       # total distinct reviewers (comparative + non-comparative)
```
(`scripts/run_score.py` writes a `None` as the literal `N/A` in its CSV outputs.) The three integer fields are reviewer counts and `reviewer_differentiation` is a rate; none of them is a probability that the score is correct.

Column order the harness writes:

| File | Key columns | Row fields | Stamp |
|---|---|---|---|
| `scores_by_agent.csv` | `agent` | `band, score, comparative_reviewers, non_comparative_reviewers, reviewer_differentiation, num_reviewers` | `repscore_version, tagmap_hash` |
| `scores_by_agent_tag.csv` | `agent, clean_tag` | `band, score, comparative_reviewers, non_comparative_reviewers, reviewer_differentiation, num_reviewers` | `repscore_version, tagmap_hash` |

RANKED and INSUFFICIENT rows are **not co-rankable**: sort/threshold the 0–100 axis only within RANKED.
There is **no sybil bound** on the score; `comparative_reviewers` beside
`num_reviewers` is how a consumer spots thin or lopsided support (see `docs/SCORING.md`).

## Agent identity & the canonical publish key
The scorer treats each `ratee` (and therefore each `by_agent` key) as an **opaque identity string**: it
groups by exact string match and never parses it. So the identity convention is the caller's to set;
the helper below keeps it consistent.

The canonical key is the CAIP-19 identifier of the agent's ERC-8004 Identity-Registry NFT, in CAIP-19's
standard slash form: chain, token standard, contract and token id in a single self-describing string:
```
eip155:<chainId>/erc721:0x8004A169FB4a3325136EB29fA0ceB6D2e539a432/<tokenId>
```
Build it with `repscore.agent_key(chain_id, token_id)`. The default registry is the ERC-8004 Identity Registry
as deployed on the Base chain (chainId 8453; pass `registry=` for a deployment that differs), and
`token_id` is the ERC-8004 `agentId`. `repscore.ERC8004_IDENTITY_REGISTRY` exposes the address. Keys are compared as
exact strings and never normalized, so keep the checksummed casing; a lowercase `registry=` produces keys that will not match a published key.

**Recommended flow** (makes the output publish-ready and multi-chain-safe): compose each feedback record's
`ratee` as `agent_key(chain_id, token_id)` before scoring. Then (a) an agent registered on two
chains with the same `tokenId` does **not** merge into one, and (b) every `by_agent` key in the output is
already a valid CAIP-19 identifier. (The chain must come from the extraction step; a bare `tokenId`
is ambiguous across chains.)

## Reproducibility / provenance
Every published number is reproducible from the on-chain records up to the block it was computed against (not part
of this library's input or output), the tag map file it was computed with, and the scorer that produced it. Every row
`scripts/run_score.py` writes also carries two stamps: `repscore_version` (the algorithm) and `tagmap_hash` (full sha256 over
the canonical `clean_tags` mapping; a change to any dimension id, or to the spellings under one or their order,
restamps the rows, while reordering the dimensions in the file does not). Canonical form, so a third party can recompute it:
`sha256(json.dumps({"clean_tags": <the map's clean_tags mapping, verbatim>}, sort_keys=True, separators=(",", ":")))`.
A missing or malformed tag map file is an error. There
is no third stamp because there is **no operator-tunable constant in the scorer**: no prior, no threshold (the curation
tooling's thresholds only shape the tag map). All arithmetic is
exact (`fractions.Fraction`); the only rounding is the final half-to-even to 2 decimals. See
`docs/SCORING.md` for the algorithm and its accepted limitations.

**Getting a tag map.** The tag map is an input the caller chooses, from three sources. To run this repository, use the
bundled `config/tag_schema.yaml.example`; it lets the harness and the tests run and shows the format. To score with
any other map, whether your own or a publisher's, pass its path to `load_schema`. To reproduce a score someone
published, use the map file that produced it, which the publisher supplies: a Deep3 Labs assessment carries `method.repscore.tagmap.url` and `method.repscore.tagmap.sha256`, so fetch
the URL and check the download with `sha256sum`.

That confirms the map. Recomputing the number also needs the feedback records for every agent scored in each
dimension the agent appears in, since a score is a position among peers, read up to the height for your chain in `method.asOfBlock`, less
any records the publisher states it excluded (a Deep3 Labs assessment states the exclusion in `method.source`), scored with the
code at `method.repscore.commit`.

`tagmap_hash` is the canonical-form hash above, a different value from the file's sha256, written into
`run_score.py`'s output columns and present in no published assessment. Equal `tagmap_hash` implies two tag maps
resolve every tag identically; the converse does not hold, since spelling order is hashed and does not affect
resolution. Narrative in [README, Reproducibility](../README.md#reproducibility). The bundled example is a snapshot
of a past curation round, so it will not reproduce a current published score.

## Running the harness in this repo
```bash
python scripts/run_score.py data/feedback_sample.csv --schema config/tag_schema.yaml.example --out data
python -m pytest tests/ -q                                    # the suite needs no copy: it falls back to the example
```
`run_score.py` reaches the library without an install by putting `src/` on `sys.path` itself. Deep3 Labs runs its curation tooling and feedback extraction in a
private operations repository; the map files it produces are published as described above.

Feedback extraction spec (for independent reproduction): source the `NewFeedback` event of the chain's
Reputation Registry (Base, chainId 8453: `0x8004BAa17C55a88189AE136b182e5fdA19dE9b63`).
The signature is `NewFeedback(uint256,address,uint64,int128,uint8,string,string,string,string,string,bytes32)`; topic0 is
`0x6a4a61743519c9d648a14e6493f47dbe3ff1aa29e7785c96c8326a205e58febc` (keccak256 of the signature). One dataset row per event: rater, ratee, value, decimals, tag1, where ratee is `agent_key(<the chainId you extracted from>, agentId)` per the recommended flow above; `data/feedback_sample.csv` uses that CAIP-19 form.
A published score may exclude records the registry later revoked; a publisher states what it excluded, and this spec does not cover revocation.

The layout below was observed on Base in the events extracted through 21 August 2026 from the registry above (topics and data
words are 0-indexed; ABI dynamic strings are read through their offset word). A later deployment may change the
event, so check this layout against the ABI of the registry you extract from before relying on it:

| Log field | Index | Holds | Dataset column |
|---|---|---|---|
| topic | 0 | topic0 of `NewFeedback` | (none) |
| topic | 1 | `agentId`, uint256 | `ratee`, as `agent_key(chainId, agentId)` |
| topic | 2 | `rater`, address (low 20 bytes of the word) | `rater` |
| topic | 3 | constant across observed events | (none) |
| data word | 0 | uint64 identifier | (none) |
| data word | 1 | `value`, int128 | `value` |
| data word | 2 | `valueDecimals`, uint8 | `decimals` |
| data word | 3 | ABI offset of `tag1` | `tag1` (decoded via the offset) |
