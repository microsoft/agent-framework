# Copyright (c) Microsoft. All rights reserved.

from agent_framework.foundry import FoundryChatClient
from agent_framework.eval import GAIA, Task, Prediction, Evaluation
from azure.identity.aio import AzureCliCredential

async def run_task(task: Task) -> Prediction:
    """Run a single GAIA task and return the prediction."""
    # Since no Agent ID is provided, the agent will be automatically created
    # and deleted after getting a response
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        FoundryChatClient(async_credential=credential).create_agent(
            name="GaiaAgent",
            instructions="Solve tasks to your best ability.",
        ) as agent,
    ):
        input_message = f"Task: {task.question}"
        if task.file_name:
            input_message += f"\nFile: {task.file_name}"
        result = await agent.run(input_message)
        return Prediction(prediction=result.text, messages=result.messages)


async def evaluate_task(task: Task, prediction: Prediction) -> Evaluation:
    """Evaluate the prediction for a given task."""
    # Simple evaluation: check if the prediction contains the answer
    is_correct = task.answer.lower() in prediction.prediction.lower()
    return Evaluation(is_correct=is_correct, score=1 if is_correct else 0)


async def main() -> None:
    # Create the GAIA benchmark runner with default settings and evaluation function.
    runner = GAIA(evaluator=evaluate_task)

    # Run the benchmark with the task runner.
    # By default, this will check for locally cached benchmark data and checkout
    # the latest version from HuggingFace if not found.
    results = await runner.run(
        run_task, 
        level=1, # Level 1, 2, or 3 or multiple levels like [1, 2]
        max_n=5, # Maximum number of tasks to run per level
        parallel=2, # Number of parallel tasks to run
        timeout=60, # Timeout per task in seconds
        out="gaia_results_level1.jsonl" # Output file to save results (optional)
        traces_out="gaia_results_level1_traces" # Directory to save detailed OTel traces by task ID (optional)
    )

    # Print the results.
    print("\n=== GAIA Benchmark Results ===")
    for result in results:
        print(f"\n--- Task ID: {result.task_id} ---")
        print(f"Task: {result.task}")
        print(f"Prediction: {result.prediction}")
        print(f"Evaluation: {result.evaluation}")