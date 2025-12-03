# Copyright (c) Microsoft. All rights reserved.
# type: ignore
import asyncio
import os
import time
import argparse
import pandas as pd
import openai
from typing import Any
from dotenv import load_dotenv
from openai.types.eval_create_params import DataSourceConfigCustom
from openai.types.evals.create_eval_jsonl_run_data_source_param import (
    CreateEvalJSONLRunDataSourceParam,
    SourceFileContent,
    SourceFileContentContent,
)

from agent_framework import ChatAgent, ChatMessage
from agent_framework.azure import AzureOpenAIChatClient
from azure.ai.projects import AIProjectClient
from azure.identity import AzureCliCredential

"""
Self-Reflection LLM Runner

Reflexion: language agents with verbal reinforcement learning.
Noah Shinn, Federico Cassano, Ashwin Gopinath, Karthik Narasimhan, and Shunyu Yao. 2023.
In Proceedings of the 37th International Conference on Neural Information Processing Systems (NIPS '23). Curran Associates Inc., Red Hook, NY, USA, Article 377, 8634–8652.
https://arxiv.org/abs/2303.11366 

This module implements a self-reflection loop for LLM responses using groundedness evaluation.
It loads prompts from a JSONL file, runs them through an LLM with self-reflection,
and saves the results.


Usage as CLI:
    python self_reflection.py

Usage as CLI with extra options:
    python self_reflection.py --input resources/suboptimal_groundedness_prompts.jsonl \\
                              --output resources/results.jsonl \\
                              --max-reflections 3 \\
                              -n 10  # Optional: process only first 10 prompts
"""


DEFAULT_AGENT_MODEL = "gpt-4.1"
DEFAULT_JUDGE_MODEL = "gpt-4.1"


def create_openai_client():
    endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
    credential = AzureCliCredential()
    project_client = AIProjectClient(endpoint=endpoint, credential=credential)
    return project_client.get_openai_client()


def create_eval(client: openai.OpenAI, judge_model: str) -> openai.types.EvalCreateResponse:
    print("Creating Eval")
    data_source_config = DataSourceConfigCustom({
        "type": "custom",
        "item_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "response": {"type": "string"},
                "context": {"type": "string"},
            },
            "required": [],
        },
        "include_sample_schema": True,
    })

    testing_criteria = [{
        "type": "azure_ai_evaluator",
        "name": "groundedness",
        "evaluator_name": "builtin.groundedness",
        "data_mapping": {"query": "{{item.query}}", "response": "{{item.response}}", "context": "{{item.context}}"},
        "initialization_parameters": {"deployment_name": f"{judge_model}"},
    }]

    return client.evals.create(
        name="Eval",
        data_source_config=data_source_config,
        testing_criteria=testing_criteria,  # type: ignore
    )


def run_eval(
        client: openai.OpenAI,
        eval_object: openai.types.EvalCreateResponse,
        query: str,
        response: str,
        context: str,
):
    eval_run_object = client.evals.runs.create(
        eval_id=eval_object.id,
        name="inline_data_run",
        metadata={"team": "eval-exp", "scenario": "inline-data-v1"},
        data_source=CreateEvalJSONLRunDataSourceParam(
            type="jsonl",
            source=SourceFileContent(
                type="file_content",
                content=[
                    SourceFileContentContent(
                        item={
                            "query": query,
                            "context": context,
                            "response": response,
                        }
                    ),
                ],
            ),
        ),
    )

    eval_run_response = client.evals.runs.retrieve(run_id=eval_run_object.id, eval_id=eval_object.id)

    MAX_RETRY = 10
    for _ in range(0, MAX_RETRY):
        run = client.evals.runs.retrieve(run_id=eval_run_response.id, eval_id=eval_object.id)
        if run.status == "failed":
            print(f"Eval run failed. Run ID: {run.id}, Status: {run.status}, Error: {getattr(run, 'error', 'Unknown error')}")
            continue
        elif run.status == "completed":
            output_items = list(client.evals.runs.output_items.list(run_id=run.id, eval_id=eval_object.id))
            return output_items
        time.sleep(5)

    print("Eval result retrieval timeout.")
    return None


