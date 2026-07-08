import ast
from pathlib import Path

from deadlock_matches import config, queries, schemas

NOTEBOOK = Path(__file__).parent.parent / "notebooks" / "getting_started.py"


def notebook_tree():
    return ast.parse(NOTEBOOK.read_text(encoding="utf-8"))


def attribute_names(tree, module):
    return {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == module
    }


def test_notebook_parses():
    notebook_tree()


def test_query_helpers_exist():
    for name in attribute_names(notebook_tree(), "queries"):
        assert hasattr(queries, name), f"queries.{name} does not exist"


def test_config_helpers_exist():
    for name in attribute_names(notebook_tree(), "config"):
        assert hasattr(config, name), f"config.{name} does not exist"


def test_table_names_are_real():
    tree = notebook_tree()
    table_calls = ("scan", "table_exists")

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func = node.func

        if not (isinstance(func, ast.Attribute) and func.attr in table_calls):
            continue

        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                assert arg.value in schemas.TABLES, f"unknown table {arg.value!r}"
