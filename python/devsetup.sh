uv python install 3.10 3.11 3.12 3.13
# Create a virtual environment with Python 3.10 (you can change this to 3.11, 3.12 or 3.13)
PYTHON_VERSION="3.13"
uv venv --python $PYTHON_VERSION
# Install AF and all dependencies
uv sync --dev
# Install all the tools and dependencies
uv run poe install
# Install pre-commit hooks
uv run poe pre-commit-install
