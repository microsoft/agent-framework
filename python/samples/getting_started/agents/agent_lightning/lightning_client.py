# type: ignore

import json
import os
from datetime import datetime
from loguru import logger
from agentlightning import LitAgent, Trainer, configure_logger
from tau2.data_model.tasks import Task as Tau2Task
from complex import criteria, loop, AgentConfiguration

proxy_base_url = os.getenv("PROXY_OPENAI_BASE_URL")
proxy_api_key = os.getenv("PROXY_OPENAI_API_KEY")
timestamp = datetime.now().strftime("%m%d%H%M")  # for logging
output_dir = f"outputs/client/{timestamp}"

def to_dumpable(task: Tau2Task, result: dict) -> dict:
    if "error" in result:
        return {
            "id": task.id,
            "error": result["error"],
            "evaluation": {
                "reward": 0.0,
            },
            "config": result["config"],
            "task": task.model_dump(),
        }
    else:
        return {
            "id": task.id,
            "evaluation": result["evaluation"].model_dump(),
            "config": result["config"],
            "termination_reason": result["termination_reason"].value,
            "messages": [m.model_dump() for m in result["messages"]],
            "task": task.model_dump(),
        }


class Tau2Agent(LitAgent):

    async def training_rollout_async(self, task: dict, rollout_id: str, resources: dict) -> float:
        assert proxy_base_url is not None, "PROXY_OPENAI_BASE_URL must be set"
        assert proxy_api_key is not None, "PROXY_OPENAI_API_KEY must be set"

        main_llm = resources["main_llm"]

        assistant_config = AgentConfiguration(
            model=main_llm.model,
            temperature=main_llm.sampling_parameters["temperature"],
            base_url=main_llm.endpoint,
            api_key=proxy_api_key if main_llm.endpoint == proxy_base_url else "dummy",
            sliding_window=4000,
            # We have to reserve the buffer for tool calls. It will be around 7000 in runtime.
        )
        user_config = AgentConfiguration(
            model="gpt-4.1",
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

        task_obj = Tau2Task.model_validate(task)
        _logger = logger.opt(colors=True)
        _logger.info(f"<cyan>[TASK]\n{str(task_obj)}</cyan>")
        result = await loop(task_obj, assistant_config, user_config, judge_config, max_steps=100)
        _logger.info(f"<cyan>Agent result - Termination:</cyan> {result.get('termination_reason')}")
        _logger.info(f"<cyan>Number of messages:</cyan> {len(result['messages'])}")

        reward = criteria(task_obj, result, return_reward_info=True)
        _logger.info(f"<cyan>Final reward:</cyan> {reward.reward}")

        result["evaluation"] = reward
        result["config"] = {
            "assistant": assistant_config,
            "user": user_config,
            "judge": judge_config,
        }

        os.makedirs(output_dir, exist_ok=True)
        with open(f"{output_dir}/{self.runner.worker_id}.jsonl", "a") as f:
            f.write(json.dumps(to_dumpable(task, result), default=str) + "\n")

        return reward.reward

    async def validation_rollout_async(self, task: dict, rollout_id: str, resources: dict) -> float:
        return await self.training_rollout_async(task, rollout_id, resources)


if __name__ == "__main__":
    configure_logger()
    trainer = Trainer(n_workers=4)
    agent = Tau2Agent(trained_agents="assistant_agent")
    trainer.fit(agent, "http://localhost:9991")
