# Sample Validation System

An AI-powered workflow system for validating Python samples by discovering them, creating a nested batched workflow, and producing a report.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Sample Validation Workflow                        │
│                    (Sequential - 4 Executors)                        │
└─────────────────────────────────────────────────────────────────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        ▼                          ▼                          ▼
┌───────────────┐        ┌─────────────────┐        ┌─────────────────┐
│   Discover    │   ──►  │ Create Dynamic  │   ──►  │ Run Nested      │
│   Samples     │        │ Batched Flow    │        │ Workflow        │
└───────────────┘        └─────────────────┘        └─────────────────┘
        │                          │                          │
        ▼                          ▼                          ▼
  List[SampleInfo]          WorkflowCreationResult      ExecutionResult
                        (workers + coordinator)              │
                                                             ▼
                                                    ┌─────────────────┐
                                                    │ Generate Report │
                                                    └─────────────────┘
                                                             │
                                                             ▼
                                                          Report
```

### Nested Workflow Strategy

```
┌─────────────────────────────────────────────────────────────────────┐
│             Nested Batched Workflow (coordinator + workers)          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ WorkflowBuilder + fan-out/fan-in edges                      │   │
│  │ - Coordinator dispatches tasks in bounded batches           │   │
│  │ - Worker executors run GitHub Copilot agents               │   │
│  │ - Collector aggregates per-sample RunResult messages       │   │
│  │ - Max in-flight workers set by --max-parallel-workers      │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

## File Structure

```
samples/
├── _sample_validation/
│   ├── __init__.py              # Package exports
│   ├── README.md                # This file
│   ├── models.py                # Data classes
│   │   ├── SampleInfo           # Discovered sample metadata
│   │   ├── RunResult            # Execution result
│   │   └── Report               # Final validation report
│   ├── discovery.py             # Sample discovery
│   │   ├── discover_samples()   # Finds all .py files
│   │   └── DiscoverSamplesExecutor
│   ├── report.py                # Report generation
│   │   ├── generate_report()    # Create Report from results
│   │   ├── save_report()        # Write to markdown/JSON
│   │   ├── print_summary()      # Console output
│   │   └── GenerateReportExecutor
│   ├── create_dynamic_workflow_executor.py # Coordinator, workers, collector, CreateConcurrentValidationWorkflowExecutor
│   ├── run_dynamic_validation_workflow_executor.py # RunDynamicValidationWorkflowExecutor
│   └── workflow.py              # Workflow assembly entrypoint
├── __main__.py                  # CLI entry point
```

## Dependencies

### Required

- **agent-framework** - Core workflow and agent functionality
- **agent-framework-github-copilot** - GitHub Copilot agent integration

### Optional

- `GITHUB_COPILOT_MODEL` to override default Copilot model selection.

## Environment Variables

No required environment variables. Optional:

| Variable                 | Description                       | Required |
| ------------------------ | --------------------------------- | -------- |
| `GITHUB_COPILOT_MODEL`   | Copilot model override            | No       |
| `GITHUB_COPILOT_TIMEOUT` | Copilot request timeout (seconds) | No       |

## Usage

### Basic Usage

```bash
# Validate all samples
uv run python -m _sample_validation

# Validate specific subdirectory
uv run python -m _sample_validation --subdir 03-workflows

# Save reports to files
uv run python -m _sample_validation --save-report --output-dir ./reports
```

### Configuration Options

```bash
uv run python -m _sample_validation [OPTIONS]

Options:
  --subdir TEXT                Subdirectory to validate (relative to samples/)
  --output-dir TEXT            Report output directory (default: ./_sample_validation/reports)
  --max-parallel-workers INT   Max in-flight workers per batch (default: 10)
  --save-report                      Save reports to files
```

### Examples

```bash
# Quick validation of a small directory
uv run python -m _sample_validation --subdir 03-workflows/_start-here

# Limit parallel workers for large sample sets
uv run python -m _sample_validation --subdir 02-agents --max-parallel-workers 8

# Save report artifacts
uv run python -m _sample_validation --save-report
```

## How It Works

### 1. Discovery

Walks the samples directory and finds all `.py` files that:

- Don't start with `_` (excludes private files)
- Aren't in `__pycache__` directories
- Aren't in directories starting with `_` (excludes `_sample_validation`)

### 2. Dynamic Workflow Creation

Creates a nested workflow with:

- A coordinator executor
- One worker executor per discovered sample
- A collector executor

### 3. Nested Workflow Execution

The coordinator sends initial work to the first `max_parallel_workers` workers. As each worker finishes, it notifies
the coordinator, which dispatches the next queued sample. Workers also send result items to the collector, which emits
the final `ExecutionResult` once all samples are processed.

### 4. Report Generation

Produces:

- **Console summary** - Pass/fail counts with emoji indicators
- **Markdown report** - Detailed results grouped by status
- **JSON report** - Machine-readable for CI integration

## Report Status Codes

| Status  | Label     | Description                               |
| ------- | --------- | ----------------------------------------- |
| SUCCESS | [PASS]    | Sample ran to completion with exit code 0 |
| FAILURE | [FAIL]    | Sample exited with non-zero code          |
| TIMEOUT | [TIMEOUT] | Sample exceeded timeout limit             |
| ERROR   | [ERROR]   | Exception during execution                |

## Troubleshooting

### Agent output parsing errors

If an agent returns non-JSON content, that sample is marked as `ERROR` with parser details in the report.

### GitHub Copilot authentication or CLI issues

Ensure GitHub Copilot is authenticated in your environment and the Copilot CLI is available.
