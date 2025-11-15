"""
Self-Reflection LLM Runner

This module implements a self-reflection loop for LLM responses using groundedness evaluation.
It loads prompts from a parquet file, runs them through an LLM with self-reflection,
and saves the results.

Can be used as a library or as a standalone CLI tool.

Usage as CLI:
    python self_reflection_runner.py

Usage as CLI with extra options:
    python self_reflection_runner.py --input resources/suboptimal_groundedness_prompts.parquet \\
                                     --output resources/results.parquet \\
                                     --max-reflections 3 \\
                                     -n 10  # Optional: process only first 10 prompts

Usage as library:
    from self_reflection_runner import run_self_reflection_batch
    
    results_df = run_self_reflection_batch(
        input_file='resources/suboptimal_groundedness_prompts.parquet',
        max_self_reflections=3
    )
"""

import os
import time
import argparse
import pandas as pd
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from openai import AzureOpenAI
from azure.ai.evaluation import GroundednessEvaluator, AzureOpenAIModelConfiguration


DEFAULT_AGENT_MODEL = "gpt-4.1"
DEFAULT_JUDGE_MODEL = "gpt-4.1"


def configure_azure_openai(
    endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    api_version: str = "2024-12-01-preview"
) -> AzureOpenAI:
    """
    Configure Azure OpenAI client.
    
    Args:
        endpoint: Azure OpenAI endpoint (defaults to env var AZURE_OPENAI_ENDPOINT)
        api_key: Azure OpenAI API key (defaults to env var AZURE_OPENAI_API_KEY)
        api_version: API version to use
        
    Returns:
        Configured AzureOpenAI client
    """
    endpoint = endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT")
    api_key = api_key or os.environ.get("AZURE_OPENAI_API_KEY")
    
    if not endpoint or not api_key:
        raise ValueError("Azure OpenAI endpoint and API key must be provided via parameters or environment variables")
    
    return AzureOpenAI(
        api_version=api_version,
        azure_endpoint=endpoint,
        api_key=api_key,
    )


def create_groundedness_evaluator(
    judge_model: str,
    endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    api_version: str = "2024-12-01-preview"
) -> GroundednessEvaluator:
    """
    Create a groundedness evaluator.
    
    Args:
        judge_model: Model deployment name for evaluation
        endpoint: Azure OpenAI endpoint
        api_key: Azure OpenAI API key
        api_version: API version
        
    Returns:
        Configured GroundednessEvaluator
    """
    endpoint = endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT")
    api_key = api_key or os.environ.get("AZURE_OPENAI_API_KEY")
    
    judge_model_config = AzureOpenAIModelConfiguration(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
        azure_deployment=judge_model,
    )
    
    return GroundednessEvaluator(model_config=judge_model_config)


