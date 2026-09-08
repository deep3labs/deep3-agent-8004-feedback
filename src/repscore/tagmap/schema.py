from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .normalize import normalize


class SchemaError(ValueError):
    pass


class _StrictLoader(yaml.SafeLoader):
    """Rejects duplicate explicit mapping keys (yaml's default silently keeps the last)."""

    def construct_mapping(self, node, deep=False):
        keys = [self.construct_object(k, deep=True) for k, _ in node.value
                if k.tag != "tag:yaml.org,2002:merge"]
        for k in keys:
            if keys.count(k) > 1:
                raise SchemaError(f"duplicate mapping key in YAML: {k!r}")
        return super().construct_mapping(node, deep)


class TagSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")          # a misspelled key must not be silently ignored
    clean_tags: dict[str, list[str]] = Field(default_factory=dict)


class Resolver:
    def __init__(self, schema: TagSchema):
        self.schema = schema
        self.index: dict[str, str] = {}
        self._build()

    def _build(self) -> None:
        names: dict[str, str] = {}
        for ct, members in self.schema.clean_tags.items():
            nk = normalize(ct)
            if not nk:
                raise SchemaError(f"clean_tag name {ct!r} normalizes to empty")
            if nk in names and names[nk] != ct:
                raise SchemaError(f"clean_tags {ct!r} and {names[nk]!r} normalize alike")
            names[nk] = ct
            for k in {nk, *(normalize(m) for m in members)}:
                if not k:
                    continue
                if k in self.index and self.index[k] != ct:
                    raise SchemaError(f"key {k!r} claimed by both {self.index[k]!r} and {ct!r}")
                self.index[k] = ct

    def resolve(self, raw: str) -> tuple[str, bool]:
        """Claimed tags return (clean_tag, False); unclaimed ones return (normalized key, True) and are not scored."""
        k = normalize(raw)
        if not k:
            return ("", True)
        ct = self.index.get(k)
        return (ct, False) if ct else (k, True)

    def status(self, raw: str) -> str:
        k = normalize(raw)
        if not k:
            return "empty"
        return "member" if k in self.index else "pending"

    def known_keys(self) -> set[str]:
        return set(self.index)

    def clean_tag_ids(self) -> set[str]:
        return set(self.schema.clean_tags)


def load_schema(path: str | Path) -> Resolver:
    p = Path(path)
    try:
        exists, isfile = p.exists(), p.is_file()
        data = yaml.load(p.read_text(encoding="utf-8"), Loader=_StrictLoader) if isfile else None
    except Exception as e:
        raise SchemaError(f"{p}: {e}") from None
    if not exists:
        raise SchemaError(f"tag schema not found: {p}")
    if not isfile:
        raise SchemaError(f"tag schema is not a file: {p}")
    if not isinstance(data, dict) or not data.get("clean_tags"):
        raise SchemaError(f"{p}: must be a YAML mapping with a non-empty `clean_tags`")
    try:
        schema = TagSchema.model_validate(data)
    except ValidationError as err:
        raise SchemaError(f"{p}: {err}") from None
    return Resolver(schema)
