# Copyright (c) Microsoft. All rights reserved.

import argparse
import asyncio
import json
import os
import traceback
from datetime import datetime
from typing import Any

from agent_framework.openai import OpenAIChatClient
from loguru import logger
from tau2.domains.airline.environment import get_tasks

from agent_framework_lab_tau2 import TaskRunner, patch_env_set_state


def to_dumpable(result: dict[str, Any]) -> dict[str, Any]:
    """Convert benchmark result to JSONL-serializable format.

    Handles both successful runs and error cases, ensuring consistent output
    format for downstream analysis. Converts Pydantic models to dictionaries
    and extracts enum values for JSON compatibility.
    """
    if "error" in result:
        # Error case: minimal structure with zero reward
        return {
            "id": result["task"].id,
            "error": result["error"],
            "evaluation": {
                "reward": 0.0,  # Standard zero reward for failed runs
            },
            "config": result["config"],
            "task": result["task"].model_dump(),
        }
    else:
        # Success case: full result structure
        return {
            "id": result["task"].id,
            "evaluation": result["evaluation"].model_dump(),  # Detailed evaluation metrics
            "config": result["config"],  # Model configuration used
            "termination_reason": result["termination_reason"].value,  # Enum to string
            "messages": [m.model_dump() for m in result["messages"]],  # Full conversation
            "task": result["task"].model_dump(),  # Task specification
        }


async def run_benchmark(assistant_model: str, user_model: str, debug_task_id: str | None, max_steps: int):
    """Run comprehensive tau2 benchmark evaluation using agent framework.

    This is the main function that:

    1. Sets up output file handling (full benchmark vs debug mode)
    2. Loads tau2 task dataset and configures LLM clients
    3. Runs each task through the agent framework workflow
    4. Evaluates performance using tau2's multi-dimensional metrics
    5. Aggregates results and calculates overall benchmark scores

    Args:
        assistant_model: Model ID for the customer service agent (e.g., "gpt-4o")
        user_model: Model ID for the user simulator (e.g., "gpt-4o")
        debug_task_id: Optional specific task ID to run (disables batch processing)
        max_steps: Maximum conversation steps before forced termination

    Output:
        Creates timestamped JSONL file with detailed results for analysis
        Prints summary statistics to console with colored logging
    """

    # STEP 1: Configure output handling based on execution mode
    result_fp = None
    if debug_task_id is None:
        # Full benchmark mode: create timestamped results file
        timestamp = datetime.now().strftime("%m%d%H%M")  # Format: MMDDHHMM
        result_filename = f"results/{assistant_model}_user-{user_model}_{timestamp}.jsonl"
        os.makedirs("results", exist_ok=True)
        result_fp = open(result_filename, "a")  # Append mode for resumability
        logger.info(f"Results will be saved to: {result_filename}")
    else:
        # Debug mode: single task, no file output, verbose logging
        logger.info(f"Debug mode: targeting task ID {debug_task_id}")

    # STEP 2: Load tau2 dataset and validate environment
    tasks = get_tasks()  # Loads all tau2 airline customer service tasks
    logger.info(f"Found {len(tasks)} tasks in the dataset")

    _logger = logger.opt(colors=True)  # Enable colored console output

    # Validate required OpenAI configuration
    # Both models use the same endpoint but can be different model types
    openai_base_url = os.getenv("OPENAI_BASE_URL")
    if openai_base_url is None:
        raise ValueError("OPENAI_BASE_URL must be set")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if openai_api_key is None:
        raise ValueError("OPENAI_API_KEY must be set")

    # STEP 3: Initialize LLM clients for both agent roles
    # Assistant: handles customer service with access to tools and policies
    assistant_chat_client = OpenAIChatClient(
        base_url=openai_base_url,
        api_key=openai_api_key,
        ai_model_id=assistant_model,
    )

    # User simulator: simulates realistic customer behavior and requests
    user_simulator_chat_client = OpenAIChatClient(
        base_url=openai_base_url,
        api_key=openai_api_key,
        ai_model_id=user_model,
    )

    # STEP 4: Filter task set for debug mode
    if debug_task_id is not None:
        tasks = [task for task in tasks if task.id == debug_task_id]
        if not tasks:
            logger.error(f"Task ID {debug_task_id} not found in dataset")
            return

    # STEP 5: Initialize evaluation tracking
    all_rewards: list[float] = []  # Stores reward scores for final statistics
    task_runner = TaskRunner(max_steps=max_steps)  # Reusable workflow orchestrator

    # STEP 6: Execute benchmark across all tasks
    for task in tasks:
        _logger.info(f"<red>Testing task #{task.id}</red>")
        _logger.info(f"<cyan>Purpose:</cyan> {task.description.purpose}")  # type: ignore

        # Initialize result structure for this task
        result: dict[str, Any] = {
            "config": {
                "assistant": assistant_chat_client.ai_model_id,
                "user": user_simulator_chat_client.ai_model_id,
            },
            "task": task,
        }

        # Log user scenario context for transparency
        if task.user_scenario and task.user_scenario.instructions:
            _logger.info(f"<cyan>User scenario:</cyan> {task.user_scenario.instructions.reason_for_call}")  # type: ignore

        try:
            # Execute the workflow: agent + user simulator conversation
            conversation = await task_runner.run(task, assistant_chat_client, user_simulator_chat_client)

            # Evaluate performance using tau2's comprehensive metrics
            reward_value = task_runner.evaluate(task, conversation, task_runner.termination_reason)

            # Store detailed results for analysis
            result["evaluation"] = task_runner.full_reward_info  # Full evaluation breakdown
            result["messages"] = conversation  # Complete conversation history
            result["termination_reason"] = task_runner.termination_reason  # How conversation ended

            # Log evaluation results (escape HTML for colored output)
            reward_str = str(task_runner.full_reward_info).replace("<", r"\<")
            _logger.info(f"<cyan>Final evaluation:</cyan> {reward_str}")

        except Exception as e:
            # Robust error handling: capture all failures for analysis
            _logger.error(f"<red>Error testing task #{task.id}:</red> {e}")
            result["error"] = traceback.format_exc()  # Full stack trace for debugging

            traceback.print_exc()  # Console output for immediate debugging
            reward_value = 0.0  # Zero score for failed runs

        # STEP 7: Persist results incrementally (enables partial analysis)
        if result_fp is not None:
            result_fp.write(json.dumps(to_dumpable(result), default=str) + "\n")

        all_rewards.append(reward_value)  # Track for final statistics

        # Reset runner state for next task
        task_runner.reinit()

    # STEP 8: Finalize and report aggregate results
    if result_fp is not None:
        result_fp.close()

    # Calculate overall benchmark performance
    all_accuracy = sum(all_rewards) / len(all_rewards) if all_rewards else 0.0

    # Report final statistics with colored formatting
    _logger.info("<green>Final Results:</green>")
    _logger.info(f"<cyan>All tasks accuracy:</cyan> {all_accuracy:.2f} ({int(sum(all_rewards))}/{len(tasks)})")


