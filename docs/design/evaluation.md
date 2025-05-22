## Evaluation

The goal of Evaluation is to enable developers measure both the quality of agent responses and the efficiency of their decision-making processes.

### Core Evaluation Concepts

To enable effective evaluation (mindful of the fact that agents may be implemented with different approaches or even frameworks), it is useful to focus on the following core concepts:

- **Standardized Trajectory Format**: A unified representation of agent interactions (messages, tool calls, events) enabling consistent evaluation across different agent implementations.
- **Trajectory and Outcome Evaluation**: Analyze both the path an agent takes and the final response it generates. This includes evaluating the sequence of tool calls, the order of operations, and the final output.

### Evaluation Components

The framework provides these key evaluation components:

- **Trajectory Converter**: Transforms agent runs from various frameworks into a standardized format for evaluation.
- **Metrics Library**:
  - Computation-based metrics: Direct algorithms that calculate objective measures without requiring a model
  - Model-based metrics: Evaluation criteria that require an AI model to assess subjective qualities
- **Judge**: For model-based metrics, a judge is the LLM responsible for applying evaluation criteria. Different judge models can be selected based on evaluation needs.
- **Evaluator**: Coordinates the evaluation process by running computation-based metrics directly and applying judges to model-based metrics.
- **Integration**: Connect with cloud evaluation services including Azure AI Evaluation.

### (Example) Metrics

Metrics may be pointwise (evaluating a single response on some criteria) or pairwise (evaluating two responses against each other e.g., where some ground truth is available).

#### Computation-based Metrics

- **Tool Match**: Measures tool call sequence matching in various ways:
  - Exact Match: Perfect match with reference sequence
  - In-Order Match: Required tools called in correct order (extra steps allowed)
  - Any-Order Match: All required tools called regardless of order
- **Precision**: Proportion of agent's tool calls that match reference tool calls.
- **Recall**: Proportion of reference tool calls included in the agent's tool calls.
- **Single Tool Usage**: Checks if a specific tool was used during the trajectory.
- **Tool Call Errors**: Measures rate of tool call failures or errors.
- **Latency**: Time required for agent to complete its task.

#### Model-based Metrics

- **Task Adherence**: Evaluates how well the agent's response addresses the assigned task.
- **Coherence**: Assesses logical flow and internal consistency of the response.
- **Safety**: Detects potential harmful content in responses.
- **Follows Trajectory**: Evaluates if the response logically follows from the tools used.
- **Efficiency**: Measures if the agent took an optimal path to reach the solution.

This can build on the suite of metrics provided by [Azure AI evaluation](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/develop/agent-evaluate-sdk).

### Sample Developer Experience

**Sample Developer Experience:**

1. **Run Agent**: Execute your agent on tasks to generate trajectories.
2. **Create Trajectory**: Structure task, run data, and optional reference.
3. **Configure Metrics**: Select pre-built or custom metrics for evaluation.
4. **Evaluate**: Run evaluator to get scores and detailed results.
5. **Analyze**: Review metrics to identify improvements.

```python
from azure.ai.evaluation import AzureOpenAIModelConfiguration
from agent_framework.evaluation import (
    TrajectoryMatchMetric,
    TaskAdherenceMetric,
    Evaluator,
    Trajectory
)

# Model configuration for judge
model_config = AzureOpenAIModelConfiguration(
    azure_deployment="o3-mini",
    api_version="2024-02-01",
    temperature=0
)

# Run your agent
task = "What's the weather in Seattle?"
run = your_agent.run(task)

# Create trajectory object
trajectory = Trajectory(
    task=task,
    run=run,
    reference=[  # Optional reference trajectory
        {"type": "tool_call", "tool": "weather_api", "args": {"location": "Seattle"}},
        {"type": "response", "content": "Weather information for Seattle"}
    ]
)

# Define metrics
trajectory_match = TrajectoryMatchMetric(match_type="exact")
task_adherence = TaskAdherenceMetric(
    criteria={
        "Task adherence": (
            "Does the response address the user's request and incorporate "
            "information from tool calls appropriately?"
        )
    },
    rating_rubric={
        "5": "Excellent - Fully addresses task with complete detail",
        "4": "Good - Addresses most aspects effectively",
        "3": "Adequate - Addresses core task, minor gaps",
        "2": "Poor - Partial addressing with significant gaps",
        "1": "Inadequate - Fails to address task properly"
    }
)

# Create evaluator
evaluator = Evaluator(
    metrics=[trajectory_match, task_adherence],
    model_config=model_config,
    trajectory=trajectory
)

# Run evaluation
result = evaluator.run()

# Results follow Azure format
print("Evaluation Results:")
for metric_name, score in result.items():
    if isinstance(score, dict):
        print(f"{metric_name}: {score.get('score', 'N/A')}")
        print(f"  Result: {score.get('result', 'N/A')}")
        print(f"  Reason: {score.get('reason', 'N/A')}")
    else:
        print(f"{metric_name}: {score}")


```
