# Copyright (c) Microsoft. All rights reserved.

"""Advanced example showing multi-agent RL training using Tau2 benchmark.

This demonstrates:
- LitAgent class-based approach (vs @rollout decorator)
- Multi-agent scenarios with agent filtering
- Resource management for complex setups
- Integration with external benchmarks

Builds on concepts from train_math_agent.py with additional complexity.
Requires one GPU of at least 80GB of memory.
"""

import argparse
import asyncio
import json
import os
import random
import traceback
from pathlib import Path
from typing import TypedDict, cast

from agent_framework.lab.tau2 import ASSISTANT_AGENT_ID, patch_env_set_state  # type: ignore
from agent_framework.lab.tau2 import TaskRunner as Tau2TaskRunner  # type: ignore
from agent_framework.openai import OpenAIChatClient
from agent_framework_lab_lightning import init as lightning_init
from agentlightning import LLM, Dataset, LitAgent, NamedResources, Rollout, Trainer
from agentlightning.algorithm.verl import VERL
from tau2.data_model.tasks import Task as Tau2Task  # type: ignore[import-untyped]


# Tau2 tasks are complex objects that need special handling during distributed training
class SerializedTask(TypedDict):
    """Tau2 task object type."""

    id: str
    data: str  # JSON-serialized task data to prevent HuggingFace conversion issues


def _load_dataset() -> tuple[Dataset[SerializedTask], Dataset[SerializedTask]]:
    """Load and prepare Tau2 dataset with proper serialization.

    It takes external data dependency (TAU2_DATA_DIR) and uses deterministic train/val split for reproducibility.
    """
    data_dir = os.getenv("TAU2_DATA_DIR")
    if data_dir is None:
        raise ValueError("TAU2_DATA_DIR must be set")
    tasks_path = Path(data_dir) / "tau2/domains/airline/tasks.json"
    with tasks_path.open("r") as f:
        dataset = json.load(f)

    # Serialize complex task objects to prevent HuggingFace tokenizer issues
    dataset = [{"id": task["id"], "data": json.dumps(task)} for task in dataset]

    # Deterministic train/val split (25/25) for reproducible experiments
    random_state = random.Random(42)  # noqa: S311
    indices = list(range(len(dataset)))
    random_state.shuffle(indices)
    train_indices = indices[: int(len(dataset) * 0.5)]
    val_indices = indices[int(len(dataset) * 0.5) :]
    print(f"Train indices: {train_indices}")
    print(f"Val indices: {val_indices}")
    train_dataset = [dataset[i] for i in train_indices]
    val_dataset = [dataset[i] for i in val_indices]

    return cast(Dataset[SerializedTask], train_dataset), cast(Dataset[SerializedTask], val_dataset)


# Alternative to @rollout: LitAgent class for advanced scenarios
# Use this approach when you need:
# - Agent filtering (training only specific agents in multi-agent setup)
# - Resource management (multiple LLMs, databases, etc.)
# - Complex initialization logic
class Tau2Agent(LitAgent):
    """Class-based agent with advanced resource management and agent filtering."""

    async def rollout_async(self, task: SerializedTask, resources: NamedResources, rollout: Rollout) -> float:
        """The main rollout method. Similar to @rollout but with more control."""
        llm = resources.get("main_llm")
        if not isinstance(llm, LLM):
            raise ValueError("main_llm must be an instance of LLM")

        openai_base_url = os.getenv("OPENAI_BASE_URL")
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if openai_base_url is None:
            raise ValueError("OPENAI_BASE_URL must be set")
        if openai_api_key is None:
            raise ValueError("OPENAI_API_KEY must be set")

        # Deserialize the complex task object
        task_data = json.loads(task["data"])
        task_obj = Tau2Task(**task_data)

        # Multi-agent setup: assistant (trainable) + user simulator (fixed)
        runner = Tau2TaskRunner(
            max_steps=100,
            assistant_window_size=4000,
            assistant_sampling_temperature=llm.sampling_parameters.get("temperature", 0.0),
        )

        # Assistant agent: uses the model being trained
        assistant_chat_client = OpenAIChatClient(
            base_url=llm.endpoint,  # vLLM endpoint for the model being trained
            api_key=openai_api_key,
            model_id=llm.model,  # Model ID being trained
        )

        # User simulator: uses a fixed, capable model for consistent simulation
        user_simulator_chat_client = OpenAIChatClient(
            base_url=openai_base_url,  # External API endpoint
            api_key=openai_api_key,
            model_id="gpt-4.1",  # Fixed model for user simulator
        )

        try:
            # Run the multi-agent conversation
            conversation = await runner.run(task_obj, assistant_chat_client, user_simulator_chat_client)
        except Exception:
            # Handle failures gracefully - assign low reward to discourage problematic behavior
            # Common issues: tool calling errors, timeout, invalid responses
            traceback.print_exc()
            return 0.0

        # Use Tau2's built-in evaluation metrics
        evaluation = runner.evaluate(task_obj, conversation, runner.termination_reason)

        # Return the evaluation score
        return evaluation  # noqa: RET504


def main():
    """Main entrypoint."""
    # RL config with higher resource requirements and W&B logging
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
            "rollout": {
                "tensor_model_parallel_size": 1,
                "n": 8,  # Higher repetition for more data per task
                "log_prob_micro_batch_size_per_gpu": 4,
                "multi_turn": {"format": "hermes"},
                "name": "vllm",
                "gpu_memory_utilization": 0.8,  # Higher utilization for 80GB GPU
            },
            "actor": {
                "ppo_mini_batch_size": 8,
                "ppo_micro_batch_size_per_gpu": 4,
                "optim": {"lr": 1e-6},
                "use_kl_loss": False,
                "clip_ratio_low": 0.2,
                "clip_ratio_high": 0.3,
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
        "trainer": {
            "n_gpus_per_node": 1,
            "val_before_train": True,
            "logger": ["console", "wandb"],  # Wandb for experiment tracking
            "project_name": "agent-framework-lab-lightning",
            "experiment_name": "tau2_agent",
            "nnodes": 1,
            "test_freq": 4,
            "total_epochs": 8,
        },
    }

    lightning_init()
    patch_env_set_state()  # Tau2-specific environment setup

    train_dataset, val_dataset = _load_dataset()

    # Key difference with math_agent: trained_agents parameter specifies which agents to train
    # Only the assistant agent is trained; user simulator remains fixed
    tau2_agent = Tau2Agent(trained_agents=ASSISTANT_AGENT_ID)

    trainer = Trainer(algorithm=VERL(rl_training_config), n_workers=4)
    trainer.fit(tau2_agent, train_dataset, val_data=val_dataset)


def debug():
    """Debug mode for testing multi-agent setup and Tau2 integration."""
    lightning_init()

    train_dataset, _ = _load_dataset()
    tau2_agent = Tau2Agent(trained_agents=ASSISTANT_AGENT_ID)

    openai_base_url = os.getenv("OPENAI_BASE_URL")
    if openai_base_url is None:
        raise ValueError("OPENAI_BASE_URL must be set")

    patch_env_set_state()  # Required for Tau2 environment

    # Test with resources dict (different from @rollout LLM parameter)
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