def do_query_with_self_reflection(
    full_user_query: str,
    agent_model_name: str,
    query: str,
    context: str,
    evaluator: GroundednessEvaluator,
    max_self_reflections: int = 3,
    max_completion_tokens: int = 32768,
    client: Optional[AzureOpenAI] = None
) -> Dict[str, Any]:
    """
    Execute a query with self-reflection loop.
    
    Args:
        full_user_query: Complete prompt including system prompt, user request, and context
        agent_model_name: Name of the agent model to use
        query: Just the user request (without system prompt or context)
        context: Context document for groundedness evaluation
        evaluator: Groundedness evaluator function
        max_self_reflections: Maximum number of self-reflection iterations
        max_completion_tokens: Maximum tokens for completion
        client: Optional pre-configured AzureOpenAI client
        
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
    messages = [{"role": "user", "content": full_user_query}]
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
        
        # Get agent response
        raw_response = client.chat.completions.create(
            messages=messages,
            max_completion_tokens=max_completion_tokens,
            model=agent_model_name,
        )
        agent_response = raw_response.choices[0].message.content
        
        # Evaluate groundedness
        start_time_eval = time.time()
        groundedness_res = evaluator(
            query=query,
            response=agent_response,
            context=context
        )
        end_time_eval = time.time()
        total_groundedness_eval_time += (end_time_eval - start_time_eval)

        feedback = groundedness_res['groundedness_reason']
        score = int(groundedness_res['groundedness'])

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
        messages.append({"role": "assistant", "content": agent_response})
        
        # Request improvement
        reflection_prompt = (
            f"The groundedness score of your response is {score}/{max_score}. "
            f"Explanation for score: [{feedback}]. "
            f"Reflect on your answer and improve it to get the maximum score of {max_score} "
            f"considering the explanation. Now please provide an updated response, taking into "
            f"account the feedback, but make your answer sound as if it was your first response. "
            f"Don't refer to the feedback in your answer."
        )
        messages.append({"role": "user", "content": reflection_prompt})
    
    end_time = time.time()
    latency = end_time - start_time

    # Handle edge case where no response improved the score
    if best_response is None and raw_response is not None:
        best_response = raw_response.choices[0].message.content
        best_iteration = i + 1

    usage_metadata = {
        "completion_tokens": raw_response.usage.completion_tokens if raw_response.usage else None,
        "prompt_tokens": raw_response.usage.prompt_tokens if raw_response.usage else None,
        "total_tokens": raw_response.usage.total_tokens if raw_response.usage else None
    }

    return {
        "best_response": best_response,
        "best_response_score": best_score,
        "best_iteration": best_iteration,
        "iteration_scores": iteration_scores,  # Structured list of all scores
        "messages": messages,
        "usage_metadata": usage_metadata,
        "num_retries": i + 1,
        "total_groundedness_eval_time": total_groundedness_eval_time,
        "total_end_to_end_time": latency,
    }


def run_self_reflection_batch(
    input_file: str,
    output_file: str,
    agent_model: str = DEFAULT_AGENT_MODEL,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    max_self_reflections: int = 3,
    max_completion_tokens: int = 32768,
    env_file: Optional[str] = None,
    limit: Optional[int] = None
) -> pd.DataFrame:
    """
    Run self-reflection on a batch of prompts.

    Args:
        input_file: Path to input parquet file with prompts
        output_file: Path to save output parquet file
        agent_model: Model to use for generating responses
        judge_model: Model to use for groundedness evaluation
        max_self_reflections: Maximum number of self-reflection iterations
        max_completion_tokens: Maximum tokens for completion
        env_file: Optional path to .env file
        limit: Optional limit to process only the first N prompts

    Returns:
        DataFrame with results
    """
    # Load environment variables
    if env_file and os.path.exists(env_file):
        load_dotenv(env_file, override=True)
    else:
        load_dotenv(override=True)
    
    # Load input data
    print(f"Loading prompts from: {input_file}")
    df = pd.read_parquet(input_file)
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
    client = configure_azure_openai()
    
    print(f"Creating groundedness evaluator with model: {judge_model}")
    evaluator = create_groundedness_evaluator(judge_model)
    
    # Process each prompt
    print(f"\nProcessing prompts with model: {agent_model}")
    print(f"Max self-reflections: {max_self_reflections}\n")
    
    results = []
    for counter, (idx, row) in enumerate(df.iterrows(), start=1):
        print(f"[{counter}/{len(df)}] Processing prompt {row.get('original_index', idx)}...")
        
        try:
            result = do_query_with_self_reflection(
                full_user_query=row['full_prompt'],
                agent_model_name=agent_model,
                query=row['user_request'],
                context=row['context_document'],
                evaluator=evaluator,
                max_self_reflections=max_self_reflections,
                max_completion_tokens=max_completion_tokens,
                client=client
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
    results_df.to_parquet(output_file, index=False)

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

    return results_df


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Run self-reflection loop on LLM prompts with groundedness evaluation")
    parser.add_argument('--input', '-i', default="resources/suboptimal_groundedness_prompts.parquet", help='Input parquet file with prompts')
    parser.add_argument('--output', '-o', default="resources/results.parquet", help='Output parquet file for results')
    parser.add_argument('--model', '-m', default=DEFAULT_AGENT_MODEL, help=f'Agent model deployment name (default: {DEFAULT_AGENT_MODEL})')
    parser.add_argument('--judge-model', '-e', default=DEFAULT_JUDGE_MODEL, help=f'Judge model deployment name (default: {DEFAULT_JUDGE_MODEL})')
    parser.add_argument('--max-reflections', type=int, default=3, help='Maximum number of self-reflection iterations (default: 3)')
    parser.add_argument('--max-tokens', type=int, default=32768, help='Maximum completion tokens (default: 32768)')
    parser.add_argument('--env-file', help='Path to .env file with Azure OpenAI credentials')
    parser.add_argument('--limit', '-n', type=int, default=None, help='Process only the first N prompts from the input file')

    args = parser.parse_args()
    
    # Run the batch processing
    try:
        results_df = run_self_reflection_batch(
            input_file=args.input,
            output_file=args.output,
            agent_model=args.model,
            judge_model=args.judge_model,
            max_self_reflections=args.max_reflections,
            max_completion_tokens=args.max_tokens,
            env_file=args.env_file,
            limit=args.limit
        )
        print("\n✓ Processing complete!")

    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        return 1
    return 0


if __name__ == "__main__":
    exit(main())
