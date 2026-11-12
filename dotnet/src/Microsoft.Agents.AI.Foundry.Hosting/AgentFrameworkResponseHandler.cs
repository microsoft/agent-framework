// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;

// The terminal stream events are named the same in two namespaces this file pulls in, and the short
// name binds to the one the event objects are not. Naming them here keeps `is` checks against the
// types the response stream actually produces.
using ResponseCompletedEvent = Azure.AI.AgentServer.Responses.Models.ResponseCompletedEvent;
using ResponseFailedEvent = Azure.AI.AgentServer.Responses.Models.ResponseFailedEvent;
using ResponseIncompleteEvent = Azure.AI.AgentServer.Responses.Models.ResponseIncompleteEvent;
using ResponseOutputItemDoneEvent = Azure.AI.AgentServer.Responses.Models.ResponseOutputItemDoneEvent;

namespace Microsoft.Agents.AI.Foundry.Hosting;
#pragma warning disable SYSLIB1006 // Preserve the legacy EventId 0 for every migrated log message.

/// <summary>
/// A <see cref="ResponseHandler"/> implementation that bridges the Azure AI Responses Server SDK
/// with agent-framework <see cref="AIAgent"/> instances, enabling agent-framework agents and workflows
/// to be hosted as Azure Foundry Hosted Agents.
/// </summary>
internal sealed partial class AgentFrameworkResponseHandler : ResponseHandler
{
    private const string LatestWorkflowCheckpointIdMetadataKey = "_last_checkpoint_id";
    private const string UserPartitionName = "user";
    private const string ConsentLinkRejectedMessage = "The OAuth consent request was rejected by the consent link policy.";

