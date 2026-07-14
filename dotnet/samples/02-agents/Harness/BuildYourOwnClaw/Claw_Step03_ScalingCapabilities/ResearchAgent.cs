// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace ClawSample;

/// <summary>
/// Builds the background "research" agent that the main claw fans work out to.
/// </summary>
/// <remarks>
/// This sub-agent doesn't need any of the harness machinery, so it's a plain
/// <see cref="ChatClientAgent"/> with a single tool: the hosted web search. The parent claw
/// delegates a per-ticker research task to one of these and they run concurrently.
/// </remarks>
internal static class ResearchAgent
{
    /// <summary>Creates a web-search-only background agent for delegated ticker research.</summary>
    /// <param name="chatClient">The chat client the background agent should use.</param>
    public static AIAgent Create(IChatClient chatClient) =>
        chatClient.AsAIAgent(
            instructions:
                "You research a single stock ticker. Use the web search tool to find the most " +
                "recent, relevant news and commentary, then return a short, factual summary " +
                "(3-4 bullet points) with no preamble.",
            name: "TickerResearchAgent",
            description: "Searches the web for recent news and commentary about a single stock ticker.",
            // The only tool it needs: the same hosted web search the harness would have added.
            tools: [new HostedWebSearchTool()]);
}
