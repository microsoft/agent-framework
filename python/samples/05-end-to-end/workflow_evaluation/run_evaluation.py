# Copyright (c) Microsoft. All rights reserved.
# type: ignore

from __future__ import annotations

import asyncio
import os
import time
from typing import TYPE_CHECKING, Any

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from create_workflow import create_and_run_workflow
from dotenv import load_dotenv

if TYPE_CHECKING:
    from openai import OpenAI
    from openai.types import EvalCreateResponse
    from openai.types.evals import RunCreateResponse

"""
Script to run multi-agent travel planning workflow and evaluate agent responses.

This script:
1. Runs the multi-agent travel planning workflow
2. Displays a summary of tracked agent responses
3. Fetches and previews final agent responses
4. Creates an evaluation with multiple evaluators
5. Runs the evaluation on selected agent responses
6. Monitors evaluation progress and displays results
"""


def create_openai_client() -> OpenAI:
    project_client = AIProjectClient(
        endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        credential=DefaultAzureCredential(),
    )
    return project_client.get_openai_client()


def print_section(title: str):
    """Print a formatted section header."""
    print(f"\n{'=' * 80}")
    print(f"{title}")
    print(f"{'=' * 80}")


async def run_workflow(deployment_name: str | None = None) -> dict[str, Any]:
    """Execute the multi-agent travel planning workflow.

    Args:
        deployment_name: Optional model deployment name for the workflow agents

    Returns:
        Dictionary containing workflow data with agent response IDs
    """
    print("Executing multi-agent travel planning workflow...")
    print("This may take a few minutes...")

    workflow_data = await create_and_run_workflow(deployment_name=deployment_name)

    print("Workflow execution completed")
    return workflow_data


def display_response_summary(workflow_data: dict) -> None:
    """Display summary of response data."""
    print(f"Query: {workflow_data['query']}")
    print(f"\nAgents tracked: {len(workflow_data['agents'])}")

    for agent_name, agent_data in workflow_data["agents"].items():
        response_count = agent_data["response_count"]
        print(f"  {agent_name}: {response_count} response(s)")


def fetch_agent_responses(openai_client: OpenAI, workflow_data: dict[str, Any], agent_names: list[str]) -> None:
    """Fetch and display final responses from specified agents."""
    for agent_name in agent_names:
        if agent_name not in workflow_data["agents"]:
            continue

        agent_data = workflow_data["agents"][agent_name]
        if not agent_data["response_ids"]:
            continue

        final_response_id = agent_data["response_ids"][-1]
        print(f"\n{agent_name}")
        print(f"  Response ID: {final_response_id}")

        try:
            response = openai_client.responses.retrieve(response_id=final_response_id)
            content = response.output[-1].content[-1].text
            truncated = content[:300] + "..." if len(content) > 300 else content
            print(f"  Content preview: {truncated}")
        except Exception as e:
            print(f"  Error: {e}")


def create_evaluation(openai_client: OpenAI, deployment_name: str | None = "gpt-5.2") -> EvalCreateResponse:
    """Create evaluation with multiple evaluators."""
    deployment_name = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", deployment_name)
    data_source_config = {"type": "azure_ai_source", "scenario": "responses"}

    testing_criteria = [
        {
            "type": "azure_ai_evaluator",
            "name": "relevance",
            "evaluator_name": "builtin.relevance",
            "initialization_parameters": {"deployment_name": deployment_name},
        },
        {
            "type": "azure_ai_evaluator",
            "name": "groundedness",
            "evaluator_name": "builtin.groundedness",
            "initialization_parameters": {"deployment_name": deployment_name},
        },
        {
            "type": "azure_ai_evaluator",
            "name": "tool_call_accuracy",
            "evaluator_name": "builtin.tool_call_accuracy",
            "initialization_parameters": {"deployment_name": deployment_name},
        },
        {
            "type": "azure_ai_evaluator",
            "name": "tool_output_utilization",
            "evaluator_name": "builtin.tool_output_utilization",
            "initialization_parameters": {"deployment_name": deployment_name},
        },
    ]

    eval_object = openai_client.evals.create(
        name="Travel Workflow Multi-Evaluator Assessment",
        data_source_config=data_source_config,
        testing_criteria=testing_criteria,
    )

    evaluator_names = [criterion["name"] for criterion in testing_criteria]
    print(f"Evaluation created: {eval_object.id}")
    print(f"Evaluators ({len(evaluator_names)}): {', '.join(evaluator_names)}")

    return eval_object