    private readonly IServiceProvider _serviceProvider;
    private readonly FoundryHostedAgentSource _agentSource;
    private readonly ILogger<AgentFrameworkResponseHandler> _logger;
    private readonly FoundryResponsesServerOptions _options;
    private readonly FoundryToolboxService? _toolboxService;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentFrameworkResponseHandler"/> class
    /// that serves the agent supplied by <paramref name="agentSource"/>.
    /// </summary>
    /// <param name="serviceProvider">The service provider each response run creates its DI scope from.</param>
    /// <param name="agentSource">Supplies the agent this container serves.</param>
    /// <param name="logger">The logger instance.</param>
    public AgentFrameworkResponseHandler(
        IServiceProvider serviceProvider,
        FoundryHostedAgentSource agentSource,
        ILogger<AgentFrameworkResponseHandler> logger)
        : this(
            serviceProvider,
            agentSource,
            logger,
            new FoundryResponsesServerOptions())
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentFrameworkResponseHandler"/> class
    /// that serves the agent supplied by <paramref name="agentSource"/>.
    /// </summary>
    /// <param name="serviceProvider">The service provider each response run creates its DI scope from.</param>
    /// <param name="agentSource">Supplies the agent this container serves.</param>
    /// <param name="logger">The logger instance.</param>
    /// <param name="foundryResponsesOptions">
    /// Hosting options, used to read whether resilient background responses are enabled.
    /// </param>
    /// <param name="toolboxService">Optional Foundry Toolbox service providing MCP tools.</param>
    public AgentFrameworkResponseHandler(
        IServiceProvider serviceProvider,
        FoundryHostedAgentSource agentSource,
        ILogger<AgentFrameworkResponseHandler> logger,
        FoundryResponsesServerOptions foundryResponsesOptions,
        FoundryToolboxService? toolboxService = null)
    {
        _ = Throw.IfNull(serviceProvider);
        _ = Throw.IfNull(agentSource);
        _ = Throw.IfNull(logger);
        _ = Throw.IfNull(foundryResponsesOptions);

        this._serviceProvider = serviceProvider;
        this._agentSource = agentSource;
        this._logger = logger;
        this._options = foundryResponsesOptions;
        this._toolboxService = toolboxService;
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<ResponseStreamEvent> CreateAsync(
        CreateResponse request,
        ResponseContext context,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        // 1. Resolve the per-request hosted user identity, so the session can be
        // loaded from a per-user partition. Fresh sessions are tagged once; resumed sessions are
        // validated against the live request to detect cross-user session leaks and in-process tampering.
        // This runs before any agent or store is created, so a rejected request never invokes a
        // caller-supplied agent or session store factory.
        string? resolvedUserId = context.PlatformContext?.UserIdKey;
        if (string.IsNullOrWhiteSpace(resolvedUserId))
        {
            resolvedUserId = null;
        }

        if (resolvedUserId is null && FoundryEnvironment.IsHosted)
        {
            // Hosted by Foundry yet the provider produced no user identity. The endpoint filter
            // already rejected protocol 1.0.0, so this is the unexpected case of a 2.0.0
            // request that carried a call id but no x-agent-user-id. Reject rather than silently persist
            // an unscoped, cross-user session.
            throw new InvalidOperationException(
                "The Foundry platform did not provide a user identity for the current request. " +
                "Ensure the x-agent-user-id header is present.");
        }

        // 2. Get the agent and session store for a DI scope owned by this response run. The scope
        // covers the whole enumeration, not the HTTP request: background runs continue after the
        // HTTP response is sent, and recovery runs have no HTTP request at all. A scoped or transient
        // agent, and a scoped or transient session store, are therefore created per run and disposed
        // when the event stream ends. The container serves one agent, so the request does not select it.
        AsyncServiceScope serviceScope = this._serviceProvider.CreateAsyncScope();
        await using var configuredServiceScope = serviceScope.ConfigureAwait(false);
        IServiceProvider services = serviceScope.ServiceProvider;
        FoundryHostedAgentSource.Lease agentLease = this._agentSource.Acquire(services);
        await using var configuredAgentLease = agentLease.ConfigureAwait(false);
        AIAgent agent = this.PrepareAgent(agentLease.Agent);
        AgentSessionStore sessionStore = ResolveSessionStore(services);

        // When resolvedUserId is null here the container is NOT hosted by Foundry (local
        // development: docker run / dotnet run outside the platform, so no x-agent-user-id header).
        // Per-user isolation simply does not apply in that case: no user partition is added to the
        // session key and no hosted context is stamped or
        // validated. This lets contributors run the image locally without registering a fallback
        // provider, while production stays strict because FoundryEnvironment.IsHosted is true there.
        // 3. Load or create a new session from the interaction.
        // Map the request to a stable MAF AgentSession key: conversation_id when present, else the
        // partition embedded in previous_response_id (chains converge), else the minted response id
        // (cold start). Container session id is intentionally not used — it spans many conversations.
        // The session key partitions persisted state per user via resolvedUserId so one user can
        // never observe another user's session, even with a forged conversation id. Locally
        // (resolvedUserId is null) there is no user to partition on, so the session is unscoped/shared
        // by design — per-user isolation applies only when a user identity was resolved (hosted).
        var conversationId = request.GetConversationId();
        var agentSessionId = HostedConversationKey.Resolve(
            conversationId, request.PreviousResponseId, context.ResponseId);
        AgentSessionStoreKey? agentSessionKey = string.IsNullOrWhiteSpace(agentSessionId)
            ? null
            : new AgentSessionStoreKey(agentSessionId);
        if (agentSessionKey is not null && resolvedUserId is not null)
        {
            agentSessionKey = agentSessionKey.WithPartition(UserPartitionName, resolvedUserId);
        }

        var agentOptions = agent.GetService<ChatClientAgentOptions>();

        // Load the session for this conversation, or start a new one. The store returns null when
        // nothing is persisted for the key, so a fresh conversation and a resumed one both end up with
        // a session to run against.
        AgentSession? session;
        bool sessionRestoredFromStore = false;
        if (agentSessionKey is null)
        {
            session = await agent.CreateSessionAsync(cancellationToken).ConfigureAwait(false);
        }
        else
        {
            session = await sessionStore.GetSessionAsync(
                agent,
                agentSessionKey,
                cancellationToken).ConfigureAwait(false);

            sessionRestoredFromStore = session is not null;
            session ??= await agent.CreateSessionAsync(cancellationToken).ConfigureAwait(false);
        }

        // Every toolbox connection opened for this response belongs to this scope and ends with the response,
        // so no MCP session is shared with another response or caller. The scope binds each connection to the
        // platform per-request call id (x-agent-foundry-call-id, protocol 2.0.0 only), which the toolbox proxy
        // uses to resolve the caller.
        var toolboxRequestScope = this._toolboxService?.CreateRequestScope(context.PlatformContext?.CallId)
            ?? FoundryToolboxService.ToolboxRequestScope.CreateInactive();
        await using var configuredToolboxRequestScope = toolboxRequestScope.ConfigureAwait(false);

        // Stamp/validate the hosted identity only when one was resolved. Locally (non-hosted) there is
        // no user identity, so there is nothing to partition or tamper-check and the session is shared.
        if (session is not null && resolvedUserId is not null)
        {
            string? existingUserId = session.GetFoundryHostedUserId();
            if (existingUserId is null)
            {
                // Fresh path: the session has no hosted context yet (either freshly created here,
                // or freshly loaded for a conversation_id that the platform supplied without any
                // prior hosted-agent request having stamped a context). Stamp it now.
                session.SetHostedUserId(resolvedUserId);
            }
            else if (!string.Equals(existingUserId, resolvedUserId, StringComparison.Ordinal))
            {
                // Resume path: the persisted identity must match the live request. A mismatch
                // signals either a cross-user session leak or in-process tampering of the
                // persisted identity. Reject the request hard.
                throw new ResponsesApiException(
                    new Error("hosted_user_identity_mismatch", "Hosted user identity mismatch"),
                    403);
            }
        }

        // 3. Create the SDK event stream builder.
        // On recovery, AgentServer supplies the last ResponseObject snapshot that it persisted.
        // Workflow response checkpoints carry the exact workflow checkpoint id represented by that
        // snapshot, so recovery can select the matching workflow boundary rather than a newer
        // checkpoint that may already exist in workflow storage.
        var stream = context.IsRecovery && context.PersistedResponse is { } persistedResponse
            ? new ResponseEventStream(context, persistedResponse)
            : new ResponseEventStream(context, request);

        if (context.IsRecovery
            && sessionRestoredFromStore
            && session?.GetService<WorkflowSessionCheckpointRecovery>()
                is { } workflowCheckpointRecovery)
        {
            string? checkpointId =
                stream.PersistedMetadata.TryGetValue(LatestWorkflowCheckpointIdMetadataKey, out string? persistedCheckpointId)
                && !string.IsNullOrWhiteSpace(persistedCheckpointId)
                    ? persistedCheckpointId
                    : null;

            // When metadata is absent, TryPrepare keeps the checkpoint already referenced by the
            // restored session. Either path continues queued work without starting a new turn.
            workflowCheckpointRecovery.TryPrepare(checkpointId);
        }

        // 3. Emit lifecycle events
        yield return stream.EmitCreated();
        yield return stream.EmitInProgress();

        // 4. Convert input: the current input items become the run's messages. Earlier turns are not
        // added here; whatever holds the history for this agent supplies them, see step 5.
        //
        // On recovery the platform re-delivers the original input. When a persisted AgentSession was
        // restored, this adapter leaves the message list empty and lets that session define re-entry.
        // If no session was ever saved, there is no resumable MAF state, so recovery restarts from the
        // original input instead of invoking a fresh session with no messages.
        bool shouldInjectRequestInput = !context.IsRecovery || !sessionRestoredFromStore;
        var messages = new List<ChatMessage>();
        if (shouldInjectRequestInput)
        {
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
        }

        // 5. Build chat options
        var chatOptions = InputConverter.ConvertToChatOptions(
            request,
            agentOptions?.ChatOptions?.RawRepresentationFactory,
            this._options);
        chatOptions.Instructions = request.Instructions;

        // A resilient turn defers to recovery when the host shuts down; any other turn ends incomplete.
        bool isResilientTurn = this.ShouldPersistForResilience(request) || context.IsRecovery;

        // Open the pre-registered Foundry toolboxes for this response when the toolbox service is available.
        if (this._toolboxService is not null)
        {
            // Opening toolboxes waits on the network before the agent runs, so it observes shutdown itself rather
            // than holding the response through the transport timeouts. A shutdown here ends the turn the same way
            // as one during the agent run below, before the agent or its session has advanced, so nothing is saved.
            ToolboxRequestResolution toolboxResolution = ToolboxRequestResolution.Empty;
            bool shutdownDuringToolboxOpen = false;
            using (var toolboxOpenCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, context.Shutdown))
            {
                try
                {
                    toolboxResolution = await toolboxRequestScope.ResolveAsync(toolboxOpenCts.Token).ConfigureAwait(false);
                }
                catch (OperationCanceledException) when (context.IsShutdownRequested)
                {
                    shutdownDuringToolboxOpen = true;
                }
            }

            if (shutdownDuringToolboxOpen)
            {
                if (isResilientTurn)
                {
                    LogShutdownDeferredForRecovery(this._logger);
                    await context.ExitForRecoveryAsync(cancellationToken).ConfigureAwait(false);
                    yield break;
                }

                LogShutdownEmittingIncomplete(this._logger);
                yield return stream.EmitIncomplete();
                yield break;
            }

            // A toolbox that needs this caller's OAuth consent stops the turn instead of silently running
            // without its tools: the user completes consent out of band, then re-sends the request.
            if (toolboxResolution.Consents.Count > 0)
            {
                foreach (var consentEvent in this.EmitConsentRequiredResponse(
                    stream,
                    toolboxResolution.Consents,
                    context.ResponseId))
                {
                    yield return consentEvent;
                }

                yield break;
            }

            if (toolboxResolution.Tools.Count > 0)
            {
                chatOptions.Tools = [.. chatOptions.Tools ?? [], .. toolboxResolution.Tools];
            }
        }

        if (this._options.InferenceStoredOutputAllowed &&
            agent.GetService<FunctionInvokingChatClient>() is { } functionInvokingClient)
        {
            // The FICC instance is shared, so install one AsyncLocal-aware gate rather than
            // replacing its invoker per request. It is a no-op outside a stored-output consent turn.
            ConsentBlockingFunctionInvoker.EnsureInstalled(functionInvokingClient);
        }

        var options = new ChatClientAgentRunOptions(chatOptions);

        // We only use a volatile provider for the conversation history if the agent is a
        // ChatClientAgent, stored output is not allowed, and no custom history provider was supplied.
        // Recovery does not reload platform history because the restored AgentSession owns re-entry
        // state. For workflows, that includes the workflow checkpoint reference.
        var useVolatileChatHistoryProvider =
            shouldInjectRequestInput
            && !this._options.InferenceStoredOutputAllowed
            && agent.GetService<ChatClientAgent>() is not null
            && agentOptions?.ChatHistoryProvider is null;

        // This will create a temporary in-memory provider for the conversation history, which will be dropped at the end of this run.
        // This is used to avoid storing the conversation history as the SDK will by default do the same via the (InMemory/Foundry)ResponsesProvider internal implementation.
        if (useVolatileChatHistoryProvider)
        {
            var history = await context.GetHistoryAsync(cancellationToken).ConfigureAwait(false);

            options.AdditionalProperties ??= [];
            options.AdditionalProperties.Add<ChatHistoryProvider>(
                new VolatileChatHistoryProvider(InputConverter.ConvertOutputItemsToMessages(history, session?.StateBag)));
        }

        // 6. Set up consent context for -32006 OAuth consent interception. When the downstream
        //    service stores its own history, FICC makes one final no-tools request to persist the
        //    complete result batch. Otherwise it terminates before that unnecessary request. A
        //    linked CTS supports agents invoking tools outside the loop, and the shared state flows
        //    via AsyncLocal to the tool wrapper and the request-aware FICC invoker.
        using var consentCts = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            context.Shutdown);
        var consentState = new RequestConsentState
        {
            CancellationSource = consentCts,
            ReconcileDownstreamHistory = this._options.InferenceStoredOutputAllowed,
            InterruptedToolResult = this._options.OAuthConsentInterruptedToolResult,
        };

