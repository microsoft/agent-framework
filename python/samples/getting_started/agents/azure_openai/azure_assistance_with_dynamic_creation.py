# Copyright (c) Microsoft. All rights reserved.
import asyncio
from typing import List, Dict, Any
from agent_framework import ChatAgent
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential

"""
Sample: Dynamic Multi-Agent Analysis with Concurrent Processing

Demonstrates concurrent chunk processing using dynamically created AI agents.
Multiple analyst agents process data chunks in parallel, then an aggregator agent
synthesizes the results into a final report.

Purpose:
- Show how to create multiple agents dynamically for parallel processing
- Demonstrate concurrent execution using asyncio.gather()
- Illustrate agent coordination and result aggregation patterns
- Handle errors gracefully in multi-agent workflows

Prerequisites:
- Azure AI Agent Service configured with required environment variables
- Authentication via azure-identity. Run `az login` before executing
- Basic familiarity with async/await patterns and agent framework
"""

# Sample AI agent system data
SAMPLE_HTML_CONTENT = """
<html>
<body>
<div class="title">AI Agent Configuration</div>
<table>
<tr><th>Property</th><th>Value</th></tr>
<tr><td>Total Agents</td><td>15</td></tr>
<tr><td>Active Conversations</td><td>247</td></tr>
<tr><td>Custom Instructions</td><td>32</td></tr>
<tr><td>Tool Integrations</td><td>8</td></tr>
</table>

<div class="title">Agent Performance Metrics</div>
<table>
<tr><th>Metric</th><th>Value</th></tr>
<tr><td>Avg Response Time</td><td>1.2s</td></tr>
<tr><td>Success Rate</td><td>94.5%</td></tr>
<tr><td>Token Usage (24h)</td><td>2.4M</td></tr>
<tr><td>Cost per Request</td><td>$0.023</td></tr>
</table>

<div class="title">Agent Capabilities</div>
<table>
<tr><th>Agent Type</th><th>Count</th><th>Functions</th></tr>
<tr><td>Research Agent</td><td>3</td><td>web_search, document_analysis</td></tr>
<tr><td>Code Agent</td><td>5</td><td>code_generation, debugging, testing</td></tr>
<tr><td>Data Agent</td><td>4</td><td>sql_query, data_visualization</td></tr>
<tr><td>Workflow Agent</td><td>3</td><td>task_orchestration, approval_routing</td></tr>
</table>

<div class="title">Model Configuration</div>
<p>Primary Model: GPT-4 Turbo</p>
<p>Fallback Model: GPT-3.5 Turbo</p>
<p>Max Tokens per Request: 8000</p>
<p>Temperature: 0.7</p>
<p>Top-p: 0.95</p>

<div class="title">Integration Status</div>
<p>Connected APIs: 12</p>
<p>Database Connections: 5</p>
<p>Webhook Endpoints: 18</p>
<p>Real-time Streaming: Enabled</p>
</body>
</html>
"""


def chunk_html_content(html_content: str, max_chunk_size: int = 1000) -> List[str]:
    """Split HTML content into processable chunks by section."""
    chunks = []
    sections = html_content.split('<div class="title">')

    for section in sections[1:]:
        next_title_index = section.find('<div class="title">')
        section_content = section[:next_title_index] if next_title_index > 0 else section

        title_end = section_content.find('</div>')
        if title_end > 0:
            full_chunk = f'<div class="title">{section_content}'
            if len(full_chunk) > 50:
                chunks.append(full_chunk)

    return chunks


def create_analyst_agent(client: AzureAIAgentClient, chunk_index: int) -> ChatAgent:
    """Create an analyst agent for a specific chunk."""
    return client.create_agent(
        name=f"Analyst_{chunk_index}",
        instructions=(
            "You are an AI Agent System Analyst analyzing agent configuration and performance data. "
            "Extract key metrics and provide technical analysis focusing on: "
            "agent configuration and deployment, performance metrics and efficiency, "
            "tool capabilities and integrations, and model configuration parameters. "
            "Provide structured analysis with specific numbers and technical insights."
        ),
    )


def create_aggregator_agent(client: AzureAIAgentClient) -> ChatAgent:
    """Create an aggregator agent to synthesize chunk analyses."""
    return client.create_agent(
        name="Aggregator",
        instructions=(
            "You are an AI Agent System Report Aggregator. "
            "Create comprehensive technical analysis reports that synthesize multiple chunk analyses. "
            "Generate reports with these sections: "
            "1. Executive Summary - Overall agent system health "
            "2. Agent Performance Analysis - Metrics and efficiency "
            "3. Capability Assessment - Tool usage and integration status "
            "4. Model Configuration Review - Parameter optimization "
            "5. Recommendations - Optimization opportunities. "
            "Focus on technical accuracy and provide specific, actionable recommendations."
        ),
    )


