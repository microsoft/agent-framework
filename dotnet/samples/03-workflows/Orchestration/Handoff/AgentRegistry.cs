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
    // <stable_agent_identity>
    // Give each agent a stable, unique Id so its workflow executor identity stays the same when the
    // workflow is reconstructed (for example per request or dependency-injection scope), which keeps
    // checkpoints resumable. If an agent also has a Name, keep that stable too, since the executor
    // identity includes it. Use a fixed logical role here, not a conversation, request, or user id.
    internal const string IntakeAgentName = "Assistant";
    public AIAgent IntakeAgent { get; } = chatClient.AsAIAgent(new ChatClientAgentOptions
    {
        Id = "intake-agent",
        Name = IntakeAgentName,
        ChatOptions = new()
        {
            Instructions =
                """
                You receive a user request and are responsible for routing to the correct initial expert agent.
                """,
        },
    });
    // </stable_agent_identity>

    internal const string LiquidityAnalysisAgentName = "Liquidity Analysis";
    public AIAgent LiquidityAnalysisAgent { get; } = chatClient.AsAIAgent(new ChatClientAgentOptions
    {
        Id = "liquidity-analysis-agent",
        Name = LiquidityAnalysisAgentName,
        ChatOptions = new()
        {
            Instructions =
                """
                You are responsible for Liquidity Analysis.
                """,
        },
    });

    internal const string TaxAnalysisAgentName = "Tax Analysis";
    public AIAgent TaxAnalysisAgent { get; } = chatClient.AsAIAgent(new ChatClientAgentOptions
    {
        Id = "tax-analysis-agent",
        Name = TaxAnalysisAgentName,
        ChatOptions = new()
        {
            Instructions =
                """
                You are responsible for Tax Analysis.
                """,
        },
    });

    internal const string ForeignExchangeAgentName = "Foreign Exchange Analysis";
    public AIAgent ForeignExchangeAgent { get; } = chatClient.AsAIAgent(new ChatClientAgentOptions
    {
        Id = "foreign-exchange-agent",
        Name = ForeignExchangeAgentName,
        ChatOptions = new()
        {
            Instructions =
                """
                You are responsible for Foreign Exchange Analysis.
                """,
        },
    });

    internal const string EquityAgentName = "Equity Analysis";
    public AIAgent EquityAgent { get; } = chatClient.AsAIAgent(new ChatClientAgentOptions
    {
        Id = "equity-analysis-agent",
        Name = EquityAgentName,
        ChatOptions = new()
        {
            Instructions =
                """
                You are responsible for Equity Analysis.
                """,
        },
    });

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
