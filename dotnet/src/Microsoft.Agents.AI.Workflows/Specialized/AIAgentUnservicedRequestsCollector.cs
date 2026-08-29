// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized;

internal sealed class AIAgentUnservicedRequestsCollector(AIContentExternalHandler<ToolApprovalRequestContent, ToolApprovalResponseContent>? userInputHandler,
                                                         AIContentExternalHandler<FunctionCallContent, FunctionResultContent>? functionCallHandler)
{
    private readonly Dictionary<string, ToolApprovalRequestContent> _userInputRequests = [];
    private readonly Dictionary<string, FunctionCallContent> _functionCalls = [];
    private readonly Dictionary<string, AgentResponseUpdate> _withheldApprovals = [];
    private readonly HashSet<string> _emittedWithheldApprovals = new(StringComparer.Ordinal);

    public async Task SubmitAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        Task userInputTask = userInputHandler != null && this._userInputRequests.Count > 0
                           ? userInputHandler.ProcessRequestContentsAsync(this._userInputRequests, context, cancellationToken)
                           : Task.CompletedTask;

        Task functionCallTask = functionCallHandler != null && this._functionCalls.Count > 0
                              ? functionCallHandler.ProcessRequestContentsAsync(this._functionCalls, context, cancellationToken)
                              : Task.CompletedTask;

        await Task.WhenAll(userInputTask, functionCallTask).ConfigureAwait(false);

        // A withheld approval that was neither raised as a request nor already emitted alongside its answer would
        // otherwise be lost, so emit it here rather than dropping it.
        foreach (KeyValuePair<string, AgentResponseUpdate> withheld in this._withheldApprovals)
        {
            if (!this._userInputRequests.ContainsKey(withheld.Key)
                && this._emittedWithheldApprovals.Add(withheld.Key))
            {
                await context.YieldOutputAsync(withheld.Value, cancellationToken).ConfigureAwait(false);
            }
        }
    }

    public void ProcessAgentResponseUpdate(AgentResponseUpdate update, Func<FunctionCallContent, bool>? functionCallFilter = null)
        => this.ProcessAIContents(update.Contents, functionCallFilter);

    public void ProcessAgentResponse(AgentResponse response)
        => this.ProcessAIContents(response.Messages.SelectMany(message => message.Contents));

    public void ProcessAIContents(IEnumerable<AIContent> contents, Func<FunctionCallContent, bool>? functionCallFilter = null)
    {
        foreach (AIContent content in contents)
        {
            if (content is ToolApprovalRequestContent userInputRequest)
            {
                if (this._userInputRequests.ContainsKey(userInputRequest.RequestId))
                {
                    throw new InvalidOperationException($"ToolApprovalRequestContent with duplicate RequestId: {userInputRequest.RequestId}");
                }

                // It is an error to simultaneously have multiple outstanding user input requests with the same ID.
                this._userInputRequests.Add(userInputRequest.RequestId, userInputRequest);
            }
            else if (content is ToolApprovalResponseContent userInputResponse)
            {
                // If the set of messages somehow already has a corresponding user input response, remove it.
                _ = this._userInputRequests.Remove(userInputResponse.RequestId);
            }
            else if (content is FunctionCallContent functionCall)
            {
                // For function calls, we emit an event to notify the workflow.
                //
                // possibility 1: this will be handled inline by the agent abstraction
                // possibility 2: this will not be handled inline by the agent abstraction
                if (functionCallFilter == null || functionCallFilter(functionCall))
                {
                    if (this._functionCalls.ContainsKey(functionCall.CallId))
                    {
                        throw new InvalidOperationException($"FunctionCallContent with duplicate CallId: {functionCall.CallId}");
                    }

                    this._functionCalls.Add(functionCall.CallId, functionCall);
                }
            }
            else if (content is FunctionResultContent functionResult)
            {
                _ = this._functionCalls.Remove(functionResult.CallId);
            }
        }
    }

    /// <summary>
    /// Returns the approvals withheld from earlier updates that <paramref name="update"/> answers, so they can be
    /// emitted ahead of it. Returns an empty list when there are none.
    /// </summary>
    /// <remarks>
    /// A withheld approval whose answer arrives later in the same run is never raised as a request, so it has to be
    /// put back on the wire, and it has to go out before the answer or the caller sees the two in reverse order.
    /// </remarks>
    public IReadOnlyList<AgentResponseUpdate> TakeApprovalsAnsweredBy(AgentResponseUpdate update)
    {
        if (this._withheldApprovals.Count == 0)
        {
            return [];
        }

        List<AgentResponseUpdate>? answered = null;
        foreach (AIContent content in update.Contents)
        {
            if (content is ToolApprovalResponseContent approvalResponse
                && this._withheldApprovals.TryGetValue(approvalResponse.RequestId, out AgentResponseUpdate? withheld)
                && this._emittedWithheldApprovals.Add(approvalResponse.RequestId))
            {
                (answered ??= []).Add(withheld);
            }
        }

        return answered ?? (IReadOnlyList<AgentResponseUpdate>)[];
    }

    /// <summary>
    /// Returns the update to emit as workflow output, or <see langword="null"/> when the update carried nothing
    /// beyond approval requests that this collector raises to an external caller.
    /// </summary>
    /// <remarks>
    /// <para>
    /// An approval raised through a request port is surfaced to the caller a second time, cloned with the
    /// workflow-facing request ID. That is the only ID the caller can answer with, so emitting the agent-local copy
    /// as well leaves the caller with two approval requests for one tool call and no way to tell them apart.
    /// </para>
    /// <para>
    /// Whether the approval really is raised is only settled once the run ends, so each withheld copy is kept and
    /// put back on the wire by <see cref="TakeApprovalsAnsweredBy"/> or <see cref="SubmitAsync"/> if no request was
    /// raised for it after all. An approval the same update already answers is left in place, since there is no
    /// earlier position to restore it to.
    /// </para>
    /// <para>
    /// Function call content is left in place: a function call in an agent stream is normally terminated inline in
    /// the same run, and whether it is still unserviced is not known until the stream ends.
    /// </para>
    /// </remarks>
    public AgentResponseUpdate? FilterExternallyRaisedApprovals(AgentResponseUpdate update)
    {
        if (userInputHandler?.RaisesExternalRequests != true)
        {
            return update;
        }

        IList<AIContent> contents = update.Contents;
        if (!contents.Any(content => content is ToolApprovalRequestContent))
        {
            return update;
        }

        HashSet<string>? answeredHere = null;
        foreach (AIContent content in contents)
        {
            if (content is ToolApprovalResponseContent approvalResponse)
            {
                (answeredHere ??= new(StringComparer.Ordinal)).Add(approvalResponse.RequestId);
            }
        }

        List<AIContent> retained = [];
        foreach (AIContent content in contents)
        {
            if (content is ToolApprovalRequestContent approvalRequest
                && answeredHere?.Contains(approvalRequest.RequestId) != true)
            {
                this._withheldApprovals[approvalRequest.RequestId] = CloneWithContents(update, [approvalRequest]);
            }
            else
            {
                retained.Add(content);
            }
        }

        return retained.Count > 0 ? CloneWithContents(update, retained) : null;
    }

    /// <summary>
    /// Returns the response to emit as workflow output, with the approval requests that this collector is about to
    /// raise to an external caller removed. See <see cref="FilterExternallyRaisedApprovals(AgentResponseUpdate)"/>
    /// for why the agent-local copy is not emitted alongside the workflow-facing one.
    /// </summary>
    /// <remarks>
    /// This runs after the whole response has been processed, so the approvals that will be raised are already
    /// known. An approval already withheld from a streamed update is removed as well: it reaches the caller either
    /// as the raised request or as the re-emission from <see cref="SubmitAsync"/>, never from here.
    /// </remarks>
    public AgentResponse FilterExternallyRaisedApprovals(AgentResponse response)
    {
        if (userInputHandler?.RaisesExternalRequests != true
            || (this._userInputRequests.Count == 0 && this._withheldApprovals.Count == 0))
        {
            return response;
        }

        if (!response.Messages.Any(message => message.Contents.Any(IsRaisedApproval)))
        {
            return response;
        }

        List<ChatMessage> retainedMessages = [];
        foreach (ChatMessage message in response.Messages)
        {
            List<AIContent> retained = message.Contents.Where(content => !IsRaisedApproval(content)).ToList();
            if (retained.Count == message.Contents.Count)
            {
                retainedMessages.Add(message);
            }
            else if (retained.Count > 0)
            {
                ChatMessage clone = message.Clone();
                clone.Contents = retained;
                retainedMessages.Add(clone);
            }
        }

        return CloneWithMessages(response, retainedMessages);

        bool IsRaisedApproval(AIContent content)
            => content is ToolApprovalRequestContent approvalRequest
            && (this._userInputRequests.ContainsKey(approvalRequest.RequestId)
                || this._withheldApprovals.ContainsKey(approvalRequest.RequestId));
    }

    private static AgentResponseUpdate CloneWithContents(AgentResponseUpdate update, IList<AIContent> contents) =>
        new()
        {
            AdditionalProperties = update.AdditionalProperties,
            AgentId = update.AgentId,
            AuthorName = update.AuthorName,
            ContinuationToken = update.ContinuationToken,
            Contents = contents,
            CreatedAt = update.CreatedAt,
            FinishReason = update.FinishReason,
            MessageId = update.MessageId,
            RawRepresentation = update.RawRepresentation,
            ResponseId = update.ResponseId,
            Role = update.Role,
        };

    private static AgentResponse CloneWithMessages(AgentResponse response, IList<ChatMessage> messages) =>
        new(messages)
        {
            AdditionalProperties = response.AdditionalProperties,
            AgentId = response.AgentId,
            ContinuationToken = response.ContinuationToken,
            CreatedAt = response.CreatedAt,
            FinishReason = response.FinishReason,
            RawRepresentation = response.RawRepresentation,
            ResponseId = response.ResponseId,
            Usage = response.Usage,
        };
}
