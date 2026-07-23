// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
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
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public class AgentFrameworkResponseHandler : ResponseHandler
{
    private readonly IServiceProvider _serviceProvider;
    private readonly ILogger<AgentFrameworkResponseHandler> _logger;
    private readonly FoundryToolboxService? _toolboxService;

    /// <summary>
    /// Cached fallback used when no <see cref="HostedSessionIsolationKeyProvider"/> is registered in DI.
    /// Avoids a per-request allocation on the request hot path.
    /// </summary>
    private static readonly HostedSessionIsolationKeyProvider s_defaultIsolationKeyProvider = new PlatformHostedSessionIsolationKeyProvider();

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

        // Fail fast with a clear, actionable error when this 2.0.0-only image is served container
        // protocol 1.0.0. The x-agent-foundry-call-id header is exclusive to protocol 2.0.0, so when the
        // container is hosted by Foundry yet receives no call id, the platform is talking 1.0.0 to an
        // image that does not support it. Detecting this here turns an opaque 500 into a 501 that names
        // the cause and the fix instead of bubbling up as a generic server error on every request.
        var unsupportedProtocolError = HostedProtocolCompatibility.GetUnsupportedProtocolError(
            FoundryEnvironment.IsHosted, context.PlatformContext?.CallId);
        if (unsupportedProtocolError is not null)
        {
            this._logger.LogError(
                "Hosted container served unsupported Responses protocol 1.0.0 (no x-agent-foundry-call-id header); this image requires protocol 2.0.0.");
            throw unsupportedProtocolError;
        }

        // 2. Resolve the per-request hosted session identity context, so the session can be
        // loaded from a per-user partition. Fresh sessions are tagged once; resumed sessions are
        // validated against the live request to detect cross-user session leaks and in-process tampering.
        var isolationKeyProvider = this._serviceProvider.GetService<HostedSessionIsolationKeyProvider>()
            ?? s_defaultIsolationKeyProvider;
        var resolvedHostedContext = await isolationKeyProvider.GetKeysAsync(context, request, cancellationToken).ConfigureAwait(false);
        if (resolvedHostedContext is null && FoundryEnvironment.IsHosted)
        {
            // Hosted by Foundry yet the provider produced no user identity. Protocol 1.0.0 (no call id)
            // was already turned into a clear 501 above, so this is the unexpected case of a 2.0.0
            // request that carried a call id but no x-agent-user-id, or a custom provider that returned
            // null in production. Reject rather than silently persist an unscoped, cross-user session.
            throw new InvalidOperationException(
                $"The registered {nameof(HostedSessionIsolationKeyProvider)} returned null for the current request. " +
                "Ensure the Foundry platform is providing the x-agent-user-id header, " +
                "or register a custom provider that supplies fallback values for local development.");
        }

        // When resolvedHostedContext is null here the container is NOT hosted by Foundry (local
        // development: docker run / dotnet run outside the platform, so no x-agent-user-id header).
        // Per-user isolation simply does not apply in that case: the request proceeds with a null user
        // id (the session store treats null as "no user partition") and no hosted context is stamped or
        // validated. This lets contributors run the image locally without registering a fallback
        // provider, while production stays strict because FoundryEnvironment.IsHosted is true there.
        var resolvedUserId = resolvedHostedContext?.UserId;

        // 3. Load or create a new session from the interaction.
        // Map the request to a stable MAF AgentSession key: conversation_id when present, else the
        // partition embedded in previous_response_id (chains converge), else the minted response id
        // (cold start). Container session id is intentionally not used — it spans many conversations.
        // The session store partitions persisted state per user via resolvedUserId so one user can
        // never observe another user's session, even with a forged conversation id. Locally
        // (resolvedUserId is null) there is no user to partition on, so the session is unscoped/shared
        // by design — per-user isolation applies only when a user identity was resolved (hosted).
        var conversationId = request.GetConversationId();
        var sessionConversationId = HostedConversationKey.Resolve(
            conversationId, request.PreviousResponseId, context.ResponseId);

        var chatClientAgent = agent.GetService<ChatClientAgent>();

        AgentSession? session = !string.IsNullOrWhiteSpace(sessionConversationId)
            ? await sessionStore.GetSessionAsync(agent, sessionConversationId, resolvedUserId, cancellationToken).ConfigureAwait(false)
                : chatClientAgent is not null
                ? await chatClientAgent.CreateSessionAsync(cancellationToken).ConfigureAwait(false)
                : await agent.CreateSessionAsync(cancellationToken).ConfigureAwait(false);

        // Capture the platform per-request call id (x-agent-foundry-call-id, protocol 2.0.0 only).
        // It is re-applied to the ambient HostedCallContext immediately before each outbound egress
        // point below: AsyncLocal writes made in this streaming iterator are reverted across yield
        // boundaries, so a single up-front assignment would be lost before the toolbox/MCP calls run.
        var platformCallId = context.PlatformContext?.CallId;
        HostedCallContext.CallId = platformCallId;

        // Stamp/validate the hosted identity only when one was resolved. Locally (non-hosted) there is
        // no user identity, so there is nothing to partition or tamper-check and the session is shared.
        if (session is not null && resolvedHostedContext is not null)
        {
            var existingHostedContext = session.GetHostedContext();
            if (existingHostedContext is null)
            {
                // Fresh path: the session has no hosted context yet (either freshly created here,
                // or freshly loaded for a conversation_id that the platform supplied without any
                // prior hosted-agent request having stamped a context). Stamp it now.
                session.SetHostedContext(resolvedHostedContext);
            }
            else if (!string.Equals(existingHostedContext.UserId, resolvedHostedContext.UserId, StringComparison.Ordinal))
            {
                // Resume path: the persisted identity must match the live request. A mismatch
                // signals either a cross-user session leak or in-process tampering of the
                // persisted identity. Reject the request hard.
                throw new ResponsesApiException(
                    new Error("hosted_session_identity_mismatch", "Hosted session identity context mismatch"),
                    403);
            }
        }

        // 3. Create the SDK event stream builder
        var stream = new ResponseEventStream(context, request);

        // 3. Emit lifecycle events
        yield return stream.EmitCreated();
        yield return stream.EmitInProgress();

        // 4. Convert input: history + current input → ChatMessage[]
        var messages = new List<ChatMessage>();

        // Load conversation history only for fresh sessions. When a session already exists
        // (e.g. resuming a workflow paused at an external-input port), the workflow's
        // checkpointed state already contains the prior turns' messages — replaying history
        // would re-drive completed actions and break HITL resume semantics.
        var isResume = (!string.IsNullOrWhiteSpace(conversationId) || !string.IsNullOrWhiteSpace(request.PreviousResponseId))
            && session?.StateBag?.Count > 0;
        if (!isResume)
        {
            var history = await context.GetHistoryAsync(cancellationToken).ConfigureAwait(false);
            if (history.Count > 0)
            {
                messages.AddRange(InputConverter.ConvertOutputItemsToMessages(history, session?.StateBag));
            }
        }

        // Load and convert current input items
        var inputItems = await context.GetInputItemsAsync(cancellationToken: cancellationToken).ConfigureAwait(false);
        if (inputItems.Count > 0)
        {
            messages.AddRange(InputConverter.ConvertItemsToMessages(inputItems, session?.StateBag));
        }
        else
        {
            // Fall back to raw request input
            messages.AddRange(InputConverter.ConvertInputToMessages(request, session?.StateBag));
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
            // Re-apply the call id: the EmitCreated/EmitInProgress yields above reverted the ambient
            // value, and the toolbox tools/list + consent egress below must carry it per request.
            HostedCallContext.CallId = platformCallId;

            // Retry any pre-registered toolbox that was deferred at startup because it could not be
            // enumerated without a per-user context (non-consent failure). The request's egress now
            // carries the platform-injected per-user isolation key, so a delegated tool source can
            // enumerate as the user — or report that it needs OAuth consent, which is then surfaced
            // by ResolvePendingConsentsAsync below.
            await this._toolboxService
                .RetryDeferredToolboxesAsync(cancellationToken)
                .ConfigureAwait(false);

            // Resolve any pre-registered toolbox that was awaiting user OAuth consent at startup
            // (CONSENT_REQUIRED at tools/list time). If consent is still outstanding, surface it to
            // the caller as an oauth_consent_request and stop: the user completes consent out of band,
            // then re-sends the request, at which point enumeration succeeds and the tools appear.
            var pendingConsents = await this._toolboxService
                .ResolvePendingConsentsAsync(cancellationToken)
                .ConfigureAwait(false);
            if (pendingConsents.Count > 0)
            {
                foreach (var consent in pendingConsents)
                {
                    foreach (var consentEvent in EmitOAuthConsentRequest(
                        stream,
                        consent.ToolName,
                        consent.ConsentUrl))
                    {
                        yield return consentEvent;
                    }
                }

                yield return stream.EmitIncomplete(reason: null);
                yield break;
            }

            List<AITool>? toolsToAdd = null;

            if (this._toolboxService.Tools.Count > 0)
            {
                toolsToAdd = [.. this._toolboxService.Tools];
            }

            var markers = InputConverter.ReadMcpToolboxMarkers(request);
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            string? resolutionError = null;
            List<McpConsentInfo>? markerConsents = null;

            foreach (var (name, version) in markers)
            {
                if (!seen.Add(name))
                {
                    continue;
                }

                FoundryToolboxService.ToolboxResolution resolution;
                try
                {
                    resolution = await this._toolboxService
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

                // The marker hit CONSENT_REQUIRED: collect its consent requirement (request-scoped)
                // and keep resolving the other markers so we can surface every outstanding consent at
                // once. This toolbox contributes no tools to this turn.
                if (resolution.Consents.Count > 0)
                {
                    (markerConsents ??= []).AddRange(resolution.Consents);
                    continue;
                }

                toolsToAdd ??= [];
                foreach (var t in resolution.Tools)
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

            // A lazy / per-request marker that needs OAuth consent is surfaced as an
            // oauth_consent_request and stops this turn, instead of silently running without that
            // toolbox. The consent is scoped to this request (it was returned by GetToolboxToolsAsync,
            // not recorded globally), so it cannot leak onto a request that did not reference the marker.
            if (markerConsents is { Count: > 0 })
            {
                foreach (var consent in markerConsents)
                {
                    foreach (var consentEvent in EmitOAuthConsentRequest(
                        stream,
                        consent.ToolName,
                        consent.ConsentUrl))
                    {
                        yield return consentEvent;
                    }
                }

                yield return stream.EmitIncomplete(reason: null);
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
            session?.StateBag,
            cancellationToken).GetAsyncEnumerator(cancellationToken);
        try
        {
            while (true)
            {
                // Re-apply the call id before each pull from the agent stream: the per-event yields
                // below revert the ambient AsyncLocal, but the MCP tools/call egress that happens
                // inside MoveNextAsync must carry the platform call id on every request.
                HostedCallContext.CallId = platformCallId;

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
                    // Emit oauth_consent_request output item + incomplete for the consent URL.
                    foreach (var consentEvent in EmitOAuthConsentRequest(
                        stream,
                        consentInfo.ToolName,
                        consentInfo.ConsentUrl))
                    {
                        yield return consentEvent;
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

            // Persist session after streaming completes (successful or not). The user id partitions the
            // persisted session per end user, mirroring the load above so multi-turn continuity is preserved.
            if (session is not null && !string.IsNullOrWhiteSpace(sessionConversationId))
            {
                await sessionStore.SaveSessionAsync(agent, sessionConversationId, session, resolvedUserId, cancellationToken).ConfigureAwait(false);
            }
        }
    }

    /// <summary>
    /// Emits an <c>oauth_consent_request</c> output item (<c>output_item.added</c> →
    /// <c>output_item.done</c>) carrying the toolbox OAuth consent link.
    /// </summary>
    /// <remarks>
    /// This is the canonical platform surface for a per-user OAuth/toolbox consent prompt: the
    /// Foundry platform heads (Bot/Teams, A2A) natively render an <see cref="OAuthConsentRequestOutputItem"/>
    /// as an "open consent link + resume" experience, and the item round-trips through history. It is
    /// distinct from <c>mcp_approval_request</c>, which is the generic approve/deny tool gate that
    /// expects an approval response. OAuth consent needs no reply: the user signs in out of band and
    /// re-sends the request. This mirrors the Python <c>oauth_consent_request</c> emission for parity.
    /// </remarks>
    /// <param name="stream">The response event stream to emit on.</param>
    /// <param name="serverLabel">The tool source / server label that requires consent.</param>
    /// <param name="consentUrl">The OAuth consent URL the user must visit.</param>
    /// <returns>An enumerable of events: <c>output_item.added</c> → <c>output_item.done</c>.</returns>
    internal static IEnumerable<ResponseStreamEvent> EmitOAuthConsentRequest(
        ResponseEventStream stream,
        string serverLabel,
        string consentUrl)
    {
        var item = new OAuthConsentRequestOutputItem(NewOAuthConsentItemId(), consentUrl, serverLabel);
        var builder = stream.AddOutputItem<OAuthConsentRequestOutputItem>(item.Id);
        yield return builder.EmitAdded(item);
        yield return builder.EmitDone(item);
    }

    /// <summary>
    /// Generates a wire-format-valid item id for an <c>oauth_consent_request</c> output item.
    /// The Responses Server SDK requires ids of the shape <c>{prefix}_{50-char-body}</c>; we use the
    /// <c>oacr</c> prefix (matching the Python emission) with 25 random bytes rendered as 50 hex chars.
    /// </summary>
    private static string NewOAuthConsentItemId()
    {
        Span<byte> bytes = stackalloc byte[25];
        RandomNumberGenerator.Fill(bytes);
        return "oacr_" + Convert.ToHexString(bytes);
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
                FoundryHostingExtensions.TryApplyUserAgent(agent);
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
            FoundryHostingExtensions.TryApplyUserAgent(defaultAgent);
            return FoundryHostingExtensions.ApplyOpenTelemetry(defaultAgent);
        }

        var errorMessage = string.IsNullOrEmpty(agentName)
            ? "No agent name specified in the request (via agent.name or metadata[\"entity_id\"]) and no default AIAgent is registered."
            : $"Agent '{agentName}' not found. Ensure it is registered via AddFoundryResponses(services, agent) or services.AddKeyedSingleton<AIAgent>(\"{agentName}\", ...).";

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
            : $"AgentSessionStore for agent '{agentName}' not found. Ensure it is registered via AddFoundryResponses(services, agent, agentSessionStore) or services.AddKeyedSingleton<AgentSessionStore>(\"{agentName}\", ...).";

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
