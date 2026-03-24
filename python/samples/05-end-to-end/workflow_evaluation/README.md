# Multi-Agent Travel Planning Workflow Evaluation

This sample demonstrates evaluating a multi-agent workflow using Azure AI's built-in evaluators. The workflow processes travel planning requests through seven specialized agents in a fan-out/fan-in pattern: travel request handler, hotel/flight/activity search agents, booking aggregator, booking confirmation, and payment processing.

## Evaluation Metrics

The evaluation uses four Azure AI built-in evaluators:

- **Relevance** - How well responses address the user query
- **Groundedness** - Whether responses are grounded in available context
- **Tool Call Accuracy** - Correct tool selection and parameter usage
- **Tool Output Utilization** - Effective use of tool outputs in responses

## Setup

Create a `.env` file with configuration as in the `.env.example` file in this folder.

## Running the Evaluation

Execute the complete workflow and evaluation:

```bash
python run_evaluation.py
```

The script will:
1. Execute the multi-agent travel planning workflow
2. Display response summary for each agent
3. Create and run evaluation on hotel, flight, and activity search agents
4. Monitor progress and display the evaluation report URL
