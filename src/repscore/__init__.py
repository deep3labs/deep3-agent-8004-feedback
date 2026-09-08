"""Reputation scores from ERC-8004 on-chain agent feedback.

Method: docs/SCORING.md. Interface and row fields: docs/CONTRACT.md.
"""
__version__ = "1.0.0"

from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from .tagmap.schema import Resolver

from .identity import ERC8004_IDENTITY_REGISTRY, agent_key
from .score import score

__all__ = [
    "ERC8004_IDENTITY_REGISTRY",
    "__version__",
    "agent_key",
    "load_schema",
    "resolve_and_score",
    "resolve_records",
    "schema_stamp",
    "score",
]


def resolve_records(records: Iterable[tuple[str, str, int, int, str]], resolver) -> Iterator[tuple[str, str, int, int, str]]:
    for rater, ratee, value, decimals, tag1 in records:
        clean_tag, unclaimed = resolver.resolve(tag1)
        if unclaimed or not clean_tag:
            continue
        yield (rater, ratee, value, decimals, clean_tag)


def resolve_and_score(raw_records: Iterable[tuple[str, str, int, int, str]], resolver) -> tuple[dict, dict]:
    return score(list(resolve_records(raw_records, resolver)))


def schema_stamp(resolver_or_clean_tags: "Resolver | dict[str, list[str]] | None") -> dict[str, str]:
    import hashlib
    import json
    r = resolver_or_clean_tags
    clean_tags = r.schema.clean_tags if hasattr(r, "schema") else (r or {})
    canonical = json.dumps({"clean_tags": clean_tags}, sort_keys=True, separators=(",", ":"))
    return {"repscore_version": __version__,
            "tagmap_hash": hashlib.sha256(canonical.encode()).hexdigest()}


def load_schema(path: "str | Path") -> "Resolver":
    """Read the tag map at `path` and return a resolver for it.
    The lazy import keeps bare `import repscore` dependency-free."""
    from .tagmap.schema import load_schema as _load_schema
    return _load_schema(path)
