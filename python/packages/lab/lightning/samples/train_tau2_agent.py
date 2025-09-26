# Copyright (c) Microsoft. All rights reserved.

"""This sample performs RL training for a tau2 agent from `agent-framework-lab-tau2`.
It's based on the airline domain dataset.

It requires one GPU of at least 80GB of memory.
"""

import argparse
import asyncio
import json
import os
import random
from pathlib import Path
from typing import Any, cast

from agent_framework.lab.tau2 import ASSISTANT_AGENT_ID, patch_env_set_state  # type: ignore
from agent_framework.lab.tau2 import TaskRunner as Tau2TaskRunner  # type: ignore
from agent_framework.openai import OpenAIChatClient
from agentlightning import LLM, Dataset, LitAgent, NamedResources, Rollout, Trainer
from agentlightning.algorithm.verl import VERL
from tau2.data_model.tasks import Task as Tau2Task  # type: ignore[import-untyped]

from agent_framework_lab_lightning import init as lightning_init


def _load_dataset() -> tuple[Dataset[dict[str, Any]], Dataset[dict[str, Any]]]:
    data_dir = os.getenv("TAU2_DATA_DIR")
    if data_dir is None:
        raise ValueError("TAU2_DATA_DIR must be set")
    tasks_path = Path(data_dir) / "tau2/domains/airline/tasks.json"
    with tasks_path.open("r") as f:
        dataset = json.load(f)

    # Randomly split the dataset into train and val
    random_state = random.Random(42)
    indices = list(range(len(dataset)))
    random_state.shuffle(indices)
    train_indices = indices[: int(len(dataset) * 0.5)]
    val_indices = indices[int(len(dataset) * 0.5) :]
    print(f"Train indices: {train_indices}")
    print(f"Val indices: {val_indices}")
    train_dataset = [dataset[i] for i in train_indices]
    val_dataset = [dataset[i] for i in val_indices]

    return cast(Dataset[dict[str, Any]], train_dataset), cast(Dataset[dict[str, Any]], val_dataset)


class Tau2Agent(LitAgent):
    async def rollout_async(self, task: dict[str, Any], resources: NamedResources, rollout: Rollout) -> float:
        # The agent to be trained can also be written in a class-based way,
        # for richer customization like selecting the agents to be trained with `trained_agents` parameter.

        llm = resources.get("main_llm")
        if not isinstance(llm, LLM):
            raise ValueError("main_llm must be an instance of LLM")

        openai_base_url = os.getenv("OPENAI_BASE_URL")
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if openai_base_url is None:
            raise ValueError("OPENAI_BASE_URL must be set")
        if openai_api_key is None:
            raise ValueError("OPENAI_API_KEY must be set")

        task_obj = Tau2Task(**task)
        runner = Tau2TaskRunner(
            max_steps=100,
            assistant_window_size=4000,
            assistant_sampling_temperature=llm.sampling_parameters.get("temperature", 0.0),
        )
        assistant_chat_client = OpenAIChatClient(
            base_url=llm.endpoint,  # The model to be trained
            api_key=openai_api_key,
            ai_model_id=llm.model,  # The model to be trained
        )
        user_simulator_chat_client = OpenAIChatClient(
            base_url=openai_base_url,
            api_key=openai_api_key,
            ai_model_id="gpt-4.1",  # Fixed model for user simulator
        )
        conversation = await runner.run(task_obj, assistant_chat_client, user_simulator_chat_client)
        evaluation = runner.evaluate(task_obj, conversation, runner.termination_reason)
        return evaluation


def main():
    rl_training_config = {
        "agentlightning": {
            "port": 9999,
        },
        "algorithm": {"adv_estimator": "grpo"},
        "data": {
            "train_batch_size": 8,
            "max_prompt_length": 8192,
            "max_response_length": 2048,
        },
        "actor_rollout_ref": {
            # Rollout configuration
            "rollout": {
                "tensor_model_parallel_size": 1,
                "n": 8,
                "log_prob_micro_batch_size_per_gpu": 4,
                "multi_turn": {"format": "hermes"},
                "name": "vllm",
                "gpu_memory_utilization": 0.8,
            },
            # Actor training config
            "actor": {
                "ppo_mini_batch_size": 8,
                "ppo_micro_batch_size_per_gpu": 4,
                # Optimizer configuration
                "optim": {"lr": 1e-6},
                "use_kl_loss": False,
                "clip_ratio_low": 0.2,
                "clip_ratio_high": 0.3,
                # FSDP (Fully Sharded Data Parallel) configuration for memory efficiency
                # Useful when you don't have enough GPU memory
                "fsdp_config": {
                    "param_offload": True,
                    "optimizer_offload": True,
                },
            },
            # Reference model config
            "ref": {
                "log_prob_micro_batch_size_per_gpu": 8,
                "fsdp_config": {"param_offload": True},
            },
            # Common configs for the model
            "model": {
                "path": "Qwen/Qwen2.5-1.5B-Instruct",
                "use_remove_padding": True,
                "enable_gradient_checkpointing": True,
            },
        },
        # Config for the trainer
        "trainer": {
            "n_gpus_per_node": 1,
            "val_before_train": True,
            "logger": ["console", "wandb"],
            "project_name": "agent-framework-lab-lightning",
            "experiment_name": "tau2_agent",
            "nnodes": 1,
            "test_freq": 4,
            "total_epochs": 8,
        },
    }

    lightning_init()
    patch_env_set_state()

    train_dataset, val_dataset = _load_dataset()
    tau2_agent = Tau2Agent(trained_agents=ASSISTANT_AGENT_ID)

    trainer = Trainer(algorithm=VERL(rl_training_config), n_workers=4)
    trainer.fit(tau2_agent, train_dataset, val_data=val_dataset)


def debug():
    lightning_init()

    train_dataset, _ = _load_dataset()
    tau2_agent = Tau2Agent(trained_agents=ASSISTANT_AGENT_ID)

    openai_base_url = os.getenv("OPENAI_BASE_URL")
    if openai_base_url is None:
        raise ValueError("OPENAI_BASE_URL must be set")

    patch_env_set_state()

    asyncio.run(
        tau2_agent.rollout_async(
            train_dataset[0],
            resources={"main_llm": LLM(model="gpt-4.1", endpoint=openai_base_url)},
            rollout=Rollout(rollout_id="dummy"),
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    if args.debug:
        debug()
    else:
        main()
