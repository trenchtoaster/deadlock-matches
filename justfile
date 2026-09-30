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
    uv run --group lint ruff check .
    uv run --group lint ruff format --check .
    uv run --group lint ty check

typecheck: install-uv
    @echo "-----------------------------------"
    @echo "- Running type checker -"
    @echo "-----------------------------------"
    uv run --group lint ty check

changelog:
    @echo "-----------------------------------"
    @echo "- Updating changelog -"
    @echo "-----------------------------------"
    git-cliff --output CHANGELOG.md

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

protos: install-uv
    @echo "-----------------------------------"
    @echo "- Compiling the vendored protos -"
    @echo "-----------------------------------"
    uv run python -m grpc_tools.protoc -I protos --python_out=src/deadlock_matches/gen --pyi_out=src/deadlock_matches/gen citadel_gcmessages_common.proto base_gcmessages.proto gcsdk_gcmessages.proto steammessages.proto valveextensions.proto steammessages_steamlearn.steamworkssdk.proto steammessages_unified_base.steamworkssdk.proto
    @grep -h "Protobuf Python Version" src/deadlock_matches/gen/*_pb2.py | sort -u

check: lint test

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

publish: clean
    @echo "-----------------------------------"
    @echo "- Building and publishing to PyPI -"
    @echo "-----------------------------------"
    uv build
    uv publish