async def analyze_chunk_with_agent(
    client: AzureAIAgentClient,
    chunk: str,
    chunk_index: int
) -> Dict[str, Any]:
    """Analyze a single chunk using a dynamically created agent."""
    try:
        analyst_agent = create_analyst_agent(client, chunk_index)

        analysis_prompt = f"""
        Analyze this AI agent system configuration section:

        **SECTION CONTENT:**
        {chunk}

        Provide structured analysis with specific metrics and technical insights.
        """

        response = await analyst_agent.run(analysis_prompt)

        if response.messages:
            return {
                "chunk_index": chunk_index,
                "analysis": response.messages[-1].content,
                "success": True
            }
        else:
            return {
                "chunk_index": chunk_index,
                "analysis": "Analysis failed - no response",
                "success": False
            }

    except Exception as e:
        return {
            "chunk_index": chunk_index,
            "analysis": f"Analysis failed: {e}",
            "success": False
        }


async def aggregate_analyses(
    client: AzureAIAgentClient,
    chunk_analyses: List[Dict[str, Any]]
) -> str:
    """Aggregate chunk analyses into a final report."""
    try:
        aggregator_agent = create_aggregator_agent(client)

        successful_analyses = [a for a in chunk_analyses if a["success"]]
        combined = "\n\n".join([
            f"## CHUNK {a['chunk_index']}\n{a['analysis']}"
            for a in successful_analyses
        ])

        if not combined:
            return "ERROR: No successful analyses to aggregate"

        aggregation_prompt = f"""
        Create a comprehensive AI agent system analysis report from these chunk analyses:

        **CHUNK ANALYSES:**
        {combined}

        Generate a complete report with all required sections.
        """

        response = await aggregator_agent.run(aggregation_prompt)

        return response.messages[-1].content if response.messages else "ERROR: Failed to generate report"

    except Exception as e:
        return f"Aggregation failed: {e}"


async def main() -> None:
    """Main function demonstrating dynamic multi-agent concurrent analysis."""
    async with AzureCliCredential() as cred, AzureAIAgentClient(async_credential=cred) as client:
        print("Starting Dynamic Multi-Agent Analysis Demo")
        
        # Create chunks from sample data
        chunks = chunk_html_content(SAMPLE_HTML_CONTENT)
        print(f"Processing {len(chunks)} chunks concurrently...")

        # Analyze chunks concurrently with dynamic agents
        analysis_tasks = [
            analyze_chunk_with_agent(client, chunk, i)
            for i, chunk in enumerate(chunks)
        ]

        chunk_results = await asyncio.gather(*analysis_tasks, return_exceptions=True)

        # Handle results and exceptions
        chunk_analyses = []
        for i, result in enumerate(chunk_results):
            if isinstance(result, Exception):
                chunk_analyses.append({
                    "chunk_index": i,
                    "analysis": f"Failed: {result}",
                    "success": False
                })
            else:
                chunk_analyses.append(result)

        successful = sum(1 for a in chunk_analyses if a["success"])
        print(f"Completed {successful}/{len(chunk_analyses)} chunk analyses")

        # Aggregate results into final report
        print("\nGenerating final aggregated report...")
        final_report = await aggregate_analyses(client, chunk_analyses)

        # Display results
        print("\n" + "=" * 80)
        print("ANALYSIS RESULTS")
        print("=" * 80)
        print(f"\nChunks Processed: {len(chunk_analyses)}")
        print(f"Successful: {successful}")
        print(f"Failed: {len(chunk_analyses) - successful}")

        print("\n" + "-" * 80)
        print("CHUNK RESULTS:")
        print("-" * 80)
        for analysis in chunk_analyses:
            status = "✅" if analysis["success"] else "❌"
            preview = analysis['analysis'][:100] + "..." if len(analysis['analysis']) > 100 else analysis['analysis']
            print(f"\n{status} Chunk {analysis['chunk_index']}: {preview}")

        print("\n" + "=" * 80)
        print("FINAL AGGREGATED REPORT:")
        print("=" * 80)
        print(final_report)


if __name__ == "__main__":
    asyncio.run(main())