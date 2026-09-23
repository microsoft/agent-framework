// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses;

/// <summary>
/// Executes a response after the endpoint-specific executor has selected an agent.
/// </summary>
internal static class AgentResponseExecution
{
    private const string SessionInitializedStateKey = "Microsoft.Agents.AI.Hosting.OpenAI.Responses.Initialized";
    private const string PendingApprovalRequestIdsStateKey = "Microsoft.Agents.AI.Hosting.OpenAI.Responses.PendingApprovalRequestIds";

    /// <summary>
    /// Validates that requests which resume an approval have server-side session storage available.
    /// </summary>
    public static ResponseError? ValidateSessionRequirements(CreateResponse request, bool hasSessionStore)
    {
        List<ItemContentFunctionApprovalResponse> approvalResponses = GetFunctionApprovalResponses(request);
        if (approvalResponses.Count == 0)
        {
            return null;
        }

        if (hasSessionStore)
        {
            return null;
        }

        // Approval responses are trusted only when matched to a request recorded by the server.
        // Without session storage, continuing would silently ignore the decision or trust caller data.
        return new ResponseError
        {
            Code = ResponseErrorCodes.InvalidRequest,
            Message = "Approval-required function calling is not supported because no AgentSessionStore is configured."
        };
    }

    /// <summary>
    /// Validates that every incoming approval response matches a request emitted for the restored session.
    /// </summary>
    public static async ValueTask<ResponseError?> ValidatePendingApprovalResponsesAsync(
        AIAgent agent,
        CreateResponse request,
        CancellationToken cancellationToken)
    {
        List<ItemContentFunctionApprovalResponse> approvalResponses = GetFunctionApprovalResponses(request);
        if (approvalResponses.Count == 0)
        {
            return null;
        }

        // ValidateSessionRequirements ensures approval responses reach this point only through an AIHostAgent.
        var hostAgent = (AIHostAgent)agent;
        string? sessionId = request.Conversation?.Id ?? request.PreviousResponseId;
        if (sessionId is null)
        {
            return InvalidApprovalRequest(approvalResponses[0].RequestId);
        }

        AgentSession session = await hostAgent.GetOrCreateSessionAsync(sessionId, cancellationToken).ConfigureAwait(false);
        session.StateBag.TryGetValue<List<string>>(PendingApprovalRequestIdsStateKey, out var pendingRequestIds);

        foreach (ItemContentFunctionApprovalResponse approvalResponse in approvalResponses)
        {
            if (pendingRequestIds?.Exists(
                requestId => string.Equals(requestId, approvalResponse.RequestId, StringComparison.Ordinal)) != true)
            {
                return InvalidApprovalRequest(approvalResponse.RequestId);
            }
        }

        return null;
    }