        // 7. Run the agent and convert output
        // NOTE: C# forbids 'yield return' inside a try block that has a catch clause,
        // and inside catch blocks. We use a flag to defer the yield to outside the try/catch.
        //
        // On a resilient turn, save the AgentSession after completed response output items so a
        // process crash can reload a recent session snapshot. Workflow supersteps use a stronger
        // boundary below: save the session, record its workflow checkpoint id in internal response
        // metadata, then ask AgentServer to persist the matching ResponseObject snapshot.
        bool emittedTerminal = false;
        bool notAllowedStoreUsageDetected = false;

        // Set when this turn is being failed, so its session is not kept. A turn that ends incomplete,
        // waiting on OAuth consent or interrupted by a shutdown, is not a failure: the caller comes back
        // for it and needs the state that was built up, the tool approval ids among it.
        bool turnFailed = false;

        // A successful terminal event, held until the run is wound up and the session can be checked.
        ResponseStreamEvent? completedEvent = null;
        bool steeringDetected = false;
        bool deferredForRecovery = false;

        var enumerator = OutputConverter.ConvertUpdatesToItemsAsync(
            agent.RunStreamingAsync(messages, session, options: options, cancellationToken: consentCts.Token),
            stream,
            session?.StateBag,
            cancellationToken: cancellationToken).GetAsyncEnumerator(cancellationToken);
        var pendingEvents = new Queue<ResponseStreamEvent>();
        try
        {
            while (true)
            {
                bool shutdownDetected = false;
                IReadOnlyList<McpConsentInfo>? pendingConsents = null;
                ResponseStreamEvent? failedEvent = null;
                ResponseStreamEvent? evt = null;
                try
                {
                    if (!pendingEvents.TryDequeue(out evt))
                    {
                        // AsyncLocal assignments do not survive iterator yields. Bind the same
                        // consent state on every advance without replacing the caller's context.
                        var previousConsentState = McpConsentContext.Current.Value;
                        try
                        {
                            McpConsentContext.Current.Value = consentState;
                            if (!await enumerator.MoveNextAsync().ConfigureAwait(false))
                            {
                                break;
                            }
                        }
                        finally
                        {
                            McpConsentContext.Current.Value = previousConsentState;
                        }

                        switch (enumerator.Current)
                        {
                            case OutputConverterItem.ResponseEvent responseEvent:
                                evt = responseEvent.Event;
                                break;

                            case OutputConverterItem.WorkflowCheckpoint workflowCheckpoint:
                                ResponseStreamEvent? checkpointStateEvent =
                                    await PersistWorkflowCheckpointAsync(
                                        workflowCheckpoint.Checkpoint,
                                        cancellationToken).ConfigureAwait(false);

                                if (checkpointStateEvent is not null)
                                {
                                    // AgentServer persists its orchestrator-owned response snapshot.
                                    // Apply the updated internal metadata first, then request persistence.
                                    pendingEvents.Enqueue(checkpointStateEvent);
                                    pendingEvents.Enqueue(stream.CreateCheckpointEvent());
                                }

                                continue;

                            default:
                                throw new InvalidOperationException(
                                    "The output converter returned an unsupported item.");
                        }
                    }

                    if (evt is ResponseCompletedEvent)
                    {
                        consentCts.Token.ThrowIfCancellationRequested();
                        var consents = consentState.GetPendingConsents();
                        pendingConsents = consents.Length > 0 ? consents : null;
                    }

                    shutdownDetected =
                        context.IsShutdownRequested && !emittedTerminal;
                }
                catch (OperationCanceledException) when (!emittedTerminal && consentState.HasPendingConsents)
                {
                    // -32006 consent error: the tool wrapper cancelled consentCts and stored consent info.
                    pendingConsents = consentState.GetPendingConsents();
                }
                catch (OperationCanceledException) when (context.IsShutdownRequested && !emittedTerminal)
                {
                    shutdownDetected = true;
                }
                catch (OperationCanceledException) when (context.PendingInputCount > 0 && !emittedTerminal)
                {
                    steeringDetected = true;
                }
                catch (Exception ex) when (ex is not OperationCanceledException && !emittedTerminal)
                {
                    // Catch agent execution errors and emit a proper failed event
                    // with the real error message instead of letting the SDK emit
                    // a generic "An internal server error occurred."
                    LogAgentExecutionFailed(this._logger, context.ResponseId, ex);

                    failedEvent = stream.EmitFailed(
                        ResponseErrorCode.ServerError,
                        ex.Message);
                }

                if (pendingConsents is not null)
                {
                    if (evt is ResponseCompletedEvent completed)
                    {
                        foreach (var skippedResultEvent in EmitConsentInterruptedToolResults(
                            stream,
                            completed.Response.Output,
                            consentState.InterruptedToolResult))
                        {
                            yield return skippedResultEvent;
                        }
                    }

                    // The loop has recorded the consent-required result and stopped before another
                    // model request. Add explicit results for every remaining call, then emit all
                    // consent requirements. A rejected link fails the turn without exposing it.
                    foreach (var consentEvent in this.EmitConsentRequiredResponse(
                        stream,
                        pendingConsents,
                        context.ResponseId))
                    {
                        // Mark the failure before yielding it, so the finally block below does not keep
                        // the session even when the caller stops reading at the failed event.
                        turnFailed |= consentEvent is ResponseFailedEvent;
                        yield return consentEvent;
                    }

                    yield break;
                }

                if (failedEvent is not null)
                {
                    // The run may have failed precisely because the agent stored the turn: the session
                    // picks up that conversation id before the agent goes on to complain about having
                    // two history managers. Report the cause rather than the symptom.
                    if (CheckNotAllowedStoreUsage())
                    {
                        notAllowedStoreUsageDetected = true;
                        turnFailed = true;
                        throw HostedStoredOutputCompatibility.CreateMisconfiguredAgentError();
                    }

                    turnFailed = true;
                    yield return failedEvent;
                    yield break;
                }

                if (shutdownDetected)
                {
                    // Server is shutting down. On a resilient turn, leave the response in_progress
                    // so AgentServer can re-invoke this handler in a later process. The restored
                    // AgentSession determines how the agent continues. On a non-resilient turn,
                    // preserve the existing behavior and emit incomplete.
                    if (isResilientTurn)
                    {
                        LogShutdownDeferredForRecovery(this._logger);
                        deferredForRecovery = true;
                        await context.ExitForRecoveryAsync(cancellationToken).ConfigureAwait(false);
                        yield break;
                    }

                    LogShutdownEmittingIncomplete(this._logger);
                    yield return stream.EmitIncomplete();
                    yield break;
                }

                if (steeringDetected)
                {
                    // AgentServer cancelled this active turn because another input is queued for the
                    // same conversation. Finish the current response cleanly so Core can drain the
                    // queued input as a new handler invocation. The MAF AgentSession is saved in the
                    // outer finally block and becomes the starting state for that invocation.
                    LogSteeringInputDetected(this._logger, context.ResponseId);
                    emittedTerminal = true;
                    yield return stream.EmitCompleted();
                    yield break;
                }

                // A completed event is held back rather than sent straight out. The id of any
                // conversation the agent's own service kept only lands on the session once the run is
                // fully wound up, which is after this point, so sending the event now could tell the
                // caller the turn finished and then hand them a failure for the very same turn.
                if (evt is ResponseCompletedEvent)
                {
                    completedEvent = evt;
                    emittedTerminal = true;
                    continue;
                }

                // Emit the output boundary before saving the matching MAF session. AgentServer
                // persists the event while this iterator is suspended. Reversing this order could
                // advance the session past output that the caller never received. A crash after the
                // event but before the save can replay work, which is the deliberate at-least-once
                // side of this cross-store boundary.
                // yield is in the outer try (finally-only) — allowed by C#
                yield return evt!;

                // Best-effort session snapshot for a non-workflow agent after a response output item
                // closes. Workflow agents save only at the paired superstep boundary so their session
                // cursor cannot advance independently of the response snapshot. The final save below
                // remains authoritative for a turn that reaches normal completion.
                if (isResilientTurn
                    && evt is ResponseOutputItemDoneEvent
                    && session is not null
                    && session.GetService<WorkflowSessionCheckpointRecovery>() is null
                    && agentSessionKey is not null
                    && !turnFailed)
                {
                    try
                    {
                        await sessionStore.SaveSessionAsync(agent, agentSessionKey, session, cancellationToken).ConfigureAwait(false);
                    }
                    catch (Exception ex) when (ex is not OperationCanceledException)
                    {
                        LogIncrementalSessionSaveSkipped(this._logger, context.ResponseId, ex);
                    }
                }

                if (evt is ResponseFailedEvent or ResponseIncompleteEvent)
                {
                    emittedTerminal = true;
                }
            }
        }
        finally
        {
            var previousConsentState = McpConsentContext.Current.Value;
            try
            {
                McpConsentContext.Current.Value = consentState;
                await enumerator.DisposeAsync().ConfigureAwait(false);
            }
            finally
            {
                McpConsentContext.Current.Value = previousConsentState;
            }

            // Only after the the agent ran when can check precisely if the session had been used to store messages in the backend for validation.
            if (CheckNotAllowedStoreUsage())
            {
                notAllowedStoreUsageDetected = true;
                turnFailed = true;
            }

            // Persist the session for the next turn unless this turn failed or deferred after the
            // agent advanced beyond the last event emitted to AgentServer.
            if (session is not null && !turnFailed && !deferredForRecovery)
            {
                await sessionStore.SaveSessionAsync(
                    agent,
                    agentSessionKey!,
                    session,
                    steeringDetected ? CancellationToken.None : cancellationToken).ConfigureAwait(false);
            }
        }

