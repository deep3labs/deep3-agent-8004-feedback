import re
import unicodedata

MAX_LEN = 64          # cap untrusted input

_STRIP = re.compile(r"[^a-z0-9]+")


def normalize(raw: str) -> str:
    """Reduce a raw tag to its normalized key: first 64 characters, NFKC, casefold, keep [a-z0-9].
    Non-ASCII that NFKC does not fold is deleted, so a decorated spelling can
    collide with the plain key it reduces to."""
    if not raw:
        return ""
    s = unicodedata.normalize("NFKC", raw[:MAX_LEN]).casefold()
    return _STRIP.sub("", s)