def run_evaluation(
    openai_client: OpenAI, eval_object: EvalCreateResponse, workflow_data: dict[str, Any], agent_names: list[str]
) -> RunCreateResponse:
    """Run evaluation on selected agent responses."""
    selected_response_ids = []
    for agent_name in agent_names:
        if agent_name in workflow_data["agents"]:
            agent_data = workflow_data["agents"][agent_name]
            if agent_data["response_ids"]:
                selected_response_ids.append(agent_data["response_ids"][-1])

    print(f"Selected {len(selected_response_ids)} responses for evaluation")

    data_source = {
        "type": "azure_ai_responses",
        "item_generation_params": {
            "type": "response_retrieval",
            "data_mapping": {"response_id": "{{item.resp_id}}"},
            "source": {
                "type": "file_content",
                "content": [{"item": {"resp_id": resp_id}} for resp_id in selected_response_ids]
            },
        },
    }

    eval_run = openai_client.evals.runs.create(
        eval_id=eval_object.id,
        name="Multi-Agent Response Evaluation",
        data_source=data_source
    )

    print(f"Evaluation run created: {eval_run.id}")

    return eval_run


def monitor_evaluation(openai_client: OpenAI, eval_object: EvalCreateResponse, eval_run: RunCreateResponse):
    """Monitor evaluation progress and display results."""
    print("Waiting for evaluation to complete...")

    while eval_run.status not in ["completed", "failed"]:
        eval_run = openai_client.evals.runs.retrieve(
            run_id=eval_run.id,
            eval_id=eval_object.id
        )
        print(f"Status: {eval_run.status}")
        time.sleep(5)

    if eval_run.status == "completed":
        print("\nEvaluation completed successfully")
        print(f"Result counts: {eval_run.result_counts}")
        print(f"\nReport URL: {eval_run.report_url}")
    else:
        print("\nEvaluation failed")


async def main():
    """Main execution flow."""
    load_dotenv()
    openai_client = create_openai_client()

    # Model configuration
    workflow_agent_model = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME_WORKFLOW", "gpt-4.1-nano")
    eval_model = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME_EVAL", "gpt-5.2")

    # Focus on these agents, uncomment other ones you want to have evals run on
    agents_to_evaluate = [
        "hotel-search-agent",
        "flight-search-agent",
        "activity-search-agent",
        # "booking-payment-agent",
        # "booking-info-aggregation-agent",
        # "travel-request-handler",
        # "booking-confirmation-agent",
    ]

    print_section("Travel Planning Workflow Evaluation")

    print_section("Step 1: Running Workflow")
    workflow_data = await run_workflow(deployment_name=workflow_agent_model)

    print_section("Step 2: Response Data Summary")
    display_response_summary(workflow_data)

    print_section("Step 3: Fetching Agent Responses")
    fetch_agent_responses(openai_client, workflow_data, agents_to_evaluate)

    print_section("Step 4: Creating Evaluation")
    eval_object = create_evaluation(openai_client, deployment_name=eval_model)

    print_section("Step 5: Running Evaluation")
    eval_run = run_evaluation(openai_client, eval_object, workflow_data, agents_to_evaluate)

    print_section("Step 6: Monitoring Evaluation")
    monitor_evaluation(openai_client, eval_object, eval_run)

    print_section("Complete")


if __name__ == "__main__":
    asyncio.run(main())
