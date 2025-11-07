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
    public ValueTask<ResponseError?> ValidateRequestAsync(
        CreateResponse request,
        CancellationToken cancellationToken = default)
    {
        // Extract agent name from agent.name or model parameter
        string? agentName = request.Agent?.Name ?? request.Model;

        if (string.IsNullOrEmpty(agentName))
        {
            return ValueTask.FromResult<ResponseError?>(new ResponseError
            {
                Code = "missing_required_parameter",
                Message = "No 'agent.name' or 'model' specified in the request."
            });
        }

        // Validate that the agent can be resolved
        AIAgent? agent = this._serviceProvider.GetKeyedService<AIAgent>(agentName);
        if (agent is null)
        {
            this._logger.LogWarning("Failed to resolve agent with name '{AgentName}'", agentName);
            return ValueTask.FromResult<ResponseError?>(new ResponseError
            {
                Code = "agent_not_found",
                Message = $"Agent '{agentName}' not found. Ensure the agent is registered with AddAIAgent()."
            });
        }

        return ValueTask.FromResult<ResponseError?>(null);
    }

    /// <inheritdoc/>
    public async IAsyncEnumerable<StreamingResponseEvent> ExecuteAsync(
        AgentInvocationContext context,
        CreateResponse request,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        // Extract agent name from agent.name or model parameter
        string? model;
        if (request.Agent?.Name is { } agentName)
        {
            model = request.Model;
        }
        else
        {
            // If the model is being used for the agent name, do not also use it for the model.
            agentName = request.Model;
            model = null;
        }

        if (string.IsNullOrEmpty(agentName))
        {
            throw new InvalidOperationException("No 'agent.name' or 'model' specified in the request.");
        }

        // Validate and resolve agent synchronously to ensure validation errors are thrown immediately
        AIAgent agent;
        try
        {
            // Resolve the keyed agent service
            agent = this._serviceProvider.GetRequiredKeyedService<AIAgent>(agentName);
        }
        catch (InvalidOperationException ex)
        {
            this._logger.LogError(ex, "Failed to resolve agent with name '{AgentName}'", agentName);
            throw new InvalidOperationException($"Agent '{agentName}' not found. Ensure the agent is registered with AddAIAgent().", ex);
        }

        // Create options with properties from the request
        var chatOptions = new ChatOptions
        {
            ConversationId = request.Conversation?.Id,
            Temperature = (float?)request.Temperature,
            TopP = (float?)request.TopP,
            MaxOutputTokens = request.MaxOutputTokens,
            Instructions = request.Instructions,
            ModelId = model,
        };
        var options = new ChatClientAgentRunOptions(chatOptions);

        // Convert input to chat messages
        var messages = new List<ChatMessage>();

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
}
