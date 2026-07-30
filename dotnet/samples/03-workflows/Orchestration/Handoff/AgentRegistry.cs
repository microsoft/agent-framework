// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

/// <summary>
/// The registry of agents used in the workflow.
/// </summary>
/// <param name="chatClient">The <see cref="IChatClient"/> to use as the agent backend.</param>
internal sealed class AgentRegistry(IChatClient chatClient)
{
    internal const string IntakeAgentName = "Assistant";
    public AIAgent IntakeAgent { get; } = chatClient.AsAIAgent(
        instructions:
            """
                You receive a user request and are responsible for routing to the correct initial expert agent.
                """,
        IntakeAgentName
        );

    internal const string LiquidityAnalysisAgentName = "Liquidity Analysis";
    public AIAgent LiquidityAnalysisAgent { get; } = chatClient.AsAIAgent(
        instructions:
            """
                You are responsible for Liquidity Analysis.
                """,
        LiquidityAnalysisAgentName
        );

    internal const string TaxAnalysisAgentName = "Tax Analysis";
    public AIAgent TaxAnalysisAgent { get; } = chatClient.AsAIAgent(
        instructions:
            """
                You are responsible for Tax Analysis. 
                """,
        TaxAnalysisAgentName
        );

    internal const string ForeignExchangeAgentName = "Foreign Exchange Analysis";
    public AIAgent ForeignExchangeAgent { get; } = chatClient.AsAIAgent(
        instructions:
            """
                You are responsible for Foreign Exchange Analysis. 
                """,
        ForeignExchangeAgentName
        );

    internal const string EquityAgentName = "Equity Analysis";
    public AIAgent EquityAgent { get; } = chatClient.AsAIAgent(
        instructions:
            """
                You are responsible for Equity Analysis. 
                """,
        EquityAgentName
        );

    public IEnumerable<AIAgent> Experts => [this.LiquidityAnalysisAgent, this.TaxAnalysisAgent, this.ForeignExchangeAgent, this.EquityAgent];

    public HashSet<AIAgent> All
    {
        get
        {
            if (field == null)
            {
                field = [this.IntakeAgent, .. this.Experts];
            }

            return field;
        }
    }
}
