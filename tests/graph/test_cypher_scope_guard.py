"""Static guard: every Cypher string that can reach tenant data binds the dataset scope.

Walks every .py under src/ with the AST (no DB, no network). A string is Cypher when it has
a read, write or DDL keyword (any case) or a labelled node pattern. It is tenant-capable when it
names a tenant label, interpolates a label (`(n:{label})`), or matches by element id, since an
element id reaches any node. A tenant-capable string passes when it binds the scope (`dataset_id`,
or a helper from src/graph/scope.py), clause by clause, or when its (file, function, sha1 of the
exact text) is in ALLOWLIST with a reason. Editing an allowlisted query changes its sha and fails
here until it is re-reviewed.

Not seen: a MATCH on an unlabelled node that is neither scoped nor keyed by element id, and any
query built at runtime from a string that is not a literal in src/.
"""
import ast
import hashlib
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"

TENANT_LABELS = (
    "Chunk", "__Entity__", "__Node__", "Persona", "Opinion", "Document", "Provenance",
    "Agent", "MergeAudit", "MergeReview",
)
_LABELS = "|".join(map(re.escape, TENANT_LABELS))
_FLAGS = re.IGNORECASE
_KEYWORD = re.compile(
    r"\b(MATCH|MERGE|UNWIND|OPTIONAL MATCH|DETACH DELETE|CALL db\.|"
    r"CREATE (?:CONSTRAINT|INDEX|VECTOR INDEX|FULLTEXT INDEX)|DROP INDEX)\b",
    _FLAGS,
)
_LABELLED_NODE = re.compile(rf"\(\s*\w*\s*:\s*(?:{_LABELS})\b", _FLAGS)
_TENANT = re.compile(rf"[(:]\s*(?:{_LABELS})\b", _FLAGS)
_ELEMENT_ID = re.compile(r"\belementId\s*\(", _FLAGS)
_SCOPE = re.compile(r"\bdataset_id\b|\b(?:chunk|entity|path)_in_dataset\(", _FLAGS)
_CLAUSE = re.compile(
    r"\b(OPTIONAL MATCH|MATCH|MERGE|CREATE|UNWIND|WITH|CALL|RETURN|SET|DETACH DELETE|DELETE|"
    r"ORDER BY|LIMIT|FOREACH|REMOVE)\b",
    _FLAGS,
)
_PATTERN_CLAUSES = frozenset({"MATCH", "OPTIONAL MATCH", "MERGE", "CREATE"})
_DDL = re.compile(r"^\s*(CREATE|DROP) (CONSTRAINT|INDEX|VECTOR INDEX|FULLTEXT INDEX)\b", _FLAGS)
#: What an interpolated label becomes in the scanned text: `(n:{label})` is a label we cannot name.
DYNAMIC_LABEL = "__DYNAMIC_LABEL__"

#: (file under src/, function, sha1 of the exact Cypher text) -> one-line reason.
ALLOWLIST: dict[tuple[str, str, str], str] = {
    ("src/graph/graph_build.py", "_LINK_CONCEPTS_TO_DOCUMENTS", "701a3209b5521f3778bfde659653b6b70ef4920c"): (
        "KNOWN GAP (parked, 9.1 report): chunk leg not bound to dataset_id; the Document leg is scoped."
    ),
    ("src/graph/normalization.py", "_neighbor_label_jaccard", "53e49f0d76ae632e50ee0708e5da2caa522feb30"): (
        "live: elementIds come from find_surface_duplicates (dataset_id-filtered); reads labels only."
    ),
    ("src/graph/normalization.py", "create_alias_relationships", "33ea481a74e56e802f53cb04f19f40af6cbb6ce4"): (
        "live (run, >=0.75): canon carries dataset_id; originals are elementIds from find_surface_duplicates."
    ),
    ("src/graph/normalization.py", "soft_link_same_as", "ce0b339e27f8641ad61c089fe4abf996cc52284d"): (
        "live (run, 0.6-0.75): SAME_AS between elementIds from find_surface_duplicates; ids must stay in one dataset."
    ),
    ("src/graph/normalization.py", "destructive_merge", "7973acaccf8765d444919f9fd38a9026ad22c148"): (
        "MATCH MergeAudit by the audit id this call CREATEd; the mergeNodes clause is dataset-scoped and refused otherwise."
    ),
    ("src/graph/normalization.py", "write_all", "4e0abbe28f72442f4fecea2e8276313fe2c4d75a"): (
        "dead (only tests call normalize_and_write): MERGE on {labels} and entity_id alone; delete with its tests (parked)."
    ),
    ("src/graph/normalization.py", "write_entities", "86fafc9c3ec21d4a68cc24079ddc8776719c3599"): (
        "dead: the same {labels} MERGE as write_all; delete with its tests (parked)."
    ),
}

