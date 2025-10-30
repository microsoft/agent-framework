# Agent Framework Lab - GAIA

The GAIA benchmark can be used for evaluating agents and workflows built using the Agent Framework.
It includes built-in benchmarks as well as utilities for running custom evaluations.

> **Note**: This module is part of the consolidated `agent-framework-lab` package. Install the package with the `gaia` extra to use this module.

## Setup

Install the `agent-framework-lab` package with GAIA dependencies:

```bash
pip install "agent-framework-lab[gaia]"
```

Set up Hugging Face token:

```bash
export HF_TOKEN="hf\*..." # must have access to gaia-benchmark/GAIA
```

## Create an evaluation script

Create a Python script (e.g., `run_gaia.py`) with the following content:

```python
from agent_framework.lab.gaia import GAIA, Task, Prediction, GAIATelemetryConfig

async def run_task(task: Task) -> Prediction:
    return Prediction(prediction="answer here", messages=[])

async def main() -> None:
    # Optional: Enable telemetry for detailed tracing
    telemetry_config = GAIATelemetryConfig(
        enable_tracing=True,
        trace_to_file=True,
        file_path="gaia_traces.jsonl"
    )

    runner = GAIA(telemetry_config=telemetry_config)
    await runner.run(run_task, level=1, max_n=5, parallel=2)
```

See the [gaia_sample.py](./samples/gaia_sample.py) for more detail.

## View results

We provide a console viewer for reading GAIA results:

```bash
uv run gaia_viewer "gaia_results_<timestamp>.jsonl" --detailed
```