    /// <summary>
    /// Runs the selected agent and converts its updates to Responses API events.
    /// </summary>
    public static async IAsyncEnumerable<StreamingResponseEvent> ExecuteAsync(
        AIAgent agent,
        OpenAIResponsesMapOptions mapOptions,
        AgentInvocationContext context,
        CreateResponse request,
        IReadOnlyList<ChatMessage>? conversationHistory = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        // The hosting developer controls, via OpenAIResponsesMapOptions.RunOptionsFactory, which request
        // settings are mapped onto the agent run. By default no request setting is mapped.
        AgentRunOptions? options = mapOptions.RunOptionsFactory(request.ToRequestInfo());

        // A response ID identifies an immutable continuation snapshot. A conversation ID identifies the
        // mutable conversation head. A new response without either starts under its generated response ID.
        AIHostAgent? hostAgent = agent as AIHostAgent;
        if (hostAgent is not null && context.IsolationKey is not null)
        {
            // Background work cannot safely query IHttpContextAccessor after the request has ended. Bind the
            // session store to the trusted key captured by InMemoryResponsesService before detaching.
            hostAgent = hostAgent.BindIsolationKey(context.IsolationKey);
            agent = hostAgent;
        }

        AgentSession? session = null;
        bool includeConversationHistory = true;
        if (hostAgent is not null)
        {
            string sessionId = request.Conversation?.Id
                ?? request.PreviousResponseId
                ?? context.ResponseId;
            session = await hostAgent.GetOrCreateSessionAsync(sessionId, cancellationToken).ConfigureAwait(false);

            // A new agent session must be seeded from an existing conversation transcript. Once initialized,
            // the session owns both history and pending approvals, so replaying the transcript would duplicate
            // messages and could resubmit approval content that was already processed.
            includeConversationHistory = !session.StateBag.TryGetValue<string>(SessionInitializedStateKey, out _);
            session.StateBag.SetValue(SessionInitializedStateKey, bool.TrueString);
        }

        // Convert input to chat messages, prepending conversation history only when it is not already
        // represented by a restored agent session.
        var messages = new List<ChatMessage>();
        if (includeConversationHistory && conversationHistory is not null)
        {
            messages.AddRange(conversationHistory);
        }

        foreach (InputMessage inputMessage in request.Input.GetInputMessages())
        {
            messages.Add(inputMessage.ToChatMessage());
        }

        // Convert streaming agent updates to Responses API events. For persisted sessions, hold the
        // terminal event until the state has been saved. Otherwise a streaming client can immediately
        // continue the response before the approval checkpoint is available.
        StreamingResponseCompleted? completedEvent = null;
        List<string>? emittedApprovalRequestIds = null;
        await foreach (StreamingResponseEvent streamingEvent in agent.RunStreamingAsync(messages, session, options, cancellationToken)
            .ToStreamingResponseAsync(request, context, cancellationToken)
            .ConfigureAwait(false))
        {
            if (session is not null && streamingEvent is StreamingFunctionApprovalRequested approvalRequested)
            {
                (emittedApprovalRequestIds ??= []).Add(approvalRequested.RequestId);
            }

            if (hostAgent is not null && streamingEvent is StreamingResponseCompleted completed)
            {
                completedEvent = completed;
                continue;
            }

            yield return streamingEvent;
        }

        if (hostAgent is not null && session is not null)
        {
            UpdatePendingApprovalRequests(session, request, emittedApprovalRequestIds);

            // Response IDs are immutable snapshots and honor store=false. A conversation ID is a mutable
            // head and always advances after a successful turn.
            if (request.Store is not false)
            {
                await hostAgent.SaveSessionAsync(context.ResponseId, session, cancellationToken).ConfigureAwait(false);
            }

            if (request.Conversation?.Id is { } conversationId)
            {
                await hostAgent.SaveSessionAsync(conversationId, session, cancellationToken).ConfigureAwait(false);
            }
        }

        // Publish completion only after persistence so an immediate continuation can restore the session.
        if (completedEvent is not null)
        {
            yield return completedEvent;
        }
    }

    private static List<ItemContentFunctionApprovalResponse> GetFunctionApprovalResponses(CreateResponse request)
    {
        var approvalResponses = new List<ItemContentFunctionApprovalResponse>();
        foreach (InputMessage inputMessage in request.Input.GetInputMessages())
        {
            if (inputMessage.Content.Contents is not { } contents)
            {
                continue;
            }

            foreach (ItemContent content in contents)
            {
                if (content is ItemContentFunctionApprovalResponse approvalResponse)
                {
                    approvalResponses.Add(approvalResponse);
                }
            }
        }

        return approvalResponses;
    }

    private static void UpdatePendingApprovalRequests(
        AgentSession session,
        CreateResponse request,
        List<string>? emittedRequestIds)
    {
        session.StateBag.TryGetValue<List<string>>(PendingApprovalRequestIdsStateKey, out var pendingRequestIds);
        pendingRequestIds ??= [];

        // A successfully processed response consumes its matching request ID. New approval events are then
        // added so the saved session represents exactly the approvals the client can answer next.
        foreach (ItemContentFunctionApprovalResponse approvalResponse in GetFunctionApprovalResponses(request))
        {
            pendingRequestIds.RemoveAll(id => string.Equals(id, approvalResponse.RequestId, StringComparison.Ordinal));
        }

        if (emittedRequestIds is not null)
        {
            foreach (string requestId in emittedRequestIds)
            {
                if (!pendingRequestIds.Exists(id => string.Equals(id, requestId, StringComparison.Ordinal)))
                {
                    pendingRequestIds.Add(requestId);
                }
            }
        }

        if (pendingRequestIds.Count == 0)
        {
            session.StateBag.TryRemoveValue(PendingApprovalRequestIdsStateKey);
        }
        else
        {
            session.StateBag.SetValue(PendingApprovalRequestIdsStateKey, pendingRequestIds);
        }
    }

    private static ResponseError InvalidApprovalRequest(string requestId) => new()
    {
        Code = ResponseErrorCodes.InvalidRequest,
        Message = $"Function approval response '{requestId}' does not match a pending approval request for this session."
    };
}