#: Owners whose strings must be schema DDL only. A DDL string here is exempt; any other is flagged.
DDL_ONLY = {("src/graph/neo4j_bootstrap.py", "_statements")}


def fingerprint(text: str) -> str:
    """A change fingerprint for an allowlisted query (not a security hash)."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _fstring_text(node: ast.JoinedStr) -> str:
    parts: list[str] = []
    before = ""
    for value in node.values:
        if isinstance(value, ast.Constant):
            parts.append(str(value.value))
            before = str(value.value)
            continue
        if re.search(r":\s*`?$", before):
            parts.append(DYNAMIC_LABEL)
        else:
            parts.append(ast.unparse(value.value))
        before = ""
    return "".join(parts)


def cypher_strings(source: str, filename: str = "<mem>") -> list[tuple[str, int, str]]:
    """(enclosing function, line, text) for every Cypher string literal in `source`.

    Docstrings are prose, not queries, and are skipped. Module-level constants are named by
    their variable. An f-string contributes its literal text plus the source of each
    interpolated expression, so `{entity_in_dataset('e')}` counts as the predicate it names.
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
        if _KEYWORD.search(hit[2]) or _LABELLED_NODE.search(hit[2])
    ]


def _touches_tenant(text: str) -> bool:
    return bool(_TENANT.search(text) or DYNAMIC_LABEL in text or _ELEMENT_ID.search(text))


def _unscoped_pattern_clauses(text: str) -> list[str]:
    """Each MATCH/MERGE/CREATE clause that can reach tenant data but binds no scope itself.

    A clause runs to the next clause keyword, so its own WHERE is part of it. A string can
    scope one clause and leave another unscoped; this catches the second.
    """
    marks = list(_CLAUSE.finditer(text))
    unscoped = []
    for i, mark in enumerate(marks):
        if " ".join(mark.group(1).upper().split()) not in _PATTERN_CLAUSES:
            continue
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        segment = text[mark.start():end]
        if _touches_tenant(segment) and not _SCOPE.search(segment):
            unscoped.append(segment)
    return unscoped


def unscoped_tenant_queries(source: str, filename: str = "<mem>") -> list[tuple[str, int, str]]:
    flagged = []
    for owner, line, text in cypher_strings(source, filename):
        if not _touches_tenant(text):
            continue
        if not _SCOPE.search(text) or _unscoped_pattern_clauses(text):
            flagged.append((owner, line, text))
    return flagged


def violations(source: str, rel: str) -> list[str]:
    """Unscoped tenant strings in `source` that are not allowlisted or DDL-only."""
    out = []
    for owner, line, text in unscoped_tenant_queries(source, rel):
        if (rel, owner, fingerprint(text)) in ALLOWLIST:
            continue
        if (rel, owner) in DDL_ONLY and _DDL.match(text):
            continue
        out.append(
            f"{rel}:{line} in {owner}() sha={fingerprint(text)}: {' '.join(text.split())[:120]}"
        )
    return out


def _src_files() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


def _rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def _live_keys() -> set[tuple[str, str, str]]:
    return {
        (_rel(path), owner, fingerprint(text))
        for path in _src_files()
        for owner, _, text in cypher_strings(path.read_text(encoding="utf-8"), str(path))
    }


def test_every_tenant_cypher_string_binds_the_scope_or_is_allowlisted():
    problems = []
    for path in _src_files():
        problems.extend(violations(path.read_text(encoding="utf-8"), _rel(path)))
    assert problems == []


