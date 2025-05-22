## Evaluation

The framework provides a comprehensive evaluation system for assessing agent performance, enabling developers to measure both the quality of agent responses and the efficiency of their decision-making processes.

### Core Evaluation Concepts

- **Standardized Trajectory Format**: A unified representation of agent interactions (messages, tool calls, events) enabling consistent evaluation across different agent implementations.
- **Trajectory Evaluation**: Analyze both the path an agent takes and the final response it generates. This includes evaluating the sequence of tool calls, the order of operations, and the final output.

### Evaluation Components

The framework provides these key evaluation components:

- **Trajectory Converter**: Transforms agent runs from various frameworks into a standardized format for evaluation.
- **Metrics Library**:
  - Computation-based metrics: Direct algorithms that calculate objective measures without requiring a model
  - Model-based metrics: Evaluation criteria that require a model to assess subjective qualities
- **Judge**: For model-based metrics, a judge is the LLM responsible for applying evaluation criteria. Different judge models can be selected based on evaluation needs.
- **Evaluator**: Coordinates the evaluation process by running computation-based metrics directly and applying judges to model-based metrics.
- **Integration**: Connect with cloud evaluation services including Azure AI Evaluation.

### (Example) Metrics

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

### Example Metrics

The framework provides both computation-based metrics that run directly and model-based metrics that require a judge:

```python
# Example of computation-based metric (runs direct calculations, no judge needed)
trajectory_match = ExactTrajectoryMatch()

# Example of model-based metric (requires a judge model to evaluate)
task_adherence_metric = PointwiseMetric(
    metric="task_adherence",
    metric_prompt_template=PointwiseMetricPromptTemplate(
        criteria={
            "Task adherence": (
                "Evaluate whether the agent's response appropriately addresses the assigned task. "
                "Consider these sub-points:\n"
                "  - Does the response directly address the user's request?\n"
                "  - Does the response incorporate information gathered from tool calls?\n"
                "  - Is the response complete without missing important aspects of the task?\n"
            )
        },
        rating_rubric={
            "5": "Excellent - Completely addresses all aspects of the task with thorough detail",
            "4": "Good - Addresses most aspects of the task effectively",
            "3": "Adequate - Addresses the core of the task but may miss minor details",
            "2": "Poor - Only partially addresses the task with significant gaps",
            "1": "Inadequate - Fails to address the task or contains major inaccuracies",
        },
    ),
)

# Evaluator combines both types of metrics
evaluator = Evaluator(
    computation_metrics=[trajectory_match],  # Run directly
    model_metrics=[task_adherence_metric],   # Require a judge
    judge=JudgeModel(model="o3-mini", temperature=0)  # Judge for model-based metrics
)
```

### Sample Developer Experience

1. **Prepare Dataset**: Create a dataset with tasks, expected responses, and optional reference trajectories.
2. **Configure Metrics**: Select from pre-built metrics or define custom metrics based on evaluation needs.
3. **Select Judges**: Choose appropriate judge models for model-based metrics, optimizing for evaluation quality.
4. **Run Evaluation**: Execute the evaluation against agent runs or existing trajectory data.
5. **Analyze Results**: Review metrics, identify areas for improvement, and compare different agent configurations.
