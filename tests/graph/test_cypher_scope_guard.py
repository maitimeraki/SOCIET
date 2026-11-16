"""Static guard: every Cypher string that touches a tenant label binds the dataset scope.

Walks every .py under src/ with the AST (no DB, no network). A string is Cypher when it
has a read/write/DDL keyword or a labelled node pattern; it touches a tenant label when it
names one. It passes when it binds the scope (`dataset_id`, or a helper from
src/graph/scope.py) or when its (file, function) is in ALLOWLIST with a reason. A new
unscoped query fails here, not in review.
"""
import ast
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"

TENANT_LABELS = (
    "Chunk", "__Entity__", "__Node__", "Persona", "Opinion", "Document",
    "Agent", "MergeAudit", "MergeReview",
)
_LABELS = "|".join(map(re.escape, TENANT_LABELS))
_CYPHER_KEYWORD = re.compile(
    r"\b(MATCH|MERGE|UNWIND|OPTIONAL MATCH|DETACH DELETE|CALL db\.|"
    r"CREATE (?:CONSTRAINT|INDEX|VECTOR INDEX|FULLTEXT INDEX)|DROP INDEX)\b"
)
_LABELLED_NODE = re.compile(rf"\(\s*\w*\s*:\s*(?:{_LABELS})\b")
_TENANT = re.compile(rf"[(:]\s*(?:{_LABELS})\b")
_SCOPE = re.compile(r"\bdataset_id\b|\b(?:chunk|entity|path)_in_dataset\(")

#: (file under src/, function) -> reason. Each entry is one place a tenant-touching Cypher
#: string may stand without a scope predicate. Keep this list short; a new entry is a review.
ALLOWLIST: dict[tuple[str, str], str] = {
    ("src/graph/neo4j_bootstrap.py", "_statements"): (
        "schema DDL only (constraints, indexes, vector and fulltext indexes); no data is read or "
        "written. test_allowlisted_ddl_is_only_ddl enforces that."
    ),
    ("src/graph/normalization.py", "destructive_merge"): (
        "MATCH MergeAudit keyed by the audit id this call just CREATEd (namespaced uuid); the "
        "merged nodes are the dataset-scoped candidates find_surface_duplicates returned."
    ),
    ("src/graph/normalization.py", "enqueue_for_review"): (
        "CREATE MergeReview has no dataset property and no route reads review rows (live: called "
        "from run() on the normalize_graph job). KNOWN GAP, see the 9.1 report: add dataset_id."
    ),
    ("src/graph/graph_build.py", "_LINK_CONCEPTS_TO_DOCUMENTS"): (
        "KNOWN GAP, see the 9.1 report: the chunk leg is keyed by chunk ids from this ingest "
        "batch and the Document leg is dataset-scoped, but the chunk is not bound to $dataset_id. "
        "Fix: WHERE c.dataset_id = $dataset_id (outside 9.1's file set)."
    ),
}

#: Allowlisted owners that must hold only schema DDL. Their Cypher may not read or write data.
DDL_ONLY = {("src/graph/neo4j_bootstrap.py", "_statements")}
_DDL = re.compile(r"^\s*(CREATE|DROP) (CONSTRAINT|INDEX|VECTOR INDEX|FULLTEXT INDEX)\b")


def _fstring_text(node: ast.JoinedStr) -> str:
    parts = []
    for value in node.values:
        if isinstance(value, ast.Constant):
            parts.append(str(value.value))
        else:
            parts.append(ast.unparse(value.value))
    return "".join(parts)


def cypher_strings(source: str, filename: str = "<mem>") -> list[tuple[str, int, str]]:
    """(enclosing function, line, text) for every string literal in `source` that is Cypher.

    Docstrings are prose, not queries, and are skipped. An f-string contributes its literal
    text plus the source of each interpolated expression, so `{entity_in_dataset('e')}`
    counts as the predicate it names.
    """
    tree = ast.parse(source, filename=filename)
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    found: list[tuple[str, int, str]] = []

    def visit(node: ast.AST, owner: str) -> None:
        for child in ast.iter_child_nodes(node):
            inner = owner
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                inner = child.name
            elif owner == "<module>" and isinstance(child, ast.Assign) and isinstance(child.targets[0], ast.Name):
                inner = child.targets[0].id
            if isinstance(child, ast.JoinedStr):
                found.append((owner, child.lineno, _fstring_text(child)))
            elif isinstance(child, ast.Constant) and isinstance(child.value, str):
                if id(child) not in docstrings:
                    found.append((owner, child.lineno, child.value))
            else:
                visit(child, inner)

    visit(tree, "<module>")
    return [
        hit for hit in found
        if _CYPHER_KEYWORD.search(hit[2]) or _LABELLED_NODE.search(hit[2])
    ]