async def execute_query_with_self_reflection(
    *,
    client: openai.OpenAI,
    agent: ChatAgent,
    eval_object: openai.types.EvalCreateResponse,
    full_user_query: str,
    context: str,
    max_self_reflections: int = 3,
) -> dict[str, Any]:
    """
    Execute a query with self-reflection loop.
    
    Args:
        agent: ChatAgent instance to use for generating responses
        full_user_query: Complete prompt including system prompt, user request, and context
        context: Context document for groundedness evaluation
        evaluator: Groundedness evaluator function
        max_self_reflections: Maximum number of self-reflection iterations
        
    Returns:
        Dictionary containing:
            - best_response: The best response achieved
            - best_response_score: Best groundedness score
            - best_iteration: Iteration number where best score was achieved
            - iteration_scores: List of groundedness scores for each iteration
            - messages: Full conversation history
            - usage_metadata: Token usage information
            - num_retries: Number of iterations performed
            - total_groundedness_eval_time: Time spent on evaluations (seconds)
            - total_end_to_end_time: Total execution time (seconds)
    """
    messages = [ChatMessage(role="user", text=full_user_query)]

    best_score = 0
    max_score = 5
    best_response = None
    best_iteration = 0
    raw_response = None
    total_groundedness_eval_time = 0.0
    start_time = time.time()
    iteration_scores = []  # Store all iteration scores in structured format

    for i in range(max_self_reflections):
        print(f"  Self-reflection iteration {i+1}/{max_self_reflections}...")
        
        raw_response = await agent.run(messages=messages)
        agent_response = raw_response.text

        # Evaluate groundedness
        start_time_eval = time.time()
        eval_run_output_items = run_eval(
            client=client,
            eval_object=eval_object,
            query=full_user_query,
            response=agent_response,
            context=context,
        )
        if eval_run_output_items is None:
            print(f"  ⚠️ Groundedness evaluation failed (timeout or error) for iteration {i+1}.")
            continue
        score = eval_run_output_items[0].results[0].score
        end_time_eval = time.time()
        total_groundedness_eval_time += (end_time_eval - start_time_eval)

        # Store score in structured format
        iteration_scores.append(score)

        # Show groundedness score
        print(f"  Groundedness score: {score}/{max_score}")

        # Update best response if improved
        if score > best_score:
            if best_score > 0:
                print(f"  ✓ Score improved from {best_score} to {score}/{max_score}")
            best_score = score
            best_response = agent_response
            best_iteration = i + 1
            if score == max_score:
                print(f"  ✓ Perfect groundedness score achieved!")
                break
        else:
            print(f"  → No improvement (score: {score}/{max_score}). Trying again...")
        
        # Add to conversation history
        messages.append(ChatMessage(role="assistant", text=agent_response))

        # Request improvement
        reflection_prompt = (
            f"The groundedness score of your response is {score}/{max_score}. "
            f"Reflect on your answer and improve it to get the maximum score of {max_score} "
        )
        messages.append(ChatMessage(role="user", text=reflection_prompt))
    
    end_time = time.time()
    latency = end_time - start_time

    # Handle edge case where no response improved the score
    if best_response is None and raw_response is not None and len(raw_response.messages) > 0:
        best_response = raw_response.messages[0].text
        best_iteration = i + 1

    return {
        "best_response": best_response,
        "best_response_score": best_score,
        "best_iteration": best_iteration,
        "iteration_scores": iteration_scores,  # Structured list of all scores
        "messages": [message.to_json() for message in messages],
        "num_retries": i + 1,
        "total_groundedness_eval_time": total_groundedness_eval_time,
        "total_end_to_end_time": latency,
    }


