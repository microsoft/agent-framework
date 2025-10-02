# Agent Framework Lab - Lightning

**Agent Framework Lab Lightning** is a specialized package that integrates [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) with [Agent-lightning](https://github.com/microsoft/agent-lightning) to provide reinforcement learning (RL) training capabilities for AI agents.

This package enables you to train and fine-tune agents using advanced RL algorithms from VERL (e.g., GRPO, PPO, Reinforce++) with support for distributed training, multi-GPU setups, and comprehensive monitoring. It also supports complex multi-turn agent interactions during training and optimization techniques like prompt optimization. See the [Agent-lightning documentation](https://microsoft.github.io/agent-lightning/stable/) for details.

> **Note**: This module is part of the consolidated `agent-framework-lab` package. Install the package with the `lightning` extra to use this module.

## Installation

Install from source with Lightning dependencies:

```bash
git clone https://github.com/microsoft/agent-framework.git
cd agent-framework/python/packages/lab
pip install -e ".[lightning]"
```

### Optional Dependencies

```bash
# For math-related training
pip install -e ".[lightning,math]"

# For tau2 benchmarking
pip install -e ".[lightning,tau2]"
```

To prepare for RL training, you'll also need to install dependencies like PyTorch, Ray, and vLLM. See the [Agent-lightning setup instructions](https://github.com/microsoft/agent-lightning) for more details.

## Usage Patterns

The basic usage pattern follows these steps:

1. **Prepare your dataset** as a list of samples (typically dictionaries)
2. **Create an agent function** that processes samples and returns evaluation scores
3. **Decorate with `@agentlightning.rollout`** to enable training
4. **Configure and run training** with the `agentlightning.Trainer` class

### Example Implementation

```python
from agent_framework.lab.lightning import init
from agentlightning import rollout, Trainer, LLM, Dataset
from agentlightning.algorithm.verl import VERL

TaskType = Any

@rollout
async def math_agent(task: TaskType, llm: LLM) -> float:
    """A function that solves a math problem and returns the evaluation score."""
    async with (
        MCPStdioTool(name="calculator", command="uvx", args=["mcp-server-calculator"]) as mcp_server,
        ChatAgent(
            chat_client=OpenAIChatClient(
                model_id=llm.model,
                api_key="your-api-key",
                base_url=llm.endpoint,
            ),
            name="MathAgent",
            instructions="Solve the math problem and output answer after ###",
            temperature=llm.sampling_parameters.get("temperature", 0.0),
        ) as agent,
    ):
        result = await agent.run(task["question"], tools=mcp_server)
        # Your evaluation logic here...
        return evaluation_score

# Training configuration
config = {
    "data": {"train_batch_size": 8},
    "trainer": {"total_epochs": 2, "n_gpus_per_node": 1},
    # ... additional config
}

# Initialize agent-framework to send telemetry data to agent-lightning's observability backend
init()

trainer = Trainer(algorithm=VERL(config), n_workers=2)
# Both train_dataset and val_dataset are lists of TaskType
trainer.fit(math_agent, train_dataset, val_data=val_dataset)
```

## Example 1: Training a Math Agent

This example trains an agent that uses an MCP calculator tool to solve math problems. The dataset is a small subset from the [Calc-X](https://huggingface.co/datasets/MU-NLPC/Calc-X) dataset. The Agent-lightning team has also experimented with a similar agent using a larger dataset. See [this example](https://github.com/microsoft/agent-lightning/tree/a63197355cc23b5b235c49fe7c20b54f9d4ebcd2/examples/calc_x) for more details.

Running this example requires a minimum of 40GB GPU memory. If you don't have enough GPU memory, you can use a smaller model like `Qwen2.5-0.5B-Instruct`, though the results won't be as good. To run the example:

```bash
cd samples
# Run the ray cluster (see the troubleshooting section for more details)
ray start --head --dashboard-host=0.0.0.0
# Run the training script
python train_math_agent.py
```

To debug the agent used in the example, you can run the script with the `--debug` flag:

```bash
python train_math_agent.py --debug
```

The training curve below shows results with Qwen2.5-1.5B-Instruct and GRPO. Validation accuracy increases from 10% to 35% in the first 8 steps, then begins to overfit.

![Training Curve](./assets/train_math_agent.png)

## Example 2: Training a Tau2 Agent

This advanced example demonstrates training on complex multi-agent scenarios using the Tau2 benchmark. It features a multi-agent setup with an assistant agent and a user simulator agent, training the assistant while keeping the user simulator fixed. The example incorporates a multi-step workflow with tool usage and complex evaluation metrics. Currently, training uses the airline domain with a 50/50 split between training and validation data.

Before running this example, please read the [agent-lightning-lab-tau2](../tau2/README.md) documentation and follow the setup instructions.

To run the example:

```bash
# Set required environment variables
export TAU2_DATA_DIR="/path/to/tau2/data"

# Used for user simulator and LLM judge
export OPENAI_BASE_URL="your-endpoint"
export OPENAI_API_KEY="your-key"

# Used for tracking on Weights & Biases
export WANDB_API_KEY="your-key"

# Run the ray cluster
ray start --head --dashboard-host=0.0.0.0

# Train the tau2 agent
cd samples
python samples/train_tau2_agent.py

# Debug mode
python samples/train_tau2_agent.py --debug
```

This example uses more advanced Agent-lightning features compared to the math example. It's based on the `LitAgent` class rather than the `@rollout` decorator and involves concepts like resources and agent filtering. We recommend reading the [Agent-lightning documentation](https://microsoft.github.io/agent-lightning/stable/) to learn more.

Results with Qwen2.5-1.5B-Instruct and GRPO are shown below. Validation accuracy improves from 28% to 40% over 8 epochs.

![Training Curve](./assets/train_tau2_agent.png)

## Troubleshooting

### Ray Connection Issues

Agent-lightning uses VERL for RL training, which depends on Ray. To avoid issues, it's recommended to start Ray manually beforehand. If you encounter Ray startup problems:

```bash
# Stop existing Ray processes
ray stop

# Start Ray with debugging enabled
env RAY_DEBUG=legacy HYDRA_FULL_ERROR=1 VLLM_USE_V1=1 ray start --head --dashboard-host=0.0.0.0
```

**Important**: Run Ray commands in the same directory as your training script. Set any required environment variables (`WANDB_API_KEY`, `HF_TOKEN`) before starting Ray.

### GPU Memory Issues

1. **Reduce `gpu_memory_utilization`** to <0.8
2. **Enable FSDP offloading**:
   ```python
   "fsdp_config": {
       "param_offload": True,
       "optimizer_offload": True,
   }
   ```
3. **Decrease batch sizes**:
   - `train_batch_size`
   - `ppo_mini_batch_size`
   - `log_prob_micro_batch_size_per_gpu`

### Agent Debugging

Always test your agent before training:

```bash
# Use debug mode to validate agent behavior
python your_training_script.py --debug

# Check agent responses and evaluation logic
# Ensure proper tool integration and result extraction
```

## Contributing

This package is part of the Microsoft Agent Framework Lab. Please see the main repository for contribution guidelines.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
