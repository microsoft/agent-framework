// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using System;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents;

/// <summary>
/// Provides a <see cref="AgentFactory"/> which creates instances of <see cref="ChatClientAgent"/>.
/// </summary>
[Experimental("SKEXP0110")]
public sealed class ChatClientAgentFactory : AgentFactory
{
    /// <summary>
    /// The type of the chat completion agent.
    /// </summary>
    public const string ChatClientAgentType = "chat_completion_agent";

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatClientAgentFactory"/> class.
    /// </summary>
    public ChatClientAgentFactory()
        : base([ChatClientAgentType])
    {
    }

    /// <inheritdoc/>
    public override Task<Agent?> TryCreateAsync(IServiceProvider serviceProvider, AgentDefinition agentDefinition, AgentCreationOptions? agentCreationOptions = null, CancellationToken cancellationToken = default)
    {
        Verify.NotNull(agentDefinition);

        ChatClientAgent? agent = null;
        if (this.IsSupported(agentDefinition))
        {
            agent = new ChatClientAgent()
            {
                Name = agentDefinition.Name,
                Description = agentDefinition.Description,
                Instructions = agentDefinition.Instructions,
                ChatClient = serviceProvider.GetRequiredService<IChatClient>(),
            };
        }

        return Task.FromResult<Agent?>(agent);
    }
}
