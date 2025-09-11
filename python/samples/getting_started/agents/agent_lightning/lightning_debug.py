import os
from agentlightning import LitAgent, Trainer
from agentlightning.types import NamedResources, TaskInput
from complex import loop, AgentConfiguration


class Tau2Agent(LitAgent):
    
    async def training_rollout_async(self, task: dict, rollout_id: str, resources: dict) -> float:
        proxy_base_url = os.getenv("PROXY_OPENAI_BASE_URL")
        proxy_api_key = os.getenv("PROXY_OPENAI_API_KEY")
        assert proxy_base_url is not None, "PROXY_OPENAI_BASE_URL must be set"
        assert proxy_api_key is not None, "PROXY_OPENAI_API_KEY must be set"

        main_llm = resources["main_llm"]

        assistant_config = AgentConfiguration(
            model=main_llm.sampling_parameters["model"],
            temperature=main_llm.sampling_parameters["temperature"],
            base_url=main_llm.endpoint,
            api_key="dummy",
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

        task_obj = Task(**task)
        result = await loop(task_obj, assistant_config, user_config, judge_config, max_steps=100)
        return result

    async def validation_rollout_async(self, task: dict, rollout_id: str, resources: dict) -> float:
        return await self.training_rollout_async(task, rollout_id, resources)


if __name__ == "__main__":
    trainer = Trainer(n_workers=1)
    agent = Tau2Agent()
    trainer.fit(agent)

