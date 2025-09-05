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
    /// <remarks>
    /// Providing both <paramref name="agentRunOptions"/> and <paramref name="chatOptions"/> will result in the
    /// merge of instructions and tools when both are present.
    /// 1. <see cref="AgentRunOptions.Instructions"/> and <see cref="ChatOptions.Instructions"/>
    /// 2. <see cref="AgentRunOptions.Tools"/> and <see cref="ChatOptions.Tools"/>
    /// </remarks>
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
            // If no agent run options are provided, chat options instructions are used as is.
            return;
        }

        if (string.IsNullOrWhiteSpace(this.ChatOptions.Instructions) && !string.IsNullOrWhiteSpace(agentRunOptions.Instructions))
        {
            // Merge is not needed if the chat options instructions is not provided use the agent run options instructions.
            this.ChatOptions.Instructions = agentRunOptions.Instructions;
            return;
        }

        if (!string.IsNullOrWhiteSpace(agentRunOptions.Instructions) && !string.IsNullOrWhiteSpace(this.ChatOptions.Instructions))
        {
            // If both instructions are provided, concatenate in different lines.
            this.ChatOptions.Instructions = string.Concat(agentRunOptions.Instructions, "\n", this.Instructions);
        }
    }

    private void AppendTools(AgentRunOptions? agentRunOptions)
    {
        if (agentRunOptions is null || agentRunOptions.Tools is null)
        {
            // If no agent run options are provided, chat options tools are used as is.
            return;
        }

        this.ChatOptions.Tools ??= [];

        // Add to the chat options tools any existing agent run options tools.
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
