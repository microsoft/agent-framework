# Copyright (c) Microsoft. All rights reserved.

"""GAIA Benchmark Sample.

Run the GAIA (General AI Assistant) benchmark with configurable agent providers,
telemetry options, and benchmark parameters.

Agent Providers:
    - Azure AI (default): See azure_ai_agent.py for required environment variables
    - OpenAI: See openai_agent.py for required environment variables

Prerequisites:
    1. Set HF_TOKEN environment variable with your Hugging Face token:
       - Get token: https://huggingface.co/settings/tokens
       - Request dataset access: https://huggingface.co/datasets/gaia-benchmark/GAIA
       - Set: export HF_TOKEN="your-huggingface-token"

    2. Configure your chosen agent provider (see agent module files for details)

Telemetry:
    When using --otlp-endpoint or --trace-file, OpenTelemetry will export trace data
    in JSON format to the console in addition to the configured endpoints. This is
    expected behavior from the OpenTelemetry SDK and provides visibility into the
    telemetry being captured. The traces are also exported to:
    - OTLP endpoint (e.g., Aspire Dashboard) if --otlp-endpoint is specified
    - Local file if --trace-file is specified

    To suppress console output, redirect stderr: `python gaia_sample.py 2>/dev/null`

Usage:
    # Run with default settings (Azure AI agent)
    uv run python gaia_sample.py

    # Run with OpenAI agent
    uv run python gaia_sample.py --agent-provider openai

    # Run with telemetry export to Aspire Dashboard
    uv run python gaia_sample.py --otlp-endpoint http://localhost:4318

    # See all options
    uv run python gaia_sample.py --help
"""

import argparse

from agent_framework.lab.gaia import GAIA, Evaluation, GAIATelemetryConfig, Prediction, Task


async def evaluate_task(task: Task, prediction: Prediction) -> Evaluation:
    """Evaluate the prediction for a given task."""
    # Simple evaluation: check if the prediction contains the answer
    is_correct = (task.answer or "").lower() in prediction.prediction.lower()
    return Evaluation(is_correct=is_correct, score=1 if is_correct else 0)


async def main(
    otlp_endpoint: str | None = None,
    trace_file: str | None = None,
    result_file: str | None = None,
    data_dir: str | None = None,
    agent_provider: str = "azure-ai",
    level: int | list[int] = 1,
    max_n: int = 2,
    parallel: int = 1,
    timeout: int = 120,
) -> None:
    """Run GAIA benchmark with telemetry configuration.

    Args:
        otlp_endpoint: Optional OTLP endpoint URL for exporting traces (e.g., http://localhost:4318)
        trace_file: Optional file path to export traces to. If None, traces won't be saved to file.
        result_file: Optional file path to save benchmark results. If None, results won't be saved to file.
        data_dir: Directory to cache GAIA dataset. If None, uses temp directory.
        agent_provider: Agent provider to use: 'azure-ai' or 'openai' (default: 'azure-ai')
        level: GAIA level(s) to run (1, 2, or 3)
        max_n: Maximum number of tasks to run per level
        parallel: Number of parallel tasks to run
        timeout: Timeout per task in seconds
    """
    # Check for required Hugging Face token
    import logging
    import os

    # Suppress console logging for traces and verbose SDK output
    logging.getLogger("opentelemetry").setLevel(logging.ERROR)
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("agent_framework").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    # Suppress OpenTelemetry exporters console output
    import os as _os

    _os.environ.setdefault("OTEL_PYTHON_LOG_LEVEL", "error")

    # Print trace export configuration
    print("\n=== Telemetry Configuration ===")
    if trace_file:
        print(f"📁 Trace file: {os.path.abspath(trace_file)}")
    else:
        print("📁 Trace file: disabled")

    if otlp_endpoint:
        print(f"🌐 OTLP endpoint: {otlp_endpoint}")
    else:
        print("🌐 OTLP endpoint: disabled")

    if result_file:
        print(f"📊 Results file: {os.path.abspath(result_file)}")
    else:
        print("📊 Results file: disabled")

    print("\n=== Run Configuration ===")
    print(f"🤖 Agent provider: {agent_provider}")
    if data_dir:
        print(f"📂 Data directory: {os.path.abspath(data_dir)}")
    else:
        import tempfile
        from pathlib import Path

        default_data_dir = Path(tempfile.gettempdir()) / "data_gaia_hub"
        print(f"📂 Data directory: {default_data_dir} (default)")
    print(f"🎯 Level: {level}")
    print(f"🔢 Max tasks: {max_n}")
    print(f"⚡ Parallel: {parallel}")
    print(f"⏱️  Timeout: {timeout}s")
    print()

    # Import the appropriate agent factory based on provider
    if agent_provider == "azure-ai":
        from azure_ai_agent import create_gaia_agent
    elif agent_provider == "openai":
        from openai_agent import create_gaia_agent
    else:
        raise ValueError(f"Unknown agent provider: {agent_provider}. Use 'azure-ai' or 'openai'.")

    # Configure telemetry for tracing
    telemetry_config = GAIATelemetryConfig(
        enable_tracing=True,  # Enable OpenTelemetry tracing
        trace_to_file=trace_file is not None,  # Export traces to local file only if path provided
        file_path=trace_file,  # Custom file path for traces (can be None)
        otlp_endpoint=otlp_endpoint,  # Optional OTLP endpoint for Aspire Dashboard or other collectors
    )

    # Create a single agent once and reuse it for all tasks
    async with create_gaia_agent() as agent:

        async def run_task(task: Task) -> Prediction:
            """Run a single GAIA task and return the prediction using the shared agent."""
            input_message = f"Task: {task.question}"
            if task.file_name:
                input_message += f"\nFile: {task.file_name}"
            result = await agent.run(input_message)
            return Prediction(prediction=result.text, messages=result.messages)

        # Create the GAIA benchmark runner with telemetry configuration
        runner = GAIA(
            evaluator=evaluate_task,
            telemetry_config=telemetry_config,
            data_dir=data_dir,
        )

        # Run the benchmark with the task runner.
        # By default, this will check for locally cached benchmark data and checkout
        # the latest version from HuggingFace if not found.
        # Note: The GAIA dataset has been updated to use Parquet format.
        # If you encounter issues, try using validation split which has labeled data.
        results = await runner.run(
            run_task,
            level=level,
            max_n=max_n,
            parallel=parallel,
            timeout=timeout,
            out=result_file,  # Output file to save results including detailed traces (optional, None = no file output)
        )

    # Print summary similar to the viewer in gaia.py
    total = len(results)
    correct = sum(1 for r in results if r.evaluation.is_correct)
    accuracy = correct / total if total > 0 else 0.0
    avg_runtime = sum(r.runtime_seconds or 0 for r in results) / total if total > 0 else 0.0

    print("\n=== GAIA Benchmark Summary ===")
    print(f"📝 Total: {total}, ✅ Correct: {correct}, 🎯 Accuracy: {accuracy:.3f}")
    print(f"⏱️  Average runtime: {avg_runtime:.2f}s")
    if result_file:
        print(f"💾 Detailed results saved to: {result_file}")