_CLAUSE = re.compile(
    r"\b(OPTIONAL MATCH|MATCH|MERGE|CREATE|UNWIND|WITH|CALL|RETURN|SET|DETACH DELETE|DELETE|"
    r"ORDER BY|LIMIT|FOREACH|REMOVE)\b"
)
_PATTERN_CLAUSES = frozenset({"MATCH", "OPTIONAL MATCH", "MERGE", "CREATE"})


def _unscoped_pattern_clauses(text: str) -> list[str]:
    """Each MATCH/MERGE/CREATE clause that names a tenant label but binds no scope itself.

    A clause runs to the next clause keyword, so its own WHERE is part of it. A string can
    scope one clause and leave another unscoped; this catches the second.
    """
    marks = list(_CLAUSE.finditer(text))
    unscoped = []
    for i, mark in enumerate(marks):
        if mark.group(1) not in _PATTERN_CLAUSES:
            continue
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        segment = text[mark.start():end]
        if _TENANT.search(segment) and not _SCOPE.search(segment):
            unscoped.append(segment)
    return unscoped


def unscoped_tenant_queries(source: str, filename: str = "<mem>") -> list[tuple[str, int, str]]:
    flagged = []
    for owner, line, text in cypher_strings(source, filename):
        if not _TENANT.search(text):
            continue
        if not _SCOPE.search(text) or _unscoped_pattern_clauses(text):
            flagged.append((owner, line, text))
    return flagged


def _src_files() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


def _rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def test_every_tenant_cypher_string_binds_the_scope_or_is_allowlisted():
    violations = []
    for path in _src_files():
        for owner, line, text in unscoped_tenant_queries(path.read_text(encoding="utf-8"), str(path)):
            if (_rel(path), owner) not in ALLOWLIST:
                violations.append(f"{_rel(path)}:{line} in {owner}(): {' '.join(text.split())[:120]}")
    assert violations == []


def test_the_scanner_sees_the_scoped_reads_it_must_not_miss():
    hits = cypher_strings((SRC / "persona" / "graph_context.py").read_text(encoding="utf-8"))
    scoped = [text for _, _, text in hits if _SCOPE.search(text)]
    assert len(scoped) >= 10


def test_a_string_without_the_scope_is_flagged():
    source = 'def read(s):\n    return s.run("MATCH (c:Chunk {id: $id}) RETURN c")\n'
    assert [owner for owner, _, _ in unscoped_tenant_queries(source)] == ["read"]


def test_an_fstring_that_interpolates_the_scope_helper_passes():
    source = 'def read(s):\n    return s.run(f"MATCH (e:__Entity__) WHERE {entity_in_dataset(\'e\')} RETURN e")\n'
    assert unscoped_tenant_queries(source) == []


def test_a_docstring_naming_a_label_is_prose_not_a_query():
    source = 'def read():\n    """MERGE one Chunk per row."""\n    return 1\n'
    assert cypher_strings(source) == []


def test_a_non_tenant_cypher_string_needs_no_scope():
    source = 'def write(s):\n    s.run("MATCH (n:Scratch) RETURN n")\n'
    assert unscoped_tenant_queries(source) == []


def test_every_allowlist_entry_names_a_live_cypher_string():
    live = {
        (_rel(path), owner)
        for path in _src_files()
        for owner, _, _ in cypher_strings(path.read_text(encoding="utf-8"), str(path))
    }
    stale = sorted(key for key in ALLOWLIST if key not in live)
    assert stale == []


@pytest.mark.parametrize("reason", sorted(ALLOWLIST.values()))
def test_every_allowlist_entry_has_a_reason(reason):
    assert reason.strip()


@pytest.mark.parametrize("key", sorted(DDL_ONLY))
def test_allowlisted_ddl_is_only_ddl(key):
    rel, owner = key
    texts = [
        text
        for path in _src_files() if _rel(path) == rel
        for found_owner, _, text in cypher_strings(path.read_text(encoding="utf-8"), str(path))
        if found_owner == owner
    ]
    assert texts, f"{key} holds no Cypher"
    assert all(_DDL.match(text) for text in texts)
