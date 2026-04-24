// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Runtime.CompilerServices;
using System.Threading;
using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// A <see cref="ResponseHandler"/> implementation that bridges the Azure AI Responses Server SDK
/// with agent-framework <see cref="AIAgent"/> instances, enabling agent-framework agents and workflows
/// to be hosted as Azure Foundry Hosted Agents.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AIOpenAIResponses)]
public class AgentFrameworkResponseHandler : ResponseHandler
{
    private readonly IServiceProvider _serviceProvider;
    private readonly ILogger<AgentFrameworkResponseHandler> _logger;
    private readonly FoundryToolboxService? _toolboxService;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentFrameworkResponseHandler"/> class
    /// that resolves agents from keyed DI services.
    /// </summary>
    /// <param name="serviceProvider">The service provider for resolving agents.</param>
    /// <param name="logger">The logger instance.</param>
    /// <param name="toolboxService">Optional Foundry Toolbox service providing MCP tools.</param>
    public AgentFrameworkResponseHandler(
        IServiceProvider serviceProvider,
        ILogger<AgentFrameworkResponseHandler> logger,
        FoundryToolboxService? toolboxService = null)
    {
        ArgumentNullException.ThrowIfNull(serviceProvider);
        ArgumentNullException.ThrowIfNull(logger);

        this._serviceProvider = serviceProvider;
        this._logger = logger;
        this._toolboxService = toolboxService;
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<ResponseStreamEvent> CreateAsync(
        CreateResponse request,
        ResponseContext context,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        // 1. Resolve agent
        var agent = this.ResolveAgent(request);
        var sessionStore = this.ResolveSessionStore(request);

        // 2. Load or create a new session from the interaction
        var sessionConversationId = request.GetConversationId();

        var chatClientAgent = agent.GetService<ChatClientAgent>();

        AgentSession? session = !string.IsNullOrWhiteSpace(sessionConversationId)
            ? await sessionStore.GetSessionAsync(agent, sessionConversationId, cancellationToken).ConfigureAwait(false)
                : chatClientAgent is not null
                ? await chatClientAgent.CreateSessionAsync(cancellationToken).ConfigureAwait(false)
                : await agent.CreateSessionAsync(cancellationToken).ConfigureAwait(false);

        // 3. Create the SDK event stream builder
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
        var inputItems = await context.GetInputItemsAsync(cancellationToken: cancellationToken).ConfigureAwait(false);
        if (inputItems.Count > 0)
        {
            messages.AddRange(InputConverter.ConvertItemsToMessages(inputItems));
        }
        else
        {
            // Fall back to raw request input
            messages.AddRange(InputConverter.ConvertInputToMessages(request));
        }

        // 5. Build chat options
        var chatOptions = InputConverter.ConvertToChatOptions(request);
        chatOptions.Instructions = request.Instructions;

        // Inject Foundry Toolbox tools when the toolbox service is available.
        //
        // Two sources are considered:
        //   1. Pre-registered toolboxes (via AddFoundryToolboxes) — always appended.
        //   2. Per-request markers embedded in request.Tools (HostedMcpToolboxAITool)
        //      whose ServerAddress scheme is "foundry-toolbox://". Strict mode rejects
        //      unknown names; otherwise a lazy MCP client is opened and cached.
        //
        // Each toolbox's tools are only appended once per request, even if it appears
        // in both the pre-registered list and the per-request markers.
        if (this._toolboxService is not null)
        {
            List<AITool>? toolsToAdd = null;

            if (this._toolboxService.Tools.Count > 0)
            {
                toolsToAdd = [.. this._toolboxService.Tools];
            }

            var markers = InputConverter.ReadMcpToolboxMarkers(request);
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            string? resolutionError = null;

            foreach (var (name, version) in markers)
            {
                if (!seen.Add(name))
                {
                    continue;
                }

                IReadOnlyList<AITool>? toolboxTools = null;
                try
                {
                    toolboxTools = await this._toolboxService
                        .GetToolboxToolsAsync(name, version, cancellationToken)
                        .ConfigureAwait(false);
                }
                catch (InvalidOperationException ex)
                {
                    if (this._logger.IsEnabled(LogLevel.Warning))
                    {
                        this._logger.LogWarning(
                            ex,
                            "Foundry toolbox '{ToolboxName}' could not be resolved for response {ResponseId}.",
                            name,
                            context.ResponseId);
                    }

                    resolutionError = ex.Message;
                    break;
                }

                toolsToAdd ??= [];
                foreach (var t in toolboxTools)
                {
                    if (!toolsToAdd.Contains(t))
                    {
                        toolsToAdd.Add(t);
                    }
                }
            }

            if (resolutionError is not null)
            {
                yield return stream.EmitFailed(ResponseErrorCode.ServerError, resolutionError);
                yield break;
            }

            if (toolsToAdd?.Count > 0)
            {
                chatOptions.Tools = [.. chatOptions.Tools ?? [], .. toolsToAdd];
            }
        }

        var options = new ChatClientAgentRunOptions(chatOptions);

        // 6. Set up consent context for -32006 OAuth consent interception.
        //    We create a linked CTS so the consent-aware tool wrapper can cancel the agent
        //    run mid-loop when a -32006 error is returned by the proxy. The RequestConsentState
        //    is a shared mutable object that flows via AsyncLocal to the tool wrapper.
        using var consentCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        var consentState = new RequestConsentState { CancellationSource = consentCts };
        McpConsentContext.Current.Value = consentState;

        // 7. Run the agent and convert output
        // NOTE: C# forbids 'yield return' inside a try block that has a catch clause,
        // and inside catch blocks. We use a flag to defer the yield to outside the try/catch.
        bool emittedTerminal = false;
        var enumerator = OutputConverter.ConvertUpdatesToEventsAsync(
            agent.RunStreamingAsync(messages, session, options: options, cancellationToken: consentCts.Token),
            stream,
            cancellationToken).GetAsyncEnumerator(cancellationToken);
        try
        {
            while (true)
            {
                bool shutdownDetected = false;
                McpConsentInfo? consentInfo = null;
                ResponseStreamEvent? failedEvent = null;
                ResponseStreamEvent? evt = null;
                try
                {
                    if (!await enumerator.MoveNextAsync().ConfigureAwait(false))
                    {
                        break;
                    }

                    evt = enumerator.Current;
                }
                catch (OperationCanceledException) when (!emittedTerminal && consentState.Pending is not null)
                {
                    // -32006 consent error: the tool wrapper cancelled consentCts and stored consent info.
                    consentInfo = consentState.Pending;
                }
                catch (OperationCanceledException) when (context.IsShutdownRequested && !emittedTerminal)
                {
                    shutdownDetected = true;
                }
                catch (Exception ex) when (ex is not OperationCanceledException && !emittedTerminal)
                {
                    // Catch agent execution errors and emit a proper failed event
                    // with the real error message instead of letting the SDK emit
                    // a generic "An internal server error occurred."
                    if (this._logger.IsEnabled(LogLevel.Error))
                    {
                        this._logger.LogError(ex, "Agent execution failed for response {ResponseId}.", context.ResponseId);
                    }

                    failedEvent = stream.EmitFailed(
                        ResponseErrorCode.ServerError,
                        ex.Message);
                }

                if (consentInfo is not null)
                {
                    // Emit mcp_approval_request output item + incomplete for the consent URL.
                    foreach (var approvalEvent in stream.OutputItemMcpApprovalRequest(
                        consentInfo.ToolboxName,
                        consentInfo.ToolName,
                        consentInfo.ConsentUrl))
                    {
                        yield return approvalEvent;
                    }

                    yield return stream.EmitIncomplete(reason: null);
                    yield break;
                }

                if (failedEvent is not null)
                {
                    yield return failedEvent;
                    yield break;
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

            // Persist session after streaming completes (successful or not)
            if (session is not null && !string.IsNullOrWhiteSpace(sessionConversationId))
            {
                await sessionStore.SaveSessionAsync(agent, sessionConversationId, session, cancellationToken).ConfigureAwait(false);
            }
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
                return FoundryHostingExtensions.ApplyOpenTelemetry(agent);
            }

            if (this._logger.IsEnabled(LogLevel.Warning))
            {
                this._logger.LogWarning("Agent '{AgentName}' not found in keyed services. Attempting default resolution.", agentName);
            }
        }

        // Try non-keyed default
        var defaultAgent = this._serviceProvider.GetService<AIAgent>();
        if (defaultAgent is not null)
        {
            return FoundryHostingExtensions.ApplyOpenTelemetry(defaultAgent);
        }

        var errorMessage = string.IsNullOrEmpty(agentName)
            ? "No agent name specified in the request (via agent.name or metadata[\"entity_id\"]) and no default AIAgent is registered."
            : $"Agent '{agentName}' not found. Ensure it is registered via AddAIAgent(\"{agentName}\", ...) or as a default AIAgent.";

        throw new InvalidOperationException(errorMessage);
    }

    /// <summary>
    /// Resolves an <see cref="AIAgent"/> from the request.
    /// Tries <c>agent.name</c> first, then falls back to <c>metadata["entity_id"]</c>.
    /// If neither is present, attempts to resolve a default (non-keyed) <see cref="AIAgent"/>.
    /// </summary>
    private AgentSessionStore ResolveSessionStore(CreateResponse request)
    {
        var agentName = GetAgentName(request);

        if (!string.IsNullOrEmpty(agentName))
        {
            var sessionStore = this._serviceProvider.GetKeyedService<AgentSessionStore>(agentName);
            if (sessionStore is not null)
            {
                return sessionStore;
            }

            if (this._logger.IsEnabled(LogLevel.Warning))
            {
                this._logger.LogWarning("SessionStore for agent '{AgentName}' not found in keyed services. Attempting default resolution.", agentName);
            }
        }

        // Try non-keyed default
        var defaultSessionStore = this._serviceProvider.GetService<AgentSessionStore>();
        if (defaultSessionStore is not null)
        {
            return defaultSessionStore;
        }

        var errorMessage = string.IsNullOrEmpty(agentName)
            ? "No agent name specified in the request (via agent.name or metadata[\"entity_id\"]) and no default AgentSessionStore is registered."
            : $"Agent '{agentName}' not found. Ensure it is registered via AddAIAgent(\"{agentName}\", ...) or as a default AgentSessionStore.";

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
