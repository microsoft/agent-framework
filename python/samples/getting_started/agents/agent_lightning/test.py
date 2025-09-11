# type: ignore

import asyncio
import json
import os
from loguru import logger
from tau2.domains.airline.environment import get_environment, get_tasks
from tau2.data_model.tasks import Task
from complex import criteria, loop, AgentConfiguration


def to_dumpable(task: Task, result: dict) -> dict:
    return {
        "id": task.id,
        "evaluation": result['evaluation'].model_dump(),
        "termination_reason": result['termination_reason'].value,
        "messages": [m.model_dump() for m in result['messages']],
        "task": task.model_dump(),
    }


async def main(model: str = "gpt-4.1-mini"):
    result_fp = open(f"results/{model}.jsonl", "a")

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
        model=model,
        temperature=0.0,
        base_url=proxy_base_url,
        api_key=proxy_api_key,
        sliding_window=4000,
    )
    user_config = AgentConfiguration(
        model="gpt-4o-mini",
        temperature=0.0,
        base_url=proxy_base_url,
        api_key=proxy_api_key,
        sliding_window=30000,  # long sliding window for user simulator
    )
    judge_config = AgentConfiguration(
        model="gpt-4o-mini",
        temperature=0.0,
        base_url=proxy_base_url,
        api_key=proxy_api_key,
        sliding_window=0,  # Not used for judge
    )

    # Iterate over the tasks
    for task in tasks[:1]:  # Test with first tasks
        _logger.info(f"<red>Testing task #{task.id}</red>")
        _logger.info(f"<cyan>Purpose:</cyan> {task.description.purpose}")

        if task.user_scenario and task.user_scenario.instructions:
            _logger.info(f"<cyan>User scenario:</cyan> {task.user_scenario.instructions.reason_for_call}")

        result = await loop(task, assistant_config, user_config, judge_config, max_steps=100)
        _logger.info(f"<cyan>Agent result - Termination:</cyan> {result.get('termination_reason')}")
        _logger.info(f"<cyan>Number of messages:</cyan> {len(result['messages'])}")

        reward = criteria(task, result, return_reward_info=True)
        result['evaluation'] = reward
        _logger.info(f"<cyan>Final evaluation:</cyan> {reward}")

        result_fp.write(json.dumps(to_dumpable(task, result)) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
