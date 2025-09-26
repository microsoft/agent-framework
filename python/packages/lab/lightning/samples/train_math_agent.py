# Copyright (c) Microsoft. All rights reserved.

"""This sample will train a math agent using a dataset in `math_data/`.

One GPU with 16GB of memory is sufficient for this sample.
"""

import json
import math
import re
import string
from typing import TypedDict, cast

import sympy  # type: ignore[import-untyped,reportMissingImports]
from agent_framework._agents import ChatAgent
from agent_framework._mcp import MCPStdioTool
from agent_framework._types import AgentRunResponse
from agent_framework.openai._chat_client import OpenAIChatClient
from agentlightning import LLM, Dataset, Trainer, rollout
from agentlightning.algorithm.verl import VERL


class MathProblem(TypedDict):
    id: str
    question: str
    chain: str
    result: str
    source: str


def _load_jsonl(file_path: str) -> Dataset[MathProblem]:
    with open(file_path) as f:
        raw_data = [MathProblem(**json.loads(line)) for line in f]
    return cast(Dataset[MathProblem], raw_data)


# ==== Evaluation tools ====


def _normalize_option(option: str) -> str:
    return re.sub(r"(\s+|\(|\))", "", option)


def _is_option_result(result: str) -> bool:
    return _normalize_option(result) in list(string.ascii_letters)


def _float_eval(input_str: str) -> float:
    if " = around " in input_str:
        input_str = input_str.split(" = around ")[0]
    expr = sympy.parse_expr(input_str, evaluate=True)
    return float(expr.evalf())


def _scalar_are_results_same(pred_result: str, true_result: str, rel_tol: float) -> bool:
    pred_result = str(pred_result) if pred_result is not None else ""
    true_result = str(true_result) if true_result is not None else ""

    if pred_result.strip() == true_result.strip():
        return True

    if _is_option_result(true_result):
        # The task is to select correct option
        true_result = _normalize_option(true_result)
        pred_result = _normalize_option(pred_result)
        return pred_result == true_result

    # The task is to calculate the result as a number
    try:
        pred_float = _float_eval(pred_result)
        true_float = _float_eval(true_result)
        return math.isclose(pred_float, true_float, rel_tol=rel_tol)
    except Exception:
        pass

    return False


def _is_result_correct(prediction: str, ground_truth: str) -> float:
    return float(_scalar_are_results_same(prediction, ground_truth, 1e-2))


def evaluate(result: AgentRunResponse, ground_truth: str) -> float:
    # Evaluation of the agent's responsee
    if len(result.messages) == 0:
        print("No response from agent. Assuming incorrect.")
        return 0.0
    final_message = result.messages[-1].text

    answer = re.search(r"###\s*ANSWER:\s*(.+?)(\s*###|$)", final_message)
    if answer is None:
        print("No answer can be extracted from agent's response. Assuming incorrect.")
        return 0.0
    answer = answer.group(1)

    reward = _is_result_correct(answer, ground_truth)
    print(f"Reward: {reward}")
    return reward


# ==== Agent Part ====


AGENT_INSTRUCTION = """
Solve the following math problem.

Output the answer when you are ready. The answer should be surrounded by three sharps (`###`), in the form of ### ANSWER: <answer> ###.
""".strip()  # noqa: E501


@rollout
async def math_agent(task: MathProblem, llm: LLM) -> float:
    async with (
        MCPStdioTool(name="calculator", command="uvx", args=["mcp-server-calculator"]) as mcp_server,
        ChatAgent(
            chat_client=OpenAIChatClient(
                ai_model_id=llm.model,
                api_key="dummy",
                base_url=llm.endpoint,
            ),
            name="MathAgent",
            instructions=AGENT_INSTRUCTION,
        ) as agent,
    ):
        print(f"Task: {task['question']}")
        result = await agent.run(task["question"], tools=mcp_server)
        print(f"Agent responses: {result}")

        # Evaluation of the agent's responsee
        return evaluate(result, task["result"])


