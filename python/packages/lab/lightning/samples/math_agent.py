import math
import re
import string
from typing import TypedDict

import sympy  # type: ignore
from agent_framework._agents import ChatAgent
from agent_framework._mcp import MCPStdioTool
from agent_framework.openai._chat_client import OpenAIChatClient
from agentlightning import LLM, Trainer, rollout  # type: ignore
from agentlightning.algorithm.verl import VERL  # type: ignore


class MathProblem(TypedDict):
    id: str
    question: str
    chain: str
    result: str
    source: str


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
        if len(result.messages) == 0:
            print("No response from agent. Assuming incorrect.")
            return 0.0
        final_message = result.messages[-1].text

        answer = re.search(r"###\s*ANSWER:\s*(.+?)(\s*###|$)", final_message)
        if answer is None:
            print("No answer can be extracted from agent's response. Assuming incorrect.")
            return 0.0
        answer = answer.group(1)

        reward = _is_result_correct(answer, task["result"])
        print(f"Reward: {reward}")
        return reward


def main():
    rl_training_config = {
        "agentlightning": {
            "port": 9999,
        },
        "algorithm": {
            "adv_estimator": "grpo",
            "use_kl_in_reward": False,
        },
        "data": {
            "train_batch_size": 32,
            "max_prompt_length": 4096,
            "max_response_length": 2048,
            "truncation": "error",
        },
        "actor_rollout_ref": {
            "rollout": {
                "tensor_model_parallel_size": 1,
                "n": 4,
                "log_prob_micro_batch_size_per_gpu": 4,
                "multi_turn": {"format": "hermes"},
                "name": "vllm",
                "gpu_memory_utilization": 0.6,
            },
            "actor": {
                "ppo_mini_batch_size": 32,
                "ppo_micro_batch_size_per_gpu": 4,
                "optim": {"lr": 1e-6},
                "use_kl_loss": False,
                "kl_loss_coef": 0.0,
                "entropy_coeff": 0,
                "clip_ratio_low": 0.2,
                "clip_ratio_high": 0.3,
                "fsdp_config": {
                    "param_offload": True,
                    "optimizer_offload": True,
                },
            },
            "ref": {
                "log_prob_micro_batch_size_per_gpu": 8,
                "fsdp_config": {"param_offload": True},
            },
            "model": {
                "path": "Qwen/Qwen2.5-0.5B-Instruct",
                "use_remove_padding": True,
                "enable_gradient_checkpointing": True,
            },
        },
        "trainer": {
            "n_gpus_per_node": 1,
            "val_before_train": True,
            "critic_warmup": 0,
            "logger": ["console"],
            "project_name": "AgentLightningDebug",
            "experiment_name": "train_verl",
            "nnodes": 1,
            "save_freq": 256,
            "test_freq": 6,
            "total_epochs": 1,
            "total_training_steps": 6,
        },
    }

    from datasets import Dataset  # type: ignore

    train_dataset = Dataset.from_parquet("data/train.parquet").to_list()
    val_dataset = Dataset.from_parquet("data/test_mini.parquet").to_list()

    print("First 5 rows of train dataset:")
    print(train_dataset[:5])
    print("First 5 rows of val dataset:")
    print(val_dataset[:5])

    trainer = Trainer(algorithm=VERL(rl_training_config), n_workers=2)
    trainer.fit(math_agent, train_dataset, val_data=val_dataset)


if __name__ == "__main__":
    main()