if __name__ == "__main__":
    """Command-line interface for tau2 benchmark execution.

    Provides flexible execution modes:

    - Full benchmark: Runs all tasks and generates timestamped results file
    - Debug mode: Single task execution with verbose logging for development
    - Environment patching: Optional compatibility layer for tau2-bench integration

    Usage Examples:
        # Full benchmark with default models
        python run_benchmark.py

        # Custom models
        python run_benchmark.py --assistant gpt-4o --user gpt-4o-mini

        # Debug specific task
        python run_benchmark.py --debug-task-id task_123

        # Disable environment patching for testing
        python run_benchmark.py --disable-env-patch
    """

    parser = argparse.ArgumentParser(description="Run tau2-agent-framework model test")

    # Model configuration arguments
    parser.add_argument("--assistant", type=str, default="gpt-4.1", help="Assistant model id, e.g., gpt-4.1-mini")
    parser.add_argument("--user", type=str, default="gpt-4.1", help="User model id")

    # Execution mode arguments
    parser.add_argument(
        "--debug-task-id", type=str, default=None, help="Debug a specific task ID (disables result file creation)"
    )
    parser.add_argument("--max-steps", type=int, default=100, help="Maximum number of steps to run")

    # Environment configuration arguments
    parser.add_argument("--disable-env-patch", action="store_true", help="Disable patching tau2-bench environment")

    args = parser.parse_args()

    # Apply environment patch for tau2-bench compatibility
    # This modifies tau2's environment to be more flexible with tool call validation
    if not args.disable_env_patch:
        patch_env_set_state()

    # Execute benchmark with configured parameters
    asyncio.run(
        run_benchmark(
            assistant_model=args.assistant,
            user_model=args.user,
            debug_task_id=args.debug_task_id,
            max_steps=args.max_steps,
        )
    )