        if (notAllowedStoreUsageDetected)
        {
            LogServerSideStorageNotAllowed(this._logger, agent.Name);

            throw HostedStoredOutputCompatibility.CreateMisconfiguredAgentError();
        }

        if (completedEvent is not null)
        {
            yield return completedEvent;
        }

        async ValueTask<ResponseStreamEvent?> PersistWorkflowCheckpointAsync(
            CheckpointInfo checkpoint,
            CancellationToken checkpointCancellationToken)
        {
            if (!isResilientTurn
                || session is null
                || session.GetService<WorkflowSessionCheckpointRecovery>() is null
                || agentSessionKey is null
                || (stream.PersistedMetadata.TryGetValue(LatestWorkflowCheckpointIdMetadataKey, out string? lastCheckpointId)
                    && string.Equals(lastCheckpointId, checkpoint.CheckpointId, StringComparison.Ordinal)))
            {
                return null;
            }

            try
            {
                await sessionStore.SaveSessionAsync(
                    agent,
                    agentSessionKey,
                    session,
                    checkpointCancellationToken).ConfigureAwait(false);
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                LogWorkflowCheckpointNotPaired(
                    this._logger,
                    checkpoint.CheckpointId,
                    context.ResponseId,
                    ex);

                return null;
            }

            stream.PersistedMetadata[LatestWorkflowCheckpointIdMetadataKey] = checkpoint.CheckpointId;
            return stream.EmitInProgress();
        }

