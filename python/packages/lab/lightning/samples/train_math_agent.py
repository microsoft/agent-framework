# Copyright (c) Microsoft. All rights reserved.

"""This sample demonstrates the basic usage pattern of agent-framework-lab-lightning.

It trains a math agent using a dataset in `data/math/` to solve mathematical problems
using an MCP calculator tool.

One GPU with 40GB of memory is sufficient for this sample.
"""

import argparse
import asyncio
import json
import math
import os
import re
import string
from typing import TypedDict, cast

import sympy  # type: ignore[import-untyped,reportMissingImports]
from agent_framework import AgentResponse, ChatAgent, MCPStdioTool
from agent_framework.lab.lightning import AgentFrameworkTracer
from agent_framework.openai import OpenAIChatClient
from agentlightning import LLM, Dataset, Trainer, rollout
from agentlightning.algorithm.verl import VERL


class MathProblem(TypedDict):
    """This TypedDict defines the structure of each training sample.

    Your task structure should contain all the information needed for:

    - The agent to process the task (e.g., 'question')
    - Evaluation (e.g., 'result' for ground truth)

    This type is optional. Not necessary to make the example work.
    """

    # The fields come from the dataset
    id: str
    question: str  # The math problem for the agent to solve
    chain: str  # Step-by-step solution (not used in training)
    result: str  # Ground truth answer for evaluation
    source: str


def _load_jsonl(file_path: str) -> Dataset[MathProblem]:
    """Load your dataset as a list of task samples.

    Each sample should match your task structure (MathProblem in this case).
    """
    with open(file_path) as f:
        raw_data = [MathProblem(**json.loads(line)) for line in f]
    return cast(Dataset[MathProblem], raw_data)


# Evaluation logic
# These functions evaluate whether the agent's answer matches the ground truth.
# Robust evaluation is crucial for RL training - the reward signal guides learning.


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
    except Exception:  # noqa: S110
        pass

    return False


def _is_result_correct(prediction: str, ground_truth: str) -> float:
    return float(_scalar_are_results_same(prediction, ground_truth, 1e-2))


def evaluate(result: AgentResponse, ground_truth: str) -> float:
    """Main evaluation function that extracts the agent's answer and compares with ground truth.

    This function:
    1. Extracts the final answer from the agent's response (after ###)
    2. Compares it with the ground truth using mathematical equivalence
    3. Returns a reward score (0.0 or 1.0) for RL training

    The reward signal is critical - it directly influences what the model learns.
    """
    # Check if agent provided any response
    if len(result.messages) == 0:
        print("No response from agent. Assuming incorrect.")
        return 0.0
    final_message = result.messages[-1].text

    # Extract answer after ### marker (as specified in agent instructions)
    answer = re.search(r"###\s*(.+?)(\s*###|$)", final_message)
    if answer is None:
        print("No answer can be extracted from agent's response. Assuming incorrect.")
        return 0.0
    answer = answer.group(1)

    # Compare extracted answer with ground truth
    reward = _is_result_correct(answer, ground_truth)
    print(f"Reward: {reward}")
    return reward


# Agent Logic

# Clear instructions are important for consistent agent behavior
# The ### format helps with reliable answer extraction during evaluation
AGENT_INSTRUCTION = """
Solve the following math problem. Use the calculator tool to help you calculate math expressions.

Output the answer when you are ready. The answer should be after three sharps (`###`), with no extra punctuations or texts. For example: ### 123
""".strip()  # noqa: E501


# The @rollout decorator is the key integration point with agent-lightning.
# It tells the training system that this function defines a trainable agent.
@rollout
async def math_agent(task: MathProblem, llm: LLM) -> float:
    """This is your trainable agent function.

    Key points:

    1. Must be decorated with @rollout
    2. Takes a task sample and LLM object as parameters
    3. Returns a float reward score (0.0 to 1.0 typically)
    4. The LLM object contains the model being trained and its configuration

    During training:
    - llm.model: The model checkpoint being trained
    - llm.endpoint: vLLM server endpoint for inference
    - llm.sampling_parameters: Temperature, etc.
    """
    # Create the Agent Framework components
    # MCPStdioTool provides calculator functionality via MCP protocol
    async with (
        MCPStdioTool(name="calculator", command="uvx", args=["mcp-server-calculator"]) as mcp_server,
        ChatAgent(
            chat_client=OpenAIChatClient(
                model_id=llm.model,  # This is the model being trained
                api_key=os.getenv("OPENAI_API_KEY") or "dummy",  # Can be dummy when connecting to training LLM
                base_url=llm.endpoint,  # vLLM server endpoint provided by agent-lightning
            ),
            name="MathAgent",
            instructions=AGENT_INSTRUCTION,
            temperature=llm.sampling_parameters.get("temperature", 0.0),
        ) as agent,
    ):
        print(f"Task: {task['question'][:10]}...")
        # Run the agent on the task
        result = await agent.run(task["question"], tools=mcp_server)
        print(f"Agent responses: {result}")

        # Evaluate and return reward - this is what drives RL training
        return evaluate(result, task["result"])