async def run_self_reflection_batch(
    input_file: str,
    output_file: str,
    agent_model: str = DEFAULT_AGENT_MODEL,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    max_self_reflections: int = 3,
    env_file: str | None = None,
    limit: int | None = None
):
    """
    Run self-reflection on a batch of prompts.

    Args:
        input_file: Path to input JSONL file with prompts
        output_file: Path to save output JSONL file
        agent_model: Model to use for generating responses
        judge_model: Model to use for groundedness evaluation
        max_self_reflections: Maximum number of self-reflection iterations
        env_file: Optional path to .env file
        limit: Optional limit to process only the first N prompts
    """
    # Load environment variables
    if env_file and os.path.exists(env_file):
        load_dotenv(env_file, override=True)
    else:
        load_dotenv(override=True)

    # Create agent, it loads environment variables AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT automatically
    agent = AzureOpenAIChatClient(
        credential=AzureCliCredential(),
        deployment_name=agent_model,
    ).create_agent(
        instructions="You are a helpful agent.",
    )

    # Load input data
    print(f"Loading prompts from: {input_file}")
    df = pd.read_json(input_file, lines=True)
    print(f"Loaded {len(df)} prompts")

    # Apply limit if specified
    if limit is not None and limit > 0:
        df = df.head(limit)
        print(f"Processing first {len(df)} prompts (limited by -n {limit})")

    # Validate required columns
    required_columns = ['system_instruction', 'user_request', 'context_document', 
                       'full_prompt', 'domain', 'type', 'high_level_type']
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise ValueError(f"Input file missing required columns: {missing_columns}")
    
    # Configure clients
    print(f"Configuring Azure OpenAI client...")
    client = create_openai_client()

    # Create Eval
    eval_object = create_eval(client=client, judge_model=judge_model)
        
    # Process each prompt
    print(f"Max self-reflections: {max_self_reflections}\n")
    
    results = []
    for counter, (idx, row) in enumerate(df.iterrows(), start=1):
        print(f"[{counter}/{len(df)}] Processing prompt {row.get('original_index', idx)}...")
        
        try:
            result = await execute_query_with_self_reflection(
                client=client,
                agent=agent,
                eval_object=eval_object,
                full_user_query=row['full_prompt'],
                context=row['context_document'],
                max_self_reflections=max_self_reflections,
            )

            # Prepare result data
            result_data = {
                "original_index": row.get('original_index', idx),
                "domain": row['domain'],
                "question_type": row['type'],
                "high_level_type": row['high_level_type'],
                "full_prompt": row['full_prompt'],
                "system_prompt": row['system_instruction'],
                "user_request": row['user_request'],
                "context_document": row['context_document'],
                "agent_response_model": agent_model,
                "agent_response": result,
                "error": None,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            }
            results.append(result_data)

            print(f"  ✓ Completed with score: {result['best_response_score']}/5 "
                  f"(best at iteration {result['best_iteration']}/{result['num_retries']}, "
                  f"time: {result['total_end_to_end_time']:.1f}s)\n")

        except Exception as e:
            print(f"  ✗ Error: {str(e)}\n")

            # Save error information
            error_data = {
                "original_index": row.get('original_index', idx),
                "domain": row['domain'],
                "question_type": row['type'],
                "high_level_type": row['high_level_type'],
                "full_prompt": row['full_prompt'],
                "system_prompt": row['system_instruction'],
                "user_request": row['user_request'],
                "context_document": row['context_document'],
                "agent_response_model": agent_model,
                "agent_response": None,
                "error": str(e),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            }
            results.append(error_data)
            continue
    
    # Create DataFrame and save
    results_df = pd.DataFrame(results)

    print(f"\nSaving results to: {output_file}")
    results_df.to_json(output_file, orient='records', lines=True)

    # Generate detailed summary
    successful_runs = results_df[results_df['error'].isna()]
    failed_runs = results_df[results_df['error'].notna()]

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Total prompts processed: {len(results_df)}")
    print(f"  ✓ Successful: {len(successful_runs)}")
    print(f"  ✗ Failed: {len(failed_runs)}")

    if len(successful_runs) > 0:
        # Extract scores and iteration data from nested agent_response dict
        best_scores = [r['best_response_score'] for r in successful_runs['agent_response'] if r is not None]
        iterations = [r['best_iteration'] for r in successful_runs['agent_response'] if r is not None]
        iteration_scores_list = [r['iteration_scores'] for r in successful_runs['agent_response'] if r is not None and 'iteration_scores' in r]

        if best_scores:
            avg_score = sum(best_scores) / len(best_scores)
            perfect_scores = sum(1 for s in best_scores if s == 5)
            print(f"\nGroundedness Scores:")
            print(f"  Average best score: {avg_score:.2f}/5")
            print(f"  Perfect scores (5/5): {perfect_scores}/{len(best_scores)} ({100*perfect_scores/len(best_scores):.1f}%)")

            # Calculate improvement metrics
            if iteration_scores_list:
                first_scores = [scores[0] for scores in iteration_scores_list if len(scores) > 0]
                last_scores = [scores[-1] for scores in iteration_scores_list if len(scores) > 0]
                improvements = [last - first for first, last in zip(first_scores, last_scores)]
                improved_count = sum(1 for imp in improvements if imp > 0)

                if first_scores and last_scores:
                    avg_first_score = sum(first_scores) / len(first_scores)
                    avg_last_score = sum(last_scores) / len(last_scores)
                    avg_improvement = sum(improvements) / len(improvements)

                    print(f"\nImprovement Analysis:")
                    print(f"  Average first score: {avg_first_score:.2f}/5")
                    print(f"  Average final score: {avg_last_score:.2f}/5")
                    print(f"  Average improvement: +{avg_improvement:.2f}")
                    print(f"  Responses that improved: {improved_count}/{len(improvements)} ({100*improved_count/len(improvements):.1f}%)")

            # Show iteration statistics
            if iterations:
                avg_iteration = sum(iterations) / len(iterations)
                first_try = sum(1 for it in iterations if it == 1)
                print(f"\nIteration Statistics:")
                print(f"  Average best iteration: {avg_iteration:.2f}")
                print(f"  Best on first try: {first_try}/{len(iterations)} ({100*first_try/len(iterations):.1f}%)")

    print("="*60)