        // A per-service-call history provider uses a local marker in ConversationId to keep
        // function invocation working; only a real service conversation indicates stored output.
        bool CheckNotAllowedStoreUsage() =>
            !this._options.InferenceStoredOutputAllowed
            && session is ChatClientAgentSession { ConversationId: not null } chatSession
            && !string.Equals(
                chatSession.ConversationId,
                PerServiceCallChatHistoryPersistingChatClient.LocalHistoryConversationId,
                StringComparison.Ordinal);
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
    /// <param name="consentLinkPolicy">
    /// The consent link policy to enforce. When <see langword="null"/>, <see cref="OAuthConsentLinkPolicy.UnrestrictedOrigin"/>
    /// is used, so the link must still pass absolute HTTPS URL validation.
    /// </param>
    /// <returns>An enumerable of events: <c>output_item.added</c> → <c>output_item.done</c>.</returns>
    /// <exception cref="InvalidOperationException">The consent link does not satisfy the policy.</exception>
    internal static IEnumerable<ResponseStreamEvent> EmitOAuthConsentRequest(
        ResponseEventStream stream,
        string serverLabel,
        string consentUrl,
        OAuthConsentLinkPolicy? consentLinkPolicy = null)
    {
        // Callers validate first so they can fail the response cleanly; this is the last line of
        // defense and never skips validation, even when no policy is supplied.
        if (!(consentLinkPolicy ?? OAuthConsentLinkPolicy.UnrestrictedOrigin).IsAllowed(consentUrl))
        {
            throw new InvalidOperationException(ConsentLinkRejectedMessage);
        }

        var item = new OAuthConsentRequestOutputItem(NewOAuthConsentItemId(), consentUrl, serverLabel);
        var builder = stream.AddOutputItem<OAuthConsentRequestOutputItem>(item.Id);
        yield return builder.EmitAdded(item);
        yield return builder.EmitDone(item);
    }