def main():
    """Main entrypoint."""
    # Configure RL training
    # This configuration controls all aspects of the RL training process.
    # Key sections: algorithm, data, rollout, actor, trainer
    rl_training_config = {
        "algorithm": {
            # Advantage estimator type: "gae", "grpo", "reinforce_plus_plus", etc.
            "adv_estimator": "grpo"
        },
        "data": {
            # Uses this many tasks from the dataset to perform rollouts
            "train_batch_size": 8,
            # Used to filter out the over-long prompt-response pairs
            "max_prompt_length": 4096,
            "max_response_length": 1024,
        },
        "actor_rollout_ref": {
            # Controls the rollout process
            "rollout": {
                # Set to 1 unless you want to use TP in multiple GPUs
                "tensor_model_parallel_size": 1,
                # Repeat each task N many times. Required by G(rouped)RPO
                "n": 4,
                # Controls the batch size per GPU when computing the log-prob
                "log_prob_micro_batch_size_per_gpu": 2,
                # Controls the multi-turn format (this is binded to the LLM used)
                # See https://docs.vllm.ai/en/stable/features/tool_calling.html
                "multi_turn": {"format": "hermes"},
                # Only vllm is supported for now
                "name": "vllm",
                # Controls the GPU memory utilization of vLLM
                # You might want to set this to under 0.8 to prevent OOM
                "gpu_memory_utilization": 0.7,
            },
            "actor": {
                # Split each sample into sub-batches of this size for PPO
                "ppo_mini_batch_size": 8,
                # Local per-GPU micro batch size
                "ppo_micro_batch_size_per_gpu": 2,
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
                "log_prob_micro_batch_size_per_gpu": 2,
                "fsdp_config": {"param_offload": True},
            },
            # Common configs for the model
            "model": {
                # Huggingface model path.
                # If you want to train a different model, change the path here.
                "path": "Qwen/Qwen2.5-1.5B-Instruct",
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
            # Number of nodes used in the training
            "nnodes": 1,
            # Validation frequency (in training iterations)
            "test_freq": 4,
            # Number of epochs in training
            "total_epochs": 2,
        },
    }

    # Load your datasets
    train_dataset = _load_jsonl("data/math/train.jsonl")
    val_dataset = _load_jsonl("data/math/test.jsonl")

    # Preview the data to ensure it's loaded correctly
    print("First 5 rows of train dataset:")
    for i in range(5):
        print(train_dataset[i])
    print("First 5 rows of val dataset:")
    for i in range(5):
        print(val_dataset[i])

    # Create trainer with VERL algorithm and start training
    # n_workers: Number of rollout workers (processes) for parallel data collection
    trainer = Trainer(algorithm=VERL(rl_training_config), tracer=AgentFrameworkTracer(), n_workers=2)

    # This starts the actual RL training loop:
    # 1. Collect rollouts using current model
    # 2. Compute advantages and train the model
    # 3. Repeat for specified number of epochs
    trainer.fit(math_agent, train_dataset, val_dataset=val_dataset)


def debug():
    """Debug mode allows you to test your agent function before training.

    Always run debug mode first before starting expensive RL training!
    """
    train_dataset = _load_jsonl("data/math/train.jsonl")
    train_sample = train_dataset[0]

    # Use a known good model for debugging (not the one being trained)
    model = "gpt-4o-mini"
    base_url = os.getenv("OPENAI_BASE_URL")
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key is None:
        raise ValueError("OPENAI_API_KEY must be set")
    if base_url is None:
        raise ValueError("OPENAI_BASE_URL must be set")

    # Test your agent function with a sample task
    asyncio.run(math_agent(train_sample, LLM(model=model, endpoint=base_url)))  # type: ignore


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    if args.debug:
        debug()
    else:
        main()
