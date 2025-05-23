// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Threading.Tasks;

namespace Microsoft.Agents;

/// <summary>
/// Provides factory methods for creating implementations of <see cref="AIFunction"/> backed by an <see cref="Agent" />.
/// </summary>
[Experimental("SKEXP0110")]
public static class AgentKernelFunctionFactory
{
    /// <summary>
    /// Creates a <see cref="AIFunction"/> that will invoke the provided Agent.
    /// </summary>
    /// <param name="agent">The <see cref="Agent" /> to be represented via the created <see cref="AIFunction"/>.</param>
    /// <param name="name">The name to use for the function. If null, it will default to the agent name.</param>
    /// <param name="description">The description to use for the function. If null, it will default to agent description.</param>
    /// <param name="loggerFactory">The <see cref="ILoggerFactory"/> to use for logging. If null, no logging will be performed.</param>
    /// <returns>The created <see cref="ChatMessage"/> for invoking the <see cref="Agent"/>.</returns>
    [RequiresUnreferencedCode("Uses reflection to handle various aspects of the function creation and invocation, making it incompatible with AOT scenarios.")]
    [RequiresDynamicCode("Uses reflection to handle various aspects of the function creation and invocation, making it incompatible with AOT scenarios.")]
    public static AIFunction CreateFromAgent(
        Agent agent,
        string? name = null,
        string? description = null,
        ILoggerFactory? loggerFactory = null)
    {
        Verify.NotNull(agent);

        async Task<ChatMessage[]> InvokeAgentAsync(string query, string? additionalInstructions = null)
        {
            AgentInvokeOptions? options = null;
            if (!string.IsNullOrEmpty(additionalInstructions))
            {
                options = new()
                {
                    AdditionalInstructions = additionalInstructions!
                };
            }

            var response = agent.InvokeAsync(new ChatMessage(ChatRole.User, query), null, options);
            var responseItems = await response.ToArrayAsync().ConfigureAwait(false);
            var chatMessages = responseItems.Select(i => i.Message).ToArray();
            return chatMessages;
        }

        return AIFunctionFactory.Create(InvokeAgentAsync, name, description);
    }

    #region private
    #endregion
}
