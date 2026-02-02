# Copyright (c) Microsoft. All rights reserved.

"""
Script to run multi-agent travel planning workflow and evaluate agent responses.

This script:
1. Executes the multi-agent workflow
2. Displays response data summary
3. Creates and runs evaluation with multiple evaluators
4. Monitors evaluation progress and displays results
"""

import asyncio
import os
import time

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from create_workflow import create_and_run_workflow


def print_section(title: str):
    """Print a formatted section header."""
    print(f"\n{'='*80}")
    print(f"{title}")
    print(f"{'='*80}")


async def run_workflow():
    """Execute the multi-agent travel planning workflow.
    
    Returns:
        Dictionary containing workflow data with agent response IDs
    """
    print_section("Step 1: Running Workflow")
    print("Executing multi-agent travel planning workflow...")
    print("This may take a few minutes...")
    
    workflow_data = await create_and_run_workflow()
    
    print("Workflow execution completed")
    return workflow_data


def display_response_summary(workflow_data: dict):
    """Display summary of response data."""
    print_section("Step 2: Response Data Summary")
    
    print(f"Query: {workflow_data['query']}")
    print(f"\nAgents tracked: {len(workflow_data['agents'])}")
    
    for agent_name, agent_data in workflow_data['agents'].items():
        response_count = agent_data['response_count']
        print(f"  {agent_name}: {response_count} response(s)")


def fetch_agent_responses(openai_client, workflow_data: dict, agent_names: list):
    """Fetch and display final responses from specified agents."""
    print_section("Step 3: Fetching Agent Responses")
    
    for agent_name in agent_names:
        if agent_name not in workflow_data['agents']:
            continue
            
        agent_data = workflow_data['agents'][agent_name]
        if not agent_data['response_ids']:
            continue
        
        final_response_id = agent_data['response_ids'][-1]
        print(f"\n{agent_name}")
        print(f"  Response ID: {final_response_id}")
        
        try:
            response = openai_client.responses.retrieve(response_id=final_response_id)
            content = response.output[-1].content[-1].text
            truncated = content[:300] + "..." if len(content) > 300 else content
            print(f"  Content preview: {truncated}")
        except Exception as e:
            print(f"  Error: {e}")


def create_evaluation(openai_client, model_deployment: str):
    """Create evaluation with multiple evaluators."""
    print_section("Step 4: Creating Evaluation")
    
    data_source_config = {"type": "azure_ai_source", "scenario": "responses"}
    
    testing_criteria = [
        {
            "type": "azure_ai_evaluator",
            "name": "relevance",
            "evaluator_name": "builtin.relevance",
            "initialization_parameters": {"deployment_name": model_deployment}
        },
        {
            "type": "azure_ai_evaluator",
            "name": "groundedness",
            "evaluator_name": "builtin.groundedness",
            "initialization_parameters": {"deployment_name": model_deployment}
        },
        {
            "type": "azure_ai_evaluator",
            "name": "tool_call_accuracy",
            "evaluator_name": "builtin.tool_call_accuracy",
            "initialization_parameters": {"deployment_name": model_deployment}
        },
        {
            "type": "azure_ai_evaluator",
            "name": "tool_output_utilization",
            "evaluator_name": "builtin.tool_output_utilization",
            "initialization_parameters": {"deployment_name": model_deployment}
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


def run_evaluation(openai_client, eval_object, workflow_data: dict, agent_names: list):
    """Run evaluation on selected agent responses."""
    print_section("Step 5: Running Evaluation")
    
    selected_response_ids = []
    for agent_name in agent_names:
        if agent_name in workflow_data['agents']:
            agent_data = workflow_data['agents'][agent_name]
            if agent_data['response_ids']:
                selected_response_ids.append(agent_data['response_ids'][-1])
    
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


def monitor_evaluation(openai_client, eval_object, eval_run):
    """Monitor evaluation progress and display results."""
    print_section("Step 6: Monitoring Evaluation")
    
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
    
    print("Travel Planning Workflow Evaluation")
    
    workflow_data = await run_workflow()
    
    display_response_summary(workflow_data)
    
    project_client = AIProjectClient(
        endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        credential=DefaultAzureCredential(),
        api_version="2025-11-15-preview"
    )
    openai_client = project_client.get_openai_client()
    
    agents_to_evaluate = ["hotel-search-agent", "flight-search-agent", "activity-search-agent"]
    
    fetch_agent_responses(openai_client, workflow_data, agents_to_evaluate)
    
    model_deployment = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o-mini")
    eval_object = create_evaluation(openai_client, model_deployment)
    
    eval_run = run_evaluation(openai_client, eval_object, workflow_data, agents_to_evaluate)
    
    monitor_evaluation(openai_client, eval_object, eval_run)
    
    print_section("Complete")


if __name__ == "__main__":
    asyncio.run(main())
