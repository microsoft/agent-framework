# Agent Framework Lab - τ²-bench

τ²-bench implements a simulation framework for evaluating customer service agents across various domains.

The framework orchestrates conversations between two AI agents:
- **Customer Service Agent**: Follows domain-specific policies and has access to tools (e.g., booking systems, databases)
- **User Simulator**: Simulates realistic customer behavior with specific goals and scenarios

Each evaluation runs a multi-turn conversation where the user simulator presents a customer service scenario, and the agent must resolve it following the domain policy while using available tools appropriately. The results are evaluated using τ²'s comprehensive evaluation system.

## Supported Domains

| Domain | Status | Description |
|--------|--------|-------------|
| **airline** | ✅ Supported | Customer service for airline booking, changes, and support |
| **retail** | 🚧 In Development | E-commerce customer support scenarios |
| **telecom** | 🚧 In Development | Telecommunications service support |

*Note: Currently only the airline domain is fully supported.*

## Installation

```bash
pip install agent-framework-lab-tau2
```

Download data from [Tau2-Bench](https://github.com/sierra-research/tau2-bench):

```bash
git clone https://github.com/sierra-research/tau2-bench.git
mv tau2-bench/data/ .
rm -rf tau2-bench
```

Export the data directory to `TAU2_DATA_DIR` environment variable:

```bash
export TAU2_DATA_DIR="data"
```

## Quick Start

### Running a Single Task

```python
import asyncio
from agent_framework.openai import OpenAIChatClient
from agent_framework_lab_tau2 import TaskRunner
from tau2.domains.airline.environment import get_tasks

async def run_single_task():
    # Initialize the task runner
    runner = TaskRunner(max_steps=50)

    # Set up your LLM clients
    assistant_client = OpenAIChatClient(
        base_url="https://api.openai.com/v1",
        api_key="your-api-key",
        ai_model_id="gpt-4o"
    )
    user_client = OpenAIChatClient(
        base_url="https://api.openai.com/v1",
        api_key="your-api-key",
        ai_model_id="gpt-4o-mini"
    )

    # Get a task and run it
    tasks = get_tasks()
    task = tasks[0]  # Run the first task

    conversation = await runner.run(task, assistant_client, user_client)
    reward = runner.evaluate(task, conversation, runner.termination_reason)

    print(f"Task completed with reward: {reward}")

# Run the example
asyncio.run(run_single_task())
```

### Running the Full Benchmark

Use the provided script to run the complete benchmark:

```bash
# Run with default models (gpt-4.1 for both agent and user)
python samples/run_benchmark.py

# Use custom models
python samples/run_benchmark.py --assistant gpt-4o --user gpt-4o-mini

# Debug a specific task
python samples/run_benchmark.py --debug-task-id task_001 --assistant gpt-4o

# Limit conversation length
python samples/run_benchmark.py --max-steps 20
```

## Results (on Airline Domain)

The following results are reproduced from our implementation of τ²-bench with `samples/run_benchmark.py`. It shows the average success rate over the dataset of 50 tasks.

| Agent Model | User Model | Success Rate |
|-------------|------------|----------|
| gpt-5 | gpt-4.1 | 62.0% |
| gpt-5-mini | gpt-4.1 | 52.0% |
| gpt-4.1 | gpt-4.1 | 60.0% |
| gpt-4.1-mini | gpt-4.1 | 50.0% |
| gpt-4.1 | gpt-4o-mini | 42.0% |
| gpt-4o | gpt-4.1 | 42.0% |
| gpt-4o-mini | gpt-4.1 | 26.0% |

## Advanced Usage

### Environment Configuration

Set required environment variables:

```bash
export OPENAI_BASE_URL="https://api.openai.com/v1"
export OPENAI_API_KEY="your-api-key"

# Optional: for custom endpoints
export OPENAI_BASE_URL="https://your-custom-endpoint.com/v1"
```

### Custom Agent Implementation

```python
from agent_framework_lab_tau2 import TaskRunner
from agent_framework import ChatAgent

class CustomTaskRunner(TaskRunner):
    def assistant_agent(self, assistant_chat_client):
        # Override to customize the assistant agent
        return ChatAgent(
            chat_client=assistant_chat_client,
            instructions="Your custom system prompt here",
            # Add custom tools, temperature, etc.
        )

    def user_simulator(self, user_chat_client, task):
        # Override to customize the user simulator
        return ChatAgent(
            chat_client=user_chat_client,
            instructions="Custom user simulator prompt",
        )
```

### Custom Workflow Integration

```python
from agent_framework._workflow import WorkflowBuilder, AgentExecutor
from agent_framework_lab_tau2 import TaskRunner

class WorkflowTaskRunner(TaskRunner):
    def build_conversation_workflow(self, assistant_agent, user_simulator_agent):
        # Build a custom workflow
        builder = WorkflowBuilder()

        # Create agent executors
        assistant_executor = AgentExecutor(assistant_agent, id="assistant_agent")
        user_executor = AgentExecutor(user_simulator_agent, id="user_simulator")

        # Add workflow edges and conditions
        builder.set_start_executor(assistant_executor)
        builder.add_edge(assistant_executor, user_executor)
        builder.add_edge(user_executor, assistant_executor, condition=self.should_not_stop)

        return builder.build()
```

### Utility Functions

```python
from agent_framework_lab_tau2 import patch_env_set_state, unpatch_env_set_state

# Enable compatibility patches for τ²-bench integration
patch_env_set_state()

# Disable patches when done
unpatch_env_set_state()
```

## Contributing

This package is part of the Microsoft Agent Framework Lab. Please see the main repository for contribution guidelines.

## License

This project is licensed under the MIT License - see the LICENSE file for details.