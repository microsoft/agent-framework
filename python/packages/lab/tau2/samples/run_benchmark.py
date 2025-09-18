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
    if "error" in result:
        return {
            "id": result["task"].id,
            "error": result["error"],
            "evaluation": {
                "reward": 0.0,
            },
            "config": result["config"],
            "task": result["task"].model_dump(),
        }
    else:
        return {
            "id": result["task"].id,
            "evaluation": result["evaluation"].model_dump(),
            "config": result["config"],
            "termination_reason": result["termination_reason"].value,
            "messages": [m.model_dump() for m in result["messages"]],
            "task": result["task"].model_dump(),
        }


async def run_benchmark(assistant_model: str, user_model: str, debug_task_id: str | None, max_steps: int):
    # Only create result file if not debugging a specific task
    result_fp = None
    if debug_task_id is None:
        timestamp = datetime.now().strftime("%m%d%H%M")
        result_filename = f"results/{assistant_model}_user-{user_model}_{timestamp}.jsonl"
        result_fp = open(result_filename, "a")
    else:
        logger.info(f"Debug mode: targeting task ID {debug_task_id}")

    tasks = get_tasks()

    logger.info(f"Found {len(tasks)} tasks in the dataset")

    _logger = logger.opt(colors=True)

    openai_base_url = os.getenv("OPENAI_BASE_URL")
    if openai_base_url is None:
        raise ValueError("OPENAI_BASE_URL must be set")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if openai_api_key is None:
        raise ValueError("OPENAI_API_KEY must be set")

    assistant_chat_client = OpenAIChatClient(
        base_url=openai_base_url,
        api_key=openai_api_key,
        ai_model_id=assistant_model,
    )
    user_simulator_chat_client = OpenAIChatClient(
        base_url=openai_base_url,
        api_key=openai_api_key,
        ai_model_id=user_model,
    )

    # Filter tasks if debugging a specific task ID
    if debug_task_id is not None:
        tasks = [task for task in tasks if task.id == debug_task_id]
        if not tasks:
            logger.error(f"Task ID {debug_task_id} not found in dataset")
            return

    all_rewards: list[float] = []

    task_runner = TaskRunner(max_steps=max_steps)

    # Iterate over the tasks
    for task in tasks:
        _logger.info(f"<red>Testing task #{task.id}</red>")
        _logger.info(f"<cyan>Purpose:</cyan> {task.description.purpose}")  # type: ignore

        result: dict[str, Any] = {
            "config": {
                "assistant": assistant_chat_client.ai_model_id,
                "user": user_simulator_chat_client.ai_model_id,
            },
            "task": task,
        }

        if task.user_scenario and task.user_scenario.instructions:
            _logger.info(f"<cyan>User scenario:</cyan> {task.user_scenario.instructions.reason_for_call}")  # type: ignore

        try:
            conversation = await task_runner.run(task, assistant_chat_client, user_simulator_chat_client)
            reward_value = task_runner.evaluate(task, conversation, task_runner.termination_reason)
            result["evaluation"] = task_runner.full_reward_info
            result["messages"] = conversation
            result["termination_reason"] = task_runner.termination_reason

            reward_str = str(task_runner.full_reward_info).replace("<", r"\<")  # Escape for loguru colored logging
            _logger.info(f"<cyan>Final evaluation:</cyan> {reward_str}")

        except Exception as e:
            # Catch all errors
            _logger.error(f"<red>Error testing task #{task.id}:</red> {e}")
            result["error"] = traceback.format_exc()

            traceback.print_exc()
            reward_value = 0.0

        if result_fp is not None:
            result_fp.write(json.dumps(to_dumpable(result), default=str) + "\n")

        all_rewards.append(reward_value)

    # Calculate and report accuracies
    if result_fp is not None:
        result_fp.close()

    all_accuracy = sum(all_rewards) / len(all_rewards) if all_rewards else 0.0

    _logger.info("<green>Final Results:</green>")
    _logger.info(f"<cyan>All tasks accuracy:</cyan> {all_accuracy:.2f} ({int(sum(all_rewards))}/{len(tasks)})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run tau2-agent-framework model test")
    parser.add_argument("--assistant", type=str, default="gpt-4.1", help="Assistant model id, e.g., gpt-4.1-mini")
    parser.add_argument("--user", type=str, default="gpt-4.1", help="User model id")
    parser.add_argument(
        "--debug-task-id", type=str, default=None, help="Debug a specific task ID (disables result file creation)"
    )
    parser.add_argument("--disable-env-patch", action="store_true", help="Disable patching tau2-bench environment")
    parser.add_argument("--max-steps", type=int, default=100, help="Maximum number of steps to run")
    args = parser.parse_args()

    if not args.disable_env_patch:
        patch_env_set_state()

    asyncio.run(
        run_benchmark(
            assistant_model=args.assistant,
            user_model=args.user,
            debug_task_id=args.debug_task_id,
            max_steps=args.max_steps,
        )
    )
