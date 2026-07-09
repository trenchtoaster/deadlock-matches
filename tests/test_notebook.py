import ast
from pathlib import Path

import pytest

from deadlock_matches import config, queries, schemas

NOTEBOOKS = sorted((Path(__file__).parent.parent / "notebooks").glob("*.py"))


def notebook_tree(path):
    return ast.parse(path.read_text(encoding="utf-8"))


def attribute_names(tree, module):
    return {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == module
    }


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.name)
def test_notebook_parses(path):
    notebook_tree(path)


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.name)
def test_query_helpers_exist(path):
    for name in attribute_names(notebook_tree(path), "queries"):
        assert hasattr(queries, name), f"queries.{name} does not exist"


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.name)
def test_config_helpers_exist(path):
    for name in attribute_names(notebook_tree(path), "config"):
        assert hasattr(config, name), f"config.{name} does not exist"


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.name)
def test_table_names_are_real(path):
    table_calls = ("scan", "table_exists")

    for node in ast.walk(notebook_tree(path)):
        if not isinstance(node, ast.Call):
            continue

        func = node.func

        if not (isinstance(func, ast.Attribute) and func.attr in table_calls):
            continue

        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                assert arg.value in schemas.TABLES, f"unknown table {arg.value!r}"
