import ast
import io
import tokenize
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Final

PACKAGE_NAME: Final = "mercari_alert_bot"
SOURCE_ROOT: Final[Path] = Path(__file__).resolve().parents[1] / "src" / PACKAGE_NAME
ALLOWED_LAYER_IMPORTS: Final[Mapping[str, frozenset[str]]] = {
    "shared": frozenset({"shared"}),
    "domain": frozenset({"domain", "shared"}),
    "application": frozenset({"application", "domain", "shared"}),
    "infrastructure": frozenset({"infrastructure", "application", "domain", "shared"}),
    "web": frozenset({"web", "application", "domain", "shared"}),
}
ALLOWED_COMMENT_PREFIXES: Final = ("# type: ignore[", "# noqa", "# pragma:")
DOCSTRING_OWNER_TYPES: Final = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def iter_python_files(source_root: Path) -> list[Path]:
    return sorted(source_root.rglob("*.py"))


def describe_location(source_root: Path, file_path: Path, line_number: int) -> str:
    return f"{file_path.relative_to(source_root)}:{line_number}"


def layer_of_file(source_root: Path, file_path: Path) -> str | None:
    top_level_part = file_path.relative_to(source_root).parts[0]
    return top_level_part if top_level_part in ALLOWED_LAYER_IMPORTS else None


def iter_imported_layers(tree: ast.Module) -> Iterator[tuple[int, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield from layer_of_module_path(node.lineno, alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module == PACKAGE_NAME:
                for alias in node.names:
                    yield from layer_of_module_path(node.lineno, f"{PACKAGE_NAME}.{alias.name}")
            else:
                yield from layer_of_module_path(node.lineno, node.module)


def layer_of_module_path(line_number: int, module_path: str) -> Iterator[tuple[int, str]]:
    module_parts = module_path.split(".")
    if len(module_parts) > 1 and module_parts[0] == PACKAGE_NAME:
        yield line_number, module_parts[1]


def find_layer_violations(source_root: Path) -> list[str]:
    violations = []
    for file_path in iter_python_files(source_root):
        importing_layer = layer_of_file(source_root, file_path)
        if importing_layer is None:
            continue
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
        for line_number, imported_layer in iter_imported_layers(tree):
            if imported_layer not in ALLOWED_LAYER_IMPORTS[importing_layer]:
                location = describe_location(source_root, file_path, line_number)
                violations.append(f"{location}: {importing_layer} imports {imported_layer}")
    return violations


def find_line_comment_violations(source_root: Path, file_path: Path) -> list[str]:
    source_text = file_path.read_text(encoding="utf-8")
    return [
        f"{describe_location(source_root, file_path, token.start[0])}: comment {token.string!r}"
        for token in tokenize.generate_tokens(io.StringIO(source_text).readline)
        if token.type == tokenize.COMMENT and not token.string.startswith(ALLOWED_COMMENT_PREFIXES)
    ]


def is_allowed_docstring(file_path: Path, node: ast.AST) -> bool:
    return isinstance(node, ast.Module) and file_path.name == "__init__.py"


def find_docstring_violations(source_root: Path, file_path: Path) -> list[str]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    return [
        f"{describe_location(source_root, file_path, node.body[0].lineno)}: docstring"
        for node in ast.walk(tree)
        if isinstance(node, DOCSTRING_OWNER_TYPES)
        and ast.get_docstring(node) is not None
        and not is_allowed_docstring(file_path, node)
    ]


def find_html_comment_violations(source_root: Path) -> list[str]:
    return [
        f"{describe_location(source_root, file_path, line_number)}: html comment"
        for file_path in sorted(source_root.rglob("*.html"))
        for line_number, line in enumerate(
            file_path.read_text(encoding="utf-8").splitlines(), start=1
        )
        if "<!--" in line
    ]


def find_comment_violations(source_root: Path) -> list[str]:
    violations = []
    for file_path in iter_python_files(source_root):
        violations.extend(find_line_comment_violations(source_root, file_path))
        violations.extend(find_docstring_violations(source_root, file_path))
    violations.extend(find_html_comment_violations(source_root))
    return violations


def write_source_file(source_root: Path, relative_path: str, content: str) -> None:
    file_path = source_root / relative_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")


def test_source_tree_respects_layer_boundaries() -> None:
    assert find_layer_violations(SOURCE_ROOT) == []


def test_source_tree_has_no_comments() -> None:
    assert find_comment_violations(SOURCE_ROOT) == []


def test_domain_importing_infrastructure_is_reported(tmp_path: Path) -> None:
    write_source_file(
        tmp_path,
        "domain/models/leak.py",
        "import os\nfrom mercari_alert_bot.infrastructure.persistence import database\n",
    )

    assert find_layer_violations(tmp_path) == [
        "domain/models/leak.py:2: domain imports infrastructure"
    ]


def test_web_importing_infrastructure_is_reported(tmp_path: Path) -> None:
    write_source_file(
        tmp_path,
        "web/routers/leak.py",
        "import mercari_alert_bot.infrastructure.persistence\n",
    )

    assert find_layer_violations(tmp_path) == ["web/routers/leak.py:1: web imports infrastructure"]


def test_web_importing_composition_root_is_reported(tmp_path: Path) -> None:
    write_source_file(
        tmp_path,
        "web/routers/leak.py",
        "from mercari_alert_bot.composition_root import build_application\n",
    )

    assert find_layer_violations(tmp_path) == [
        "web/routers/leak.py:1: web imports composition_root"
    ]


def test_composition_root_may_import_every_layer(tmp_path: Path) -> None:
    write_source_file(
        tmp_path,
        "composition_root.py",
        "from mercari_alert_bot import application, domain, infrastructure, shared, web\n",
    )

    assert find_layer_violations(tmp_path) == []


def test_type_checking_import_is_reported(tmp_path: Path) -> None:
    write_source_file(
        tmp_path,
        "domain/ports/leak.py",
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from mercari_alert_bot.infrastructure import sources\n",
    )

    assert find_layer_violations(tmp_path) == [
        "domain/ports/leak.py:3: domain imports infrastructure"
    ]


def test_line_comment_is_reported(tmp_path: Path) -> None:
    write_source_file(tmp_path, "shared/note.py", "x = 1  # note\n")

    assert find_comment_violations(tmp_path) == ["shared/note.py:1: comment '# note'"]


def test_allowed_pragmas_are_not_reported(tmp_path: Path) -> None:
    write_source_file(
        tmp_path,
        "shared/pragmas.py",
        "import os  # type: ignore[attr-defined]\n"
        "import sys  # noqa: E501\n"
        "x = 1  # pragma: no cover\n",
    )

    assert find_comment_violations(tmp_path) == []


def test_function_docstring_is_reported(tmp_path: Path) -> None:
    write_source_file(
        tmp_path,
        "shared/helper.py",
        'def run() -> None:\n    """Run."""\n',
    )

    assert find_comment_violations(tmp_path) == ["shared/helper.py:2: docstring"]


def test_package_init_module_docstring_is_allowed(tmp_path: Path) -> None:
    write_source_file(tmp_path, "shared/__init__.py", '"""Shared utilities."""\n')

    assert find_comment_violations(tmp_path) == []


def test_html_comment_is_reported(tmp_path: Path) -> None:
    write_source_file(tmp_path, "web/static/index.html", "<p>\n<!-- x -->\n</p>\n")

    assert find_comment_violations(tmp_path) == ["web/static/index.html:2: html comment"]
