# Evaluations

## GAIA

1. Python deps

uv venv && source .venv/bin/activate # or: python -m venv .venv && source .venv/bin/activate
pip install "openai>=1.51" datasets huggingface_hub tqdm tenacity orjson

2. Auth

export OPENAI*API_KEY="sk-..." # your key
export HF_TOKEN="hf*..." # must have access to gaia-benchmark/GAIA

3. Run (examples)

python gaia.py --levels 1 --max-n 50 --parallel 8
python gaia.py --levels 1 2 --parallel 16 --model "gpt-4.1-mini"

## GAIA Result Viewer

A simple console viewer for analyzing GAIA evaluation results using [Rich](https://rich.readthedocs.io/).

```bash
# View summary of results (default dataset location: data_gaia_hub)
uv run python gaia_viewer.py results.jsonl

# View detailed results for each task
uv run python gaia_viewer.py results.jsonl --detailed

# Specify custom dataset directory
uv run python gaia_viewer.py results.jsonl --dataset-dir ./my_gaia_dataset

# Save output to HTML file
uv run python gaia_viewer.py results.jsonl --output-html results_report.html

# View help
uv run python gaia_viewer.py --help
```