    /// <summary>
    /// Emits the terminal events for a turn that stops on OAuth consent: one <c>oauth_consent_request</c>
    /// item per consent, then <c>response.incomplete</c>.
    /// </summary>
    /// <remarks>
    /// When any consent link fails the consent link policy, only <c>response.failed</c> is emitted, so
    /// no link from that turn is surfaced. Every later response opens the toolbox again, so it discovers
    /// the tools once the caller has consented.
    /// </remarks>
    private IEnumerable<ResponseStreamEvent> EmitConsentRequiredResponse(
        ResponseEventStream stream,
        IReadOnlyList<McpConsentInfo> consents,
        string responseId)
    {
        if (!this.AreConsentLinksAllowed(consents, responseId))
        {
            yield return stream.EmitFailed(ResponseErrorCode.ServerError, ConsentLinkRejectedMessage);
            yield break;
        }

        foreach (var consent in consents)
        {
            foreach (var consentEvent in EmitOAuthConsentRequest(
                stream,
                consent.ToolName,
                consent.ConsentUrl,
                this._toolboxService?.ConsentLinkPolicy))
            {
                yield return consentEvent;
            }
        }

        yield return stream.EmitIncomplete(reason: null);
    }

    /// <summary>
    /// Emits explicit not-executed results for function calls left unmatched when OAuth consent
    /// terminates a sequential function batch.
    /// </summary>
    private static IEnumerable<ResponseStreamEvent> EmitConsentInterruptedToolResults(
        ResponseEventStream stream,
        IList<OutputItem> output,
        string interruptedToolResult)
    {
        HashSet<string>? completedCallIds = null;
        foreach (var result in output.OfType<OutputItemFunctionToolCallOutput>())
        {
            (completedCallIds ??= new(StringComparer.Ordinal)).Add(result.CallId);
        }

        List<string>? missingCallIds = null;
        foreach (var item in output)
        {
            if (item is OutputItemFunctionToolCall call &&
                completedCallIds?.Contains(call.CallId) is not true)
            {
                (missingCallIds ??= []).Add(call.CallId);
            }
        }

        if (missingCallIds is null)
        {
            yield break;
        }

        foreach (var callId in missingCallIds)
        {
            foreach (var evt in stream.OutputItemFunctionCallOutput(
                callId,
                BinaryData.FromString(OutputConverter.EncodeFunctionResultAsJsonStringPayload(interruptedToolResult))))
            {
                yield return evt;
            }
        }
    }