def main():
    rl_training_config = {
        "agentlightning": {
            # The port to communicate between the rollout workers and the RL training process
            "port": 9999,
        },
        "algorithm": {
            # Advantage estimator type: "gae", "grpo", "reinforce_plus_plus", etc.
            "adv_estimator": "grpo"
        },
        "data": {
            # Uses this many tasks from the dataset to perform rollouts
            "train_batch_size": 32,
            # Used to filter out the over-long prompt-response pairs
            "max_prompt_length": 4096,
            "max_response_length": 2048,
        },
        "actor_rollout_ref": {
            # Controls the rollout process
            "rollout": {
                # Set to 1 unless you want to use TP in multiple GPUs
                "tensor_model_parallel_size": 1,
                # Repeat each task N many times. Required by G(rouped)RPO
                "n": 4,
                # Controls the batch size per GPU when computing the log-prob
                "log_prob_micro_batch_size_per_gpu": 4,
                # Controls the multi-turn format (this is binded to the LLM used)
                # See https://docs.vllm.ai/en/stable/features/tool_calling.html
                "multi_turn": {"format": "hermes"},
                # Only vllm is supported for now
                "name": "vllm",
                # Controls the GPU memory utilization of vLLM
                # You might want to set this to under 0.8 to prevent OOM
                "gpu_memory_utilization": 0.6,
            },
            "actor": {
                # Split each sample into sub-batches of this size for PPO
                "ppo_mini_batch_size": 32,
                # Local per-GPU micro batch size
                "ppo_micro_batch_size_per_gpu": 4,
                # Optimizer configuration
                "optim": {"lr": 1e-6},
                # Whether to use KL loss during training
                "use_kl_loss": False,
                # PPO clipping ratios for policy updates
                "clip_ratio_low": 0.2,
                "clip_ratio_high": 0.3,
                # FSDP (Fully Sharded Data Parallel) configuration for memory efficiency
                # Useful when you don't have enough GPU memory
                "fsdp_config": {
                    # Whether to offload parameters to CPU
                    "param_offload": True,
                    # Whether to offload optimizer state to CPU
                    "optimizer_offload": True,
                },
            },
            # Reference model config
            "ref": {
                # Controls the batch size per GPU when computing log-prob for reference model
                "log_prob_micro_batch_size_per_gpu": 8,
                "fsdp_config": {"param_offload": True},
            },
            # Common configs for the model
            "model": {
                # Huggingface model path. This can be either local path or HDFS path.
                "path": "Qwen/Qwen2.5-0.5B-Instruct",
                # Whether to remove padding tokens in inputs during training
                "use_remove_padding": True,
                # Enable gradient checkpointing for memory efficiency
                "enable_gradient_checkpointing": True,
            },
        },
        # Config for the trainer
        "trainer": {
            # Number of GPUs per node
            "n_gpus_per_node": 1,
            # Whether to run validation before training begins
            "val_before_train": True,
            # Logging backends to use: "console", "wandb", etc.
            "logger": ["console"],
            # Project name for experiment tracking (e.g., on wandb)
            "project_name": "agent-framework-lab-lightning",
            # Experiment name for run identification in tracking tools
            "experiment_name": "math_agent",
            # Number of nodes used in the training
            "nnodes": 1,
            # Save frequency (by iteration) for model checkpoints
            "save_freq": 32,
            # Validation frequency (in training iterations)
            "test_freq": 4,
            # Number of epochs in training
            "total_epochs": 1,
        },
    }

    train_dataset = _load_jsonl("math_data/train.jsonl")
    val_dataset = _load_jsonl("math_data/test.jsonl")

    print("First 5 rows of train dataset:")
    for i in range(5):
        print(train_dataset[i])
    print("First 5 rows of val dataset:")
    for i in range(5):
        print(val_dataset[i])

    trainer = Trainer(algorithm=VERL(rl_training_config), n_workers=2)
    trainer.fit(math_agent, train_dataset, val_data=val_dataset)


if __name__ == "__main__":
    main()
