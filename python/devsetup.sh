uv python install 3.11 3.12 3.13 3.14 3.15
# Create a virtual environment with a supported Python version.
PYTHON_VERSION="3.13"
uv venv --python $PYTHON_VERSION
# Install AF and all dependencies
uv run poe install
# Install prek hooks
uv run poe prek-install