    /// <summary>
    /// Returns whether every consent link satisfies the toolbox consent link policy. Rejected links are
    /// logged by tool and toolbox name only; the URL is not logged because it comes from an external
    /// error payload.
    /// </summary>
    private bool AreConsentLinksAllowed(IEnumerable<McpConsentInfo> consents, string responseId)
    {
        var policy = this._toolboxService?.ConsentLinkPolicy ?? OAuthConsentLinkPolicy.UnrestrictedOrigin;
        foreach (var consent in consents)
        {
            if (!policy.IsAllowed(consent.ConsentUrl))
            {
                LogConsentLinkRejected(
                    this._logger,
                    consent.ToolName,
                    consent.ToolboxName,
                    responseId);

                return false;
            }
        }

        return true;
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
    /// The resilience gate for the mid-turn session-save path: saving is worthwhile only when the
    /// host enabled resilient background responses and this specific request is a background response
    /// that did not explicitly disable storage. A null <c>store</c> value means the Responses API
    /// default of true. When any part is false, the request runs exactly as it does on a non-resilient
    /// host (the recovery path is gated separately on <c>ResponseContext.IsRecovery</c>).
    /// </summary>
    private bool ShouldPersistForResilience(CreateResponse request)
        => this._options.ResilientBackground && request.Background == true && request.Store != false;

    /// <summary>
    /// Wraps the agent this container serves with what hosting adds to every run: the hosted-agent
    /// <c>User-Agent</c>, Foundry workflow checkpointing, its session storage identity, and telemetry.
    /// </summary>
    /// <param name="agent">The agent supplied by the agent source for the current run.</param>
    /// <returns>The agent to serve the run with.</returns>
    private AIAgent PrepareAgent(AIAgent agent)
    {
        ServiceCollectionExtensions.TryApplyUserAgent(agent);

        AIAgent prepared = ServiceCollectionExtensions.ApplyWorkflowCheckpointing(
            agent,
            this._serviceProvider.GetService<ILoggerFactory>());
        prepared = new FoundryHostingAgent(prepared, FoundryHostingAgent.ResolveSessionStorageIdentity(agent));

        return ServiceCollectionExtensions.ApplyOpenTelemetry(prepared);
    }

    /// <summary>
    /// Resolves the <see cref="AgentSessionStore"/> for the current run. <c>AddFoundryResponses</c> registers
    /// the default store unless the caller registered one, so this fails only for a handler built without it.
    /// </summary>
    /// <param name="services">The service provider of the DI scope owned by the current response run.</param>
    private static AgentSessionStore ResolveSessionStore(IServiceProvider services) =>
        services.GetService<AgentSessionStore>()
            ?? throw new InvalidOperationException(
                "No AgentSessionStore is registered. Register one with AddFoundryAgentSessionStore, or pass one to AddFoundryResponses.");

    [LoggerMessage(
        EventId = 0,
        Level = LogLevel.Error,
        Message = "Agent execution failed for response {ResponseId}.")]
    private static partial void LogAgentExecutionFailed(
        ILogger logger,
        string responseId,
        Exception exception);

    [LoggerMessage(LogLevel.Information, "Shutdown detected on a resilient turn; deferring for recovery.", EventId = 0)]
    private static partial void LogShutdownDeferredForRecovery(ILogger logger);

    [LoggerMessage(LogLevel.Information, "Shutdown detected, emitting incomplete response.", EventId = 0)]
    private static partial void LogShutdownEmittingIncomplete(ILogger logger);

    [LoggerMessage(LogLevel.Information, "Steering input detected for response {ResponseId}; completing the active turn.", EventId = 0)]
    private static partial void LogSteeringInputDetected(ILogger logger, string responseId);

    [LoggerMessage(LogLevel.Debug, "Incremental session save was skipped for response {ResponseId}; the end-of-turn save will persist the final state.", EventId = 0)]
    private static partial void LogIncrementalSessionSaveSkipped(
        ILogger logger,
        string responseId,
        Exception exception);

    [LoggerMessage(LogLevel.Error, "Agent '{AgentName}' should not have server side storage enabled. This produced a new untracked conversation/response in the server while the hosted agent also generated a conversation for the request of the agent.", EventId = 0)]
    private static partial void LogServerSideStorageNotAllowed(ILogger logger, string? agentName);

    [LoggerMessage(LogLevel.Debug, "Workflow checkpoint {CheckpointId} was not paired with response {ResponseId} because its AgentSession could not be saved.", EventId = 0)]
    private static partial void LogWorkflowCheckpointNotPaired(
        ILogger logger,
        string checkpointId,
        string responseId,
        Exception exception);

    [LoggerMessage(LogLevel.Warning, "OAuth consent request for tool '{ToolName}' in toolbox '{ToolboxName}' was rejected by the consent link policy for response {ResponseId}.", EventId = 0)]
    private static partial void LogConsentLinkRejected(
        ILogger logger,
        string toolName,
        string toolboxName,
        string responseId);
}