async def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Run self-reflection loop on LLM prompts with groundedness evaluation")
    parser.add_argument('--input', '-i', default="resources/suboptimal_groundedness_prompts.jsonl", help='Input JSONL file with prompts')
    parser.add_argument('--output', '-o', default="resources/results.jsonl", help='Output JSONL file for results')
    parser.add_argument('--agent-model', '-m', default=DEFAULT_AGENT_MODEL, help=f'Agent model deployment name (default: {DEFAULT_AGENT_MODEL})')
    parser.add_argument('--judge-model', '-e', default=DEFAULT_JUDGE_MODEL, help=f'Judge model deployment name (default: {DEFAULT_JUDGE_MODEL})')
    parser.add_argument('--max-reflections', type=int, default=3, help='Maximum number of self-reflection iterations (default: 3)')
    parser.add_argument('--env-file', help='Path to .env file with Azure OpenAI credentials')
    parser.add_argument('--limit', '-n', type=int, default=None, help='Process only the first N prompts from the input file')

    args = parser.parse_args()

    # Run the batch processing
    try:
        await run_self_reflection_batch(
            input_file=args.input,
            output_file=args.output,
            agent_model=args.agent_model,
            judge_model=args.judge_model,
            max_self_reflections=args.max_reflections,
            env_file=args.env_file,
            limit=args.limit
        )
        print("\n✓ Processing complete!")

    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        return 1
    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
