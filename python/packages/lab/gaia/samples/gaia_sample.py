# Copyright (c) Microsoft. All rights reserved.

"""
GAIA Benchmark Sample

To run this sample, execute it from the root directory of the agent-framework repository:
    cd /path/to/agent-framework
    uv run python python/packages/lab/gaia/gaia_sample.py

This avoids namespace package conflicts that occur when running from within the gaia package directory.
"""

from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential

from agent_framework.lab.gaia import GAIA, Evaluation, GAIATelemetryConfig, Prediction, Task


async def evaluate_task(task: Task, prediction: Prediction) -> Evaluation:
    """Evaluate the prediction for a given task."""
    # Simple evaluation: check if the prediction contains the answer
    is_correct = (task.answer or "").lower() in prediction.prediction.lower()
    return Evaluation(is_correct=is_correct, score=1 if is_correct else 0)


async def main() -> None:
    # Configure telemetry for tracing
    telemetry_config = GAIATelemetryConfig(
        enable_tracing=True,  # Enable OpenTelemetry tracing
        # Optional: Configure external endpoints
        # otlp_endpoint="http://localhost:4317",  # For Aspire Dashboard or other OTLP endpoints
        # applicationinsights_connection_string="your_connection_string",  # For Azure Monitor
        # enable_live_metrics=True,  # Enable Azure Monitor live metrics
        # Configure local file tracing
        trace_to_file=True,  # Export traces to local file
        file_path="gaia_benchmark_traces.jsonl",  # Custom file path for traces
    )

    # Create a single agent once and reuse it for all tasks
    async with (
        AzureCliCredential() as credential,
        FoundryChatClient(async_credential=credential).create_agent(
            name="GaiaAgent",
            instructions="Solve tasks to your best ability.",
        ) as agent,
    ):

        async def run_task(task: Task) -> Prediction:
            """Run a single GAIA task and return the prediction using the shared agent."""
            input_message = f"Task: {task.question}"
            if task.file_name:
                input_message += f"\nFile: {task.file_name}"
            result = await agent.run(input_message)
            return Prediction(prediction=result.text, messages=result.messages)

        # Create the GAIA benchmark runner with telemetry configuration
        runner = GAIA(evaluator=evaluate_task, telemetry_config=telemetry_config)

        # Run the benchmark with the task runner.
        # By default, this will check for locally cached benchmark data and checkout
        # the latest version from HuggingFace if not found.
        results = await runner.run(
            run_task,
            level=1,  # Level 1, 2, or 3 or multiple levels like [1, 2]
            max_n=5,  # Maximum number of tasks to run per level
            parallel=2,  # Number of parallel tasks to run
            timeout=60,  # Timeout per task in seconds
            out="gaia_results_level1.jsonl",  # Output file to save results including detailed traces (optional)
        )

    # Print the results.
    print("\n=== GAIA Benchmark Results ===")
    for result in results:
        print(f"\n--- Task ID: {result.task_id} ---")
        print(f"Task: {result.task.question[:100]}...")
        print(f"Prediction: {result.prediction.prediction}")
        print(f"Evaluation: Correct={result.evaluation.is_correct}, Score={result.evaluation.score}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
