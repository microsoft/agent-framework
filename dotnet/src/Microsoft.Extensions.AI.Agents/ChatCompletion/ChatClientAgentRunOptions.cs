// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Chat client agent run options.
/// </summary>
internal sealed class ChatClientAgentRunOptions : AgentRunOptions
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ChatClientAgentRunOptions"/> class.
    /// </summary>
    /// <param name="agentRunOptions">An optional <see cref="AgentRunOptions"/> to clone from.</param>
    /// <param name="chatOptions">Optional chat options to pass to the agent's invocation.</param>
    internal ChatClientAgentRunOptions(AgentRunOptions? agentRunOptions = null, ChatOptions? chatOptions = null)
    {
        this.ChatOptions = chatOptions?.Clone() ?? new();

        this.AppendTools(agentRunOptions);
        this.AppendInstructions(agentRunOptions);
    }

    /// <summary>Gets or sets optional chat options to pass to the agent's invocation.</summary>
    public ChatOptions ChatOptions { get; set; }

    /// <inheritdoc />
    public override IList<AITool>? Tools
    {
        get => this.ChatOptions.Tools;
        set => this.ChatOptions.Tools = value;
    }

    /// <inheritdoc />
    public override string? Instructions
    {
        get => this.ChatOptions.Instructions;
        set => this.ChatOptions.Instructions = value;
    }

    private void AppendInstructions(AgentRunOptions? agentRunOptions)
    {
        if (agentRunOptions is null)
        {
            return;
        }

        if (!string.IsNullOrWhiteSpace(agentRunOptions.Instructions) && string.IsNullOrWhiteSpace(this.ChatOptions.Instructions))
        {
            this.ChatOptions.Instructions = agentRunOptions.Instructions;
            return;
        }

        if (!string.IsNullOrWhiteSpace(agentRunOptions.Instructions) && !string.IsNullOrWhiteSpace(this.ChatOptions.Instructions))
        {
            this.ChatOptions.Instructions = string.Concat(agentRunOptions.Instructions, "\n", this.Instructions);
        }
    }

    private void AppendTools(AgentRunOptions? agentRunOptions)
    {
        if (agentRunOptions is null || agentRunOptions.Tools is null)
        {
            return;
        }

        this.ChatOptions.Tools ??= [];
        if (this.ChatOptions.Tools is List<AITool> runToolsList)
        {
            runToolsList.AddRange(agentRunOptions.Tools);
        }
        else
        {
            foreach (var tool in agentRunOptions.Tools)
            {
                this.ChatOptions.Tools.Add(tool);
            }
        }
    }
}
