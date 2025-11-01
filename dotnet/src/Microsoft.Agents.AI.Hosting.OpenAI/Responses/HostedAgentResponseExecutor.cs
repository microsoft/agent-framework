// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses;

/// <summary>
/// Response executor that routes requests to hosted AIAgent services based on the model or agent.name parameter.
/// This executor resolves agents from keyed services registered via AddAIAgent().
/// </summary>
internal sealed class HostedAgentResponseExecutor : IResponseExecutor
{
    private readonly IServiceProvider _serviceProvider;
    private readonly ILogger<HostedAgentResponseExecutor> _logger;

    /// <summary>
    /// Initializes a new instance of the <see cref="HostedAgentResponseExecutor"/> class.
    /// </summary>
    /// <param name="serviceProvider">The service provider used to resolve hosted agents.</param>
    /// <param name="logger">The logger instance.</param>
    public HostedAgentResponseExecutor(
        IServiceProvider serviceProvider,
        ILogger<HostedAgentResponseExecutor> logger)
    {
        ArgumentNullException.ThrowIfNull(serviceProvider);
        ArgumentNullException.ThrowIfNull(logger);

        this._serviceProvider = serviceProvider;
        this._logger = logger;
    }

    /// <inheritdoc/>
    public async IAsyncEnumerable<StreamingResponseEvent> ExecuteAsync(
        AgentInvocationContext context,
        CreateResponse request,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        // Validate and resolve agent synchronously to ensure validation errors are thrown immediately
        AIAgent agent = this.ResolveAgent(request);

        // Create options with properties from the request
        var chatOptions = new ChatOptions
        {
            ConversationId = request.Conversation?.Id,
            Temperature = (float?)request.Temperature,
            TopP = (float?)request.TopP,
            MaxOutputTokens = request.MaxOutputTokens,
            Instructions = request.Instructions,
            ModelId = request.Model,
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                ["RawRequest"] = request
            }
        };
        var options = new ChatClientAgentRunOptions(chatOptions);

        // Convert input to chat messages
        var messages = new List<ChatMessage>();

        // If instructions are provided in the request, prepend them as a system message
        if (!string.IsNullOrWhiteSpace(request.Instructions))
        {
            messages.Add(new ChatMessage(ChatRole.System, request.Instructions));
        }

        foreach (var inputMessage in request.Input.GetInputMessages())
        {
            messages.Add(inputMessage.ToChatMessage());
        }

        // Use the extension method to convert streaming updates to streaming response events
        await foreach (var streamingEvent in agent.RunStreamingAsync(messages, options: options, cancellationToken: cancellationToken)
            .ToStreamingResponseAsync(request, context, cancellationToken).ConfigureAwait(false))
        {
            yield return streamingEvent;
        }
    }

    /// <summary>
    /// Resolves an agent from the service provider based on the request.
    /// </summary>
    /// <param name="request">The create response request.</param>
    /// <returns>The resolved AIAgent instance.</returns>
    /// <exception cref="InvalidOperationException">Thrown when the agent cannot be resolved.</exception>
    private AIAgent ResolveAgent(CreateResponse request)
    {
        // Extract agent name from agent.name or model parameter
        var agentName = request.Agent?.Name ?? request.Model;
        if (string.IsNullOrEmpty(agentName))
        {
            throw new InvalidOperationException("No 'agent.name' or 'model' specified in the request.");
        }

        // Resolve the keyed agent service
        try
        {
            return this._serviceProvider.GetRequiredKeyedService<AIAgent>(agentName);
        }
        catch (InvalidOperationException ex)
        {
            this._logger.LogError(ex, "Failed to resolve agent with name '{AgentName}'", agentName);
            throw new InvalidOperationException($"Agent '{agentName}' not found. Ensure the agent is registered with AddAIAgent().", ex);
        }
    }

    /// <summary>
    /// Validates that the agent can be resolved without actually resolving it.
    /// This allows early validation before starting async execution.
    /// </summary>
    /// <param name="request">The create response request.</param>
    /// <exception cref="InvalidOperationException">Thrown when the agent cannot be resolved.</exception>
    public void ValidateAgent(CreateResponse request)
    {
        // Use the same logic as ResolveAgent but don't return the agent
        _ = this.ResolveAgent(request);
    }
}