if __name__ == "__main__":
    import asyncio

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Run GAIA benchmark with optional telemetry export to OTLP endpoint and/or file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with default settings
  python gaia_sample.py

  # Run with custom data directory
  python gaia_sample.py --data-dir ./gaia_data

  # Run with OpenAI agent provider
  python gaia_sample.py --agent-provider openai

  # Run with trace file export
  python gaia_sample.py --trace-file gaia_benchmark_traces.jsonl

  # Run level 2 tasks with 5 maximum tasks
  python gaia_sample.py --level 2 --max-n 5

  # Run with OTLP export to Aspire Dashboard and custom settings
  python gaia_sample.py --otlp-endpoint http://localhost:4318 --level 1 --max-n 10 --parallel 2

  # Run with all options configured
  python gaia_sample.py --agent-provider openai \
  --trace-file traces.jsonl \
  --result-file results.jsonl \
  --otlp-endpoint http://localhost:4318 --level 1 --max-n 5 --parallel 2 --timeout 180
        """,
    )
    parser.add_argument(
        "--otlp-endpoint",
        type=str,
        default=None,
        help="OTLP endpoint URL for exporting traces (e.g., http://localhost:4318 for Aspire Dashboard)",
    )
    parser.add_argument(
        "--trace-file",
        type=str,
        default=None,
        help="File path to export traces to (e.g., gaia_benchmark_traces.jsonl). "
        "If not set, traces won't be saved to file.",
    )
    parser.add_argument(
        "--result-file",
        type=str,
        default="gaia_results_level1.jsonl",
        help="File path to save benchmark results (default: gaia_results_level1.jsonl)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="Directory to cache GAIA dataset. If not set, uses system temp directory.",
    )
    parser.add_argument(
        "--agent-provider",
        type=str,
        default="azure-ai",
        choices=["azure-ai", "openai"],
        help="Agent provider to use: 'azure-ai' or 'openai' (default: 'azure-ai')",
    )
    parser.add_argument(
        "--level",
        type=int,
        default=1,
        choices=[1, 2, 3],
        help="GAIA benchmark level to run: 1, 2, or 3 (default: 1)",
    )
    parser.add_argument(
        "--max-n",
        type=int,
        default=2,
        help="Maximum number of tasks to run per level (default: 2)",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=1,
        help="Number of parallel tasks to run (default: 1)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Timeout per task in seconds (default: 120)",
    )
    args = parser.parse_args()

    asyncio.run(
        main(
            otlp_endpoint=args.otlp_endpoint,
            trace_file=args.trace_file,
            result_file=args.result_file,
            data_dir=args.data_dir,
            agent_provider=args.agent_provider,
            level=args.level,
            max_n=args.max_n,
            parallel=args.parallel,
            timeout=args.timeout,
        )
    )