def test_the_scanner_sees_the_scoped_reads_it_must_not_miss():
    hits = cypher_strings((SRC / "persona" / "graph_context.py").read_text(encoding="utf-8"))
    scoped = [text for _, _, text in hits if _SCOPE.search(text)]
    assert len(scoped) >= 10


def test_a_string_without_the_scope_is_flagged():
    source = 'def read(s):\n    return s.run("MATCH (c:Chunk {id: $id}) RETURN c")\n'
    assert [owner for owner, _, _ in unscoped_tenant_queries(source)] == ["read"]


def test_a_lowercase_cypher_string_is_flagged_like_the_uppercase_one():
    source = (
        'def read(s):\n    return s.run("match (c:Chunk {id:$id}) with c '
        'match (d:Document) where d.dataset_id=$ds return c")\n'
    )
    assert [owner for owner, _, _ in unscoped_tenant_queries(source)] == ["read"]


def test_an_unlabelled_match_by_element_id_is_tenant_capable():
    source = 'def read(s):\n    return s.run("MATCH (a) WHERE elementId(a) = $id RETURN a")\n'
    assert [owner for owner, _, _ in unscoped_tenant_queries(source)] == ["read"]


def test_an_interpolated_label_is_tenant_capable():
    source = 'def write(s, labels):\n    return s.run(f"MERGE (n:{labels} {{entity_id: $id}})")\n'
    assert [owner for owner, _, _ in unscoped_tenant_queries(source)] == ["write"]


def test_an_fstring_that_interpolates_the_scope_helper_passes():
    source = 'def read(s):\n    return s.run(f"MATCH (e:__Entity__) WHERE {entity_in_dataset(\'e\')} RETURN e")\n'
    assert unscoped_tenant_queries(source) == []


def test_a_docstring_naming_a_label_is_prose_not_a_query():
    source = 'def read():\n    """MERGE one Chunk per row."""\n    return 1\n'
    assert cypher_strings(source) == []


def test_a_non_tenant_cypher_string_needs_no_scope():
    source = 'def write(s):\n    s.run("MATCH (n:Scratch) RETURN n")\n'
    assert unscoped_tenant_queries(source) == []


def test_a_new_query_inside_an_allowlisted_function_still_fails(monkeypatch):
    rel = "src/graph/normalization.py"
    old = "MATCH (c:Chunk {id: $id}) RETURN c"
    monkeypatch.setitem(ALLOWLIST, (rel, "read", fingerprint(old)), "probe: the reviewed query")
    reviewed = f'def read(s):\n    return s.run("{old}")\n'
    grown = (
        f'def read(s):\n    s.run("{old}")\n'
        '    s.run("MATCH (d:Chunk {id: $x}) RETURN d")\n'
    )
    assert violations(reviewed, rel) == []
    assert violations(grown, rel) != []


def test_every_allowlist_entry_names_a_live_cypher_string():
    stale = sorted(key for key in ALLOWLIST if key not in _live_keys())
    assert stale == []


def test_every_ddl_only_owner_holds_cypher():
    for rel, owner in sorted(DDL_ONLY):
        texts = [
            text
            for path in _src_files() if _rel(path) == rel
            for found_owner, _, text in cypher_strings(path.read_text(encoding="utf-8"), str(path))
            if found_owner == owner
        ]
        assert texts, f"{(rel, owner)} holds no Cypher"
        assert all(_DDL.match(text) for text in texts)


@pytest.mark.parametrize("reason", sorted(ALLOWLIST.values()))
def test_every_allowlist_entry_has_a_reason(reason):
    assert reason.strip()


def test_nothing_outside_normalization_imports_the_dead_writers():
    dead = {"normalize_and_write", "write_all", "write_entities", "write_relations"}
    offenders = []
    for path in _src_files():
        if _rel(path) == "src/graph/normalization.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.ImportFrom):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.Attribute):
                names = [node.attr]
            elif isinstance(node, ast.Name):
                names = [node.id]
            offenders.extend(f"{_rel(path)}:{node.lineno} {name}" for name in names if name in dead)
    assert offenders == []
