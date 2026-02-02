# Copyright (c) Microsoft. All rights reserved.
"""Parallel Workflow Execution Sample.

This sample demonstrates parallel execution of executors and agents in Azure Durable Functions.
It showcases three different parallel execution patterns:

1. Two executors running concurrently (fan-out to activities)
2. Two agents running concurrently (fan-out to entities)
3. One executor and one agent running concurrently (mixed fan-out)

The workflow simulates a document processing pipeline where:
- A document is analyzed by multiple processors in parallel
- Results are aggregated and then processed by agents
- A summary agent and statistics executor run in parallel
- Finally, combined into a single output

Key architectural points:
- FanOut edges enable parallel execution
- Different agents run in parallel when they're in the same iteration
- Activities (executors) also run in parallel when pending together
- Mixed agent/executor fan-outs execute concurrently
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from agent_framework import (
    AgentExecutorResponse,
    Executor,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    executor,
    handler,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from pydantic import BaseModel
from typing_extensions import Never

from agent_framework_azurefunctions import AgentFunctionApp

logger = logging.getLogger(__name__)

AZURE_OPENAI_ENDPOINT_ENV = "AZURE_OPENAI_ENDPOINT"
AZURE_OPENAI_DEPLOYMENT_ENV = "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"
AZURE_OPENAI_API_KEY_ENV = "AZURE_OPENAI_API_KEY"

# Agent names
SENTIMENT_AGENT_NAME = "SentimentAnalysisAgent"
KEYWORD_AGENT_NAME = "KeywordExtractionAgent"
SUMMARY_AGENT_NAME = "SummaryAgent"
RECOMMENDATION_AGENT_NAME = "RecommendationAgent"


# ============================================================================
# Pydantic Models for structured outputs
# ============================================================================


class SentimentResult(BaseModel):
    """Result from sentiment analysis."""
    sentiment: str  # positive, negative, neutral
    confidence: float
    explanation: str


class KeywordResult(BaseModel):
    """Result from keyword extraction."""
    keywords: list[str]
    categories: list[str]


class SummaryResult(BaseModel):
    """Result from summarization."""
    summary: str
    key_points: list[str]


class RecommendationResult(BaseModel):
    """Result from recommendation engine."""
    recommendations: list[str]
    priority: str


@dataclass
class DocumentInput:
    """Input document to be processed."""
    document_id: str
    content: str


@dataclass
class ProcessorResult:
    """Result from a document processor (executor)."""
    processor_name: str
    document_id: str
    content: str
    word_count: int
    char_count: int
    has_numbers: bool


@dataclass 
class AggregatedResults:
    """Aggregated results from parallel processors."""
    document_id: str
    content: str
    processor_results: list[ProcessorResult]


@dataclass
class AgentAnalysis:
    """Analysis result from an agent."""
    agent_name: str
    result: str


@dataclass
class FinalReport:
    """Final combined report."""
    document_id: str
    analyses: list[AgentAnalysis]


# ============================================================================
# Executor Definitions (Activities - run in parallel when pending together)
# ============================================================================


@executor(id="input_router")
async def input_router(
    doc: str,
    ctx: WorkflowContext[DocumentInput]
) -> None:
    """Route input document to parallel processors.
    
    Accepts a JSON string from the HTTP request and converts to DocumentInput.
    """
    # Parse the JSON string input
    data = json.loads(doc) if isinstance(doc, str) else doc
    document = DocumentInput(
        document_id=data.get("document_id", "unknown"),
        content=data.get("content", ""),
    )
    logger.info("[input_router] Routing document: %s", document.document_id)
    await ctx.send_message(document)


@executor(id="word_count_processor")
async def word_count_processor(
    doc: DocumentInput, 
    ctx: WorkflowContext[ProcessorResult]
) -> None:
    """Process document and count words - runs as an activity."""
    logger.info("[word_count_processor] Processing document: %s", doc.document_id)
    
    word_count = len(doc.content.split())
    char_count = len(doc.content)
    has_numbers = any(c.isdigit() for c in doc.content)
    
    result = ProcessorResult(
        processor_name="word_count",
        document_id=doc.document_id,
        content=doc.content,
        word_count=word_count,
        char_count=char_count,
        has_numbers=has_numbers,
    )
    
    await ctx.send_message(result)


@executor(id="format_analyzer_processor")
async def format_analyzer_processor(
    doc: DocumentInput,
    ctx: WorkflowContext[ProcessorResult]
) -> None:
    """Analyze document format - runs as an activity in parallel with word_count."""
    logger.info("[format_analyzer_processor] Processing document: %s", doc.document_id)
    
    # Simple format analysis
    lines = doc.content.split('\n')
    word_count = len(lines)  # Using line count as "word count" for this processor
    char_count = sum(len(line) for line in lines)
    has_numbers = doc.content.count('.') > 0  # Check for sentences
    
    result = ProcessorResult(
        processor_name="format_analyzer",
        document_id=doc.document_id,
        content=doc.content,
        word_count=word_count,
        char_count=char_count,
        has_numbers=has_numbers,
    )
    
    await ctx.send_message(result)


@executor(id="aggregator")
async def aggregator(
    results: list[ProcessorResult],
    ctx: WorkflowContext[AggregatedResults]
) -> None:
    """Aggregate results from parallel processors - receives fan-in input."""
    logger.info("[aggregator] Aggregating %d results", len(results))
    
    # Extract document info from the first result (all have the same content)
    document_id = results[0].document_id if results else "unknown"
    content = results[0].content if results else ""
    
    aggregated = AggregatedResults(
        document_id=document_id,
        content=content,
        processor_results=results,
    )
    
    await ctx.send_message(aggregated)


@executor(id="prepare_for_agents")
async def prepare_for_agents(
    aggregated: AggregatedResults,
    ctx: WorkflowContext[str]
) -> None:
    """Prepare content for agent analysis - broadcasts to multiple agents."""
    logger.info("[prepare_for_agents] Preparing content for agents")
    
    # Send the original content to agents for analysis
    await ctx.send_message(aggregated.content)


@executor(id="prepare_for_mixed")
async def prepare_for_mixed(
    analyses: list[AgentExecutorResponse],
    ctx: WorkflowContext[str]
) -> None:
    """Prepare results for mixed agent+executor parallel processing.
    
    Combines agent analysis results into a string that can be consumed by
    both the SummaryAgent and the statistics_processor in parallel.
    """
    logger.info("[prepare_for_mixed] Preparing for mixed parallel pattern")
    
    sentiment_text = ""
    keyword_text = ""
    
    for analysis in analyses:
        executor_id = analysis.executor_id
        text = analysis.agent_response.text if analysis.agent_response else ""
            
        if executor_id == SENTIMENT_AGENT_NAME:
            sentiment_text = text
        elif executor_id == KEYWORD_AGENT_NAME:
            keyword_text = text
    
    # Combine into a string that both agent and executor can process
    combined = f"Sentiment Analysis: {sentiment_text}\n\nKeyword Extraction: {keyword_text}"
    await ctx.send_message(combined)


@executor(id="statistics_processor")
async def statistics_processor(
    analysis_text: str,
    ctx: WorkflowContext[ProcessorResult]
) -> None:
    """Calculate statistics from the analysis - runs in parallel with SummaryAgent."""
    logger.info("[statistics_processor] Calculating statistics")
    
    # Calculate some statistics from the combined analysis
    word_count = len(analysis_text.split())
    char_count = len(analysis_text)
    has_numbers = any(c.isdigit() for c in analysis_text)
    
    result = ProcessorResult(
        processor_name="statistics",
        document_id="analysis",
        content=analysis_text,
        word_count=word_count,
        char_count=char_count,
        has_numbers=has_numbers,
    )
    await ctx.send_message(result)


class FinalReportExecutor(Executor):
    """Executor that compiles the final report from agent analyses."""

    @handler
    async def compile_report(
        self,
        analyses: list[AgentExecutorResponse | ProcessorResult],
        ctx: WorkflowContext[Never, str],
    ) -> None:
        """Compile final report from mixed agent + processor results."""
        logger.info("[final_report] Compiling report from %d analyses", len(analyses))
        
        report_parts = ["=== Document Analysis Report ===\n"]
        
        for analysis in analyses:
            if isinstance(analysis, AgentExecutorResponse):
                agent_name = analysis.executor_id
                text = analysis.agent_response.text if analysis.agent_response else "No response"
            elif isinstance(analysis, ProcessorResult):
                agent_name = f"Processor: {analysis.processor_name}"
                text = f"Words: {analysis.word_count}, Chars: {analysis.char_count}"
            else:
                continue
                
            report_parts.append(f"\n--- {agent_name} ---")
            report_parts.append(text)
        
        final_report = "\n".join(report_parts)
        await ctx.yield_output(final_report)


class MixedResultCollector(Executor):
    """Collector for mixed agent/executor results."""

    @handler
    async def collect_mixed_results(
        self,
        results: list[Any],
        ctx: WorkflowContext[Never, str],
    ) -> None:
        """Collect and format results from mixed parallel execution."""
        logger.info("[mixed_collector] Collecting %d mixed results", len(results))
        
        output_parts = ["=== Mixed Parallel Execution Results ===\n"]
        
        for result in results:
            if isinstance(result, AgentExecutorResponse):
                output_parts.append(f"[Agent: {result.executor_id}]")
                output_parts.append(result.agent_response.text if result.agent_response else "No response")
            elif isinstance(result, ProcessorResult):
                output_parts.append(f"[Processor: {result.processor_name}]")
                output_parts.append(f"  Words: {result.word_count}, Chars: {result.char_count}")
        
        await ctx.yield_output("\n".join(output_parts))


# ============================================================================
# Workflow Construction
# ============================================================================


def _build_client_kwargs() -> dict[str, Any]:
    """Build Azure OpenAI client kwargs from environment variables."""
    endpoint = os.getenv(AZURE_OPENAI_ENDPOINT_ENV)
    if not endpoint:
        raise RuntimeError(f"{AZURE_OPENAI_ENDPOINT_ENV} environment variable is required.")

    deployment = os.getenv(AZURE_OPENAI_DEPLOYMENT_ENV)
    if not deployment:
        raise RuntimeError(f"{AZURE_OPENAI_DEPLOYMENT_ENV} environment variable is required.")

    client_kwargs: dict[str, Any] = {
        "endpoint": endpoint,
        "deployment_name": deployment,
    }

    api_key = os.getenv(AZURE_OPENAI_API_KEY_ENV)
    if api_key:
        client_kwargs["api_key"] = api_key
    else:
        client_kwargs["credential"] = AzureCliCredential()

    return client_kwargs


def _create_workflow() -> Workflow:
    """Create the parallel workflow definition.
    
    Workflow structure demonstrating three parallel patterns:
    
    Pattern 1: Two Executors in Parallel (Fan-out/Fan-in to activities)
    ────────────────────────────────────────────────────────────────────
                   ┌─> word_count_processor ─────┐
    input_router ──┤                             ├──> aggregator
                   └─> format_analyzer_processor ─┘
    
    Pattern 2: Two Agents in Parallel (Fan-out to entities)
    ────────────────────────────────────────────────────────
    prepare_for_agents ─┬─> SentimentAgent ──┐
                        └─> KeywordAgent ────┤
                                             └──> prepare_for_mixed
    
    Pattern 3: Mixed Agent + Executor in Parallel
    ──────────────────────────────────────────────
    prepare_for_mixed ─┬─> SummaryAgent ────────┐
                       └─> statistics_processor ─┤
                                                 └──> final_report
    """
    client_kwargs = _build_client_kwargs()
    chat_client = AzureOpenAIChatClient(**client_kwargs)

    # Create agents for parallel analysis
    sentiment_agent = chat_client.as_agent(
        name=SENTIMENT_AGENT_NAME,
        instructions=(
            "You are a sentiment analysis expert. Analyze the sentiment of the given text. "
            "Return JSON with fields: sentiment (positive/negative/neutral), "
            "confidence (0.0-1.0), and explanation (brief reasoning)."
        ),
        default_options={"response_format": SentimentResult},
    )

    keyword_agent = chat_client.as_agent(
        name=KEYWORD_AGENT_NAME,
        instructions=(
            "You are a keyword extraction expert. Extract important keywords and categories "
            "from the given text. Return JSON with fields: keywords (list of strings), "
            "and categories (list of topic categories)."
        ),
        default_options={"response_format": KeywordResult},
    )

    # Create summary agent for Pattern 3 (mixed parallel)
    summary_agent = chat_client.as_agent(
        name=SUMMARY_AGENT_NAME,
        instructions=(
            "You are a summarization expert. Given analysis results (sentiment and keywords), "
            "provide a concise summary. Return JSON with fields: summary (brief text), "
            "and key_points (list of main takeaways)."
        ),
        default_options={"response_format": SummaryResult},
    )

    # Create executor instances
    final_report_executor = FinalReportExecutor(id="final_report")

    # Build workflow with parallel patterns
    workflow = (
        WorkflowBuilder()
        # Start: Route input to parallel processors
        .set_start_executor(input_router)
        
        # Pattern 1: Fan-out to two executors (run in parallel)
        .add_fan_out_edges(
            source=input_router,
            targets=[word_count_processor, format_analyzer_processor],
        )
        
        # Fan-in: Both processors send results to aggregator
        .add_fan_in_edges(
            sources=[word_count_processor, format_analyzer_processor],
            target=aggregator,
        )
        
        # Prepare content for agent analysis
        .add_edge(aggregator, prepare_for_agents)
        
        # Pattern 2: Fan-out to two agents (run in parallel)
        .add_fan_out_edges(
            source=prepare_for_agents,
            targets=[sentiment_agent, keyword_agent],
        )
        
        # Fan-in: Collect agent results into prepare_for_mixed
        .add_fan_in_edges(
            sources=[sentiment_agent, keyword_agent],
            target=prepare_for_mixed,
        )
        
        # Pattern 3: Fan-out to one agent + one executor (mixed parallel)
        .add_fan_out_edges(
            source=prepare_for_mixed,
            targets=[summary_agent, statistics_processor],
        )
        
        # Final fan-in: Collect mixed results
        .add_fan_in_edges(
            sources=[summary_agent, statistics_processor],
            target=final_report_executor,
        )
        
        .build()
    )
    
    return workflow


# ============================================================================
# Application Entry Point
# ============================================================================


def launch(durable: bool = True) -> AgentFunctionApp | None:
    """Launch the function app or DevUI."""
    workflow: Workflow | None = None

    if durable:
        workflow = _create_workflow()
        app = AgentFunctionApp(
            workflow=workflow, 
            enable_health_check=True,
        )
        return app
    else:
        from pathlib import Path
        from agent_framework.devui import serve
        from dotenv import load_dotenv

        env_path = Path(__file__).parent / ".env"
        load_dotenv(dotenv_path=env_path)

        logger.info("Starting Parallel Workflow Sample")
        logger.info("Available at: http://localhost:8095")
        logger.info("\nThis workflow demonstrates:")
        logger.info("- Pattern 1: Two executors running in parallel")
        logger.info("- Pattern 2: Two agents running in parallel")
        logger.info("- Pattern 3: Mixed agent + executor running in parallel")
        logger.info("- Fan-in aggregation of parallel results")

        workflow = _create_workflow()
        serve(entities=[workflow], port=8095, auto_open=True)

        return None


# Default: Azure Functions mode
# Run with `python function_app.py --maf` for pure MAF mode with DevUI
app = launch(durable=True)


if __name__ == "__main__":
    import sys

    if "--maf" in sys.argv:
        # Run in pure MAF mode with DevUI
        launch(durable=False)
    else:
        print("Usage: python function_app.py --maf")
        print("  --maf    Run in pure MAF mode with DevUI (http://localhost:8095)")
        print("\nFor Azure Functions mode, use: func start")
