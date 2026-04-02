// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// A <see cref="ResponseHandler"/> implementation that bridges the Azure AI Responses Server SDK
/// with agent-framework <see cref="AIAgent"/> instances, enabling agent-framework agents and workflows
/// to be hosted as Azure Foundry Hosted Agents.
/// </summary>
public class AgentFrameworkResponseHandler : ResponseHandler
{
    private readonly IServiceProvider _serviceProvider;
    private readonly ILogger<AgentFrameworkResponseHandler> _logger;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentFrameworkResponseHandler"/> class
    /// that resolves agents from keyed DI services.
    /// </summary>
    /// <param name="serviceProvider">The service provider for resolving agents.</param>
    /// <param name="logger">The logger instance.</param>
    public AgentFrameworkResponseHandler(
        IServiceProvider serviceProvider,
        ILogger<AgentFrameworkResponseHandler> logger)
    {
        ArgumentNullException.ThrowIfNull(serviceProvider);
        ArgumentNullException.ThrowIfNull(logger);

        this._serviceProvider = serviceProvider;
        this._logger = logger;
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<ResponseStreamEvent> CreateAsync(
        CreateResponse request,
        ResponseContext context,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        // 1. Resolve agent
        var agent = this.ResolveAgent(request);

        // 2. Create the SDK event stream builder
        var stream = new ResponseEventStream(context, request);

        // 3. Emit lifecycle events
        yield return stream.EmitCreated();
        yield return stream.EmitInProgress();

        // 4. Convert input: history + current input → ChatMessage[]
        var messages = new List<ChatMessage>();

        // Load conversation history if available
        var history = await context.GetHistoryAsync(cancellationToken).ConfigureAwait(false);
        if (history.Count > 0)
        {
            messages.AddRange(InputConverter.ConvertOutputItemsToMessages(history));
        }

        // Load and convert current input items
        var inputItems = await context.GetInputItemsAsync(cancellationToken).ConfigureAwait(false);
        if (inputItems.Count > 0)
        {
            messages.AddRange(InputConverter.ConvertOutputItemsToMessages(inputItems));
        }
        else
        {
            // Fall back to raw request input
            messages.AddRange(InputConverter.ConvertInputToMessages(request));
        }

        // 5. Build chat options
        var chatOptions = InputConverter.ConvertToChatOptions(request);
        chatOptions.Instructions = request.Instructions;
        var options = new ChatClientAgentRunOptions(chatOptions);

        // 6. Run the agent and convert output
        // NOTE: C# forbids 'yield return' inside a try block that has a catch clause,
        // and inside catch blocks. We use a flag to defer the yield to outside the try/catch.
        bool emittedTerminal = false;
        var enumerator = OutputConverter.ConvertUpdatesToEventsAsync(
            agent.RunStreamingAsync(messages, options: options, cancellationToken: cancellationToken),
            stream,
            cancellationToken).GetAsyncEnumerator(cancellationToken);
        try
        {
            while (true)
            {
                bool shutdownDetected = false;
                ResponseStreamEvent? evt = null;
                try
                {
                    if (!await enumerator.MoveNextAsync().ConfigureAwait(false))
                    {
                        break;
                    }

                    evt = enumerator.Current;
                }
                catch (OperationCanceledException) when (context.IsShutdownRequested && !emittedTerminal)
                {
                    shutdownDetected = true;
                }

                if (shutdownDetected)
                {
                    // Server is shutting down — emit incomplete so clients can resume
                    this._logger.LogInformation("Shutdown detected, emitting incomplete response.");
                    yield return stream.EmitIncomplete();
                    yield break;
                }

                // yield is in the outer try (finally-only) — allowed by C#
                yield return evt!;

                if (evt is ResponseCompletedEvent or ResponseFailedEvent or ResponseIncompleteEvent)
                {
                    emittedTerminal = true;
                }
            }
        }
        finally
        {
            await enumerator.DisposeAsync().ConfigureAwait(false);
        }
    }

    /// <summary>
    /// Resolves an <see cref="AIAgent"/> from the request.
    /// Tries <c>agent.name</c> first, then falls back to <c>metadata["entity_id"]</c>.
    /// If neither is present, attempts to resolve a default (non-keyed) <see cref="AIAgent"/>.
    /// </summary>
    private AIAgent ResolveAgent(CreateResponse request)
    {
        var agentName = GetAgentName(request);

        if (!string.IsNullOrEmpty(agentName))
        {
            var agent = this._serviceProvider.GetKeyedService<AIAgent>(agentName);
            if (agent is not null)
            {
                return agent;
            }

            this._logger.LogWarning("Agent '{AgentName}' not found in keyed services. Attempting default resolution.", agentName);
        }

        // Try non-keyed default
        var defaultAgent = this._serviceProvider.GetService<AIAgent>();
        if (defaultAgent is not null)
        {
            return defaultAgent;
        }

        var errorMessage = string.IsNullOrEmpty(agentName)
            ? "No agent name specified in the request (via agent.name or metadata[\"entity_id\"]) and no default AIAgent is registered."
            : $"Agent '{agentName}' not found. Ensure it is registered via AddAIAgent(\"{agentName}\", ...) or as a default AIAgent.";

        throw new InvalidOperationException(errorMessage);
    }

    private static string? GetAgentName(CreateResponse request)
    {
        // Try agent.name from AgentReference
        var agentName = request.AgentReference?.Name;

        // Fall back to "model" field (OpenAI clients send the agent name as the model)
        if (string.IsNullOrEmpty(agentName))
        {
            agentName = request.Model;
        }

        // Fall back to metadata["entity_id"]
        if (string.IsNullOrEmpty(agentName) && request.Metadata?.AdditionalProperties is not null)
        {
            request.Metadata.AdditionalProperties.TryGetValue("entity_id", out agentName);
        }

        return agentName;
    }
}
