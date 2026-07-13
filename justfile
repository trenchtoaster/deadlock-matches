install-uv:
    #!/usr/bin/env bash
    if ! command -v uv &> /dev/null; then
        echo "Installing uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
    fi

install: install-uv
    @echo "-----------------------------------"
    @echo "- Installing dependencies -"
    @echo "-----------------------------------"
    uv sync

sync: install-uv
    @echo "-----------------------------------"
    @echo "- Syncing and upgrading dependencies -"
    @echo "-----------------------------------"
    uv sync --upgrade

format: install-uv
    @echo "-----------------------------------"
    @echo "- Formatting code -"
    @echo "-----------------------------------"
    uv run --group lint ruff format

lint: install-uv
    @echo "-----------------------------------"
    @echo "- Linting code -"
    @echo "-----------------------------------"
    uv run --group lint ruff check --fix

typecheck: install-uv
    @echo "-----------------------------------"
    @echo "- Running type checker -"
    @echo "-----------------------------------"
    uv run --group lint ty check

test: install-uv
    @echo "-----------------------------------"
    @echo "- Running tests -"
    @echo "-----------------------------------"
    uv run pytest tests

sweep *args: install-uv
    @echo "-----------------------------------"
    @echo "- Running the live CLI sweep -"
    @echo "-----------------------------------"
    @test -f tests/cli_sweep.sh || (echo "tests/cli_sweep.sh is a local maintainer script, skip this recipe" && exit 1)
    bash tests/cli_sweep.sh {{args}}

check: lint typecheck test

clean:
    @echo "-----------------------------------"
    @echo "- Cleaning build artifacts -"
    @echo "-----------------------------------"
    rm -rf build/ dist/ src/*.egg-info .pytest_cache .ruff_cache
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

build: clean
    @echo "-----------------------------------"
    @echo "- Building the package -"
    @echo "-----------------------------------"
    uv build

publish: check sweep build
    @echo "-----------------------------------"
    @echo "- Publishing to PyPI -"
    @echo "-----------------------------------"
    uv publish
