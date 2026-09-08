import ast
import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"

# yaml + pydantic are deliberately allowed: load_schema uses them
FORBIDDEN = {
    "subprocess", "socket", "sqlite3", "urllib", "http", "ftplib", "smtplib",
    "requests", "httpx", "aiohttp",
    "csv", "scripts",
}


def _import_roots(path):
    """Relative imports are exempt: they stay inside src/."""
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            yield node.lineno, node.module.split(".")[0]


def test_src_imports_stay_pure():
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        for lineno, root in _import_roots(path):
            if root in FORBIDDEN:
                offenders.append(f"{path.relative_to(SRC)}:{lineno} imports {root!r}")
    assert not offenders, (
        "src/ must stay pure: no I/O, network, LLM, fuzzy or tooling imports:\n"
        + "\n".join(offenders)
    )


def test_bare_import_is_dependency_free():
    """`import repscore` must not load yaml or pydantic (docs/CONTRACT.md)."""
    code = "import sys, repscore; assert 'yaml' not in sys.modules and 'pydantic' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], check=True, env={**os.environ, "PYTHONPATH": str(SRC)})
