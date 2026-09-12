// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace ClawAgent;

/// <summary>
/// Builds the background research agent that the main claw fans work out to.
/// </summary>
internal static class ResearchAgent
{
    /// <summary>
    /// Creates a web-search-only background agent for delegated ticker research.
    /// </summary>
    public static AIAgent Create(IChatClient chatClient) =>
        chatClient.AsAIAgent(
            instructions:
                "You research a single stock ticker. Use the web search tool to find the most " +
                "recent, relevant news and commentary, then return a short, factual summary " +
                "(3-4 bullet points) with no preamble.",
            name: "TickerResearchAgent",
            description: "Searches the web for recent news and commentary about a single stock ticker.",
            tools: [new HostedWebSearchTool()]);
}
