# type: ignore

import asyncio
import json
import os
import argparse
import pandas as pd
from datetime import datetime
from loguru import logger
from tau2.domains.airline.environment import get_environment, get_tasks
from tau2.data_model.tasks import Task
from complex import criteria, loop, AgentConfiguration


def to_dumpable(task: Task, result: dict) -> dict:
    return {
        "id": task.id,
        "evaluation": result["evaluation"].model_dump(),
        "config": result["config"],
        "termination_reason": result["termination_reason"].value,
        "messages": [m.model_dump() for m in result["messages"]],
        "task": task.model_dump(),
    }


async def main(assistant_model: str, assistant_sliding_window: int, user_model: str, judge_model: str, debug_task_id: str | None):
    # Read parquet files to get task counts
    train_tasks_df = pd.read_parquet("data/tasks_train.parquet")
    test_tasks_df = pd.read_parquet("data/tasks_test.parquet")
    total_tasks = len(train_tasks_df) + len(test_tasks_df)

    logger.info(f"Loaded tasks: {len(train_tasks_df)} train, {len(test_tasks_df)} test, {total_tasks} total")

    # Only create result file if not debugging a specific task
    result_fp = None
    if debug_task_id is None:
        timestamp = datetime.now().strftime("%m%d%H%M")
        result_filename = f"results/{assistant_model}_sw-{assistant_sliding_window}_user-{user_model}_judge-{judge_model}_{timestamp}.jsonl"
        result_fp = open(result_filename, "a")
    else:
        logger.info(f"Debug mode: targeting task ID {debug_task_id}")

    # Test the environment
    env = get_environment()
    tasks = get_tasks()

    logger.info(f"Found {len(tasks)} tasks in the dataset")
    logger.info(f"Environment has {len(env.get_tools())} tools: {', '.join([tool.name for tool in env.get_tools()])}")

    _logger = logger.opt(colors=True)

    proxy_base_url = os.getenv("PROXY_OPENAI_BASE_URL")
    proxy_api_key = os.getenv("PROXY_OPENAI_API_KEY")
    assert proxy_base_url is not None, "PROXY_OPENAI_BASE_URL must be set"
    assert proxy_api_key is not None, "PROXY_OPENAI_API_KEY must be set"

    assistant_config = AgentConfiguration(
        model=assistant_model,
        temperature=0.0,
        base_url=proxy_base_url,
        api_key=proxy_api_key,
        sliding_window=assistant_sliding_window,
    )
    user_config = AgentConfiguration(
        model=user_model,
        temperature=0.0,
        base_url=proxy_base_url,
        api_key=proxy_api_key,
        sliding_window=30000,  # long sliding window for user simulator
    )
    judge_config = AgentConfiguration(
        model=judge_model,
        temperature=0.0,
        base_url=proxy_base_url,
        api_key=proxy_api_key,
        sliding_window=0,  # Not used for judge
    )

    # Track accuracy for different subsets
    all_results = []
    train_results = []
    test_results = []

    # Get train and test task IDs for filtering
    train_task_ids = set(train_tasks_df["id"].tolist())
    test_task_ids = set(test_tasks_df["id"].tolist())

    # Filter tasks if debugging a specific task ID
    if debug_task_id is not None:
        tasks = [task for task in tasks if task.id == debug_task_id]
        if not tasks:
            logger.error(f"Task ID {debug_task_id} not found in dataset")
            return

    # Iterate over the tasks
    for task in tasks:
        _logger.info(f"<red>Testing task #{task.id}</red>")
        _logger.info(f"<cyan>Purpose:</cyan> {task.description.purpose}")

        if task.user_scenario and task.user_scenario.instructions:
            _logger.info(f"<cyan>User scenario:</cyan> {task.user_scenario.instructions.reason_for_call}")

        result = await loop(task, assistant_config, user_config, judge_config, max_steps=100)
        _logger.info(f"<cyan>Agent result - Termination:</cyan> {result.get('termination_reason')}")
        _logger.info(f"<cyan>Number of messages:</cyan> {len(result['messages'])}")

        reward = criteria(task, result, return_reward_info=True)
        result["evaluation"] = reward
        result["config"] = {
            "assistant": assistant_config,
            "user": user_config,
            "judge": judge_config,
        }
        reward_str = str(reward).replace("<", r"\<")
        _logger.info(f"<cyan>Final evaluation:</cyan> {reward_str}")

        if result_fp is not None:
            result_fp.write(json.dumps(to_dumpable(task, result), default=str) + "\n")

        # Track results by subset
        reward_value = reward.reward
        all_results.append(reward_value)

        if task.id in train_task_ids:
            train_results.append(reward_value)
        elif task.id in test_task_ids:
            test_results.append(reward_value)

    # Calculate and report accuracies
    if result_fp is not None:
        result_fp.close()

    all_accuracy = sum(all_results) / len(all_results) if all_results else 0.0
    train_accuracy = sum(train_results) / len(train_results) if train_results else 0.0
    test_accuracy = sum(test_results) / len(test_results) if test_results else 0.0

    _logger.info(f"<green>Final Results:</green>")
    _logger.info(f"<cyan>All tasks accuracy:</cyan> {all_accuracy:.2f} ({int(sum(all_results))}/{len(tasks)})")
    _logger.info(f"<cyan>Train tasks accuracy:</cyan> {train_accuracy:.2f} ({len(train_results)} tasks)")
    _logger.info(f"<cyan>Test tasks accuracy:</cyan> {test_accuracy:.2f} ({len(test_results)} tasks)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run tau2-agent-framework model test")
    parser.add_argument("--assistant", type=str, default="gpt-4.1-mini", help="Assistant model id, e.g., gpt-4.1-mini")
    parser.add_argument("--assistant-sliding-window", type=int, default=4000, help="Assistant sliding window size")
    parser.add_argument("--user-model", type=str, default="gpt-4o-mini", help="User model id")
    parser.add_argument("--judge-model", type=str, default="gpt-4o-mini", help="Judge model id")
    parser.add_argument("--debug-task-id", type=str, default=None, help="Debug a specific task ID (disables result file creation)")
    args = parser.parse_args()

    asyncio.run(
        main(
            assistant_model=args.assistant,
            assistant_sliding_window=args.assistant_sliding_window,
            user_model=args.user_model,
            judge_model=args.judge_model,
            debug_task_id=args.debug_task_id,
        )
    )
