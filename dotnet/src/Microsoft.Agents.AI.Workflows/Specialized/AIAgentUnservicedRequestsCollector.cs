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
    private readonly List<string> _displacedRequestIds = [];

    public async Task SubmitAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        Task userInputTask = userInputHandler != null && this._userInputRequests.Count > 0
                           ? userInputHandler.ProcessRequestContentsAsync(this._userInputRequests, context, cancellationToken)
                           : Task.CompletedTask;

        Task functionCallTask = functionCallHandler != null && this._functionCalls.Count > 0
                              ? functionCallHandler.ProcessRequestContentsAsync(this._functionCalls, context, cancellationToken)
                              : Task.CompletedTask;

        await Task.WhenAll(userInputTask, functionCallTask).ConfigureAwait(false);

        if (this._displacedRequestIds.Count > 0)
        {
            // A different request reusing an outstanding ID cannot be serviced alongside the one already
            // recorded under it, so report the ones that were dropped rather than losing them silently.
            await context.AddEventAsync(
                new WorkflowWarningEvent(
                    $"Ignored request content reusing an outstanding request ID ([{string.Join(", ", this._displacedRequestIds)}])."),
                cancellationToken).ConfigureAwait(false);
        }
    }

    public void ProcessAgentResponseUpdate(AgentResponseUpdate update, Func<FunctionCallContent, bool>? functionCallFilter = null)
        => this.ProcessAIContents(update.Contents, functionCallFilter);

    public void ProcessAgentResponse(AgentResponse response)
        => this.ProcessAIContents(response.Messages.SelectMany(message => message.Contents));

    /// <summary>
    /// Records the requests these contents leave unserviced, and clears the ones they answer.
    /// </summary>
    /// <remarks>
    /// The first content seen for a request ID is the one kept, matching
    /// <see cref="AIContentExternalHandler{TRequestContent, TResponseContent}"/>, which treats a repeat as an
    /// idempotent re-emission, and <c>ApprovalResponseBindingChatClient</c>, which binds a response against the
    /// first request recorded for the ID. A later content that is not the same request is reported by
    /// <see cref="SubmitAsync"/>.
    /// </remarks>
    public void ProcessAIContents(IEnumerable<AIContent> contents, Func<FunctionCallContent, bool>? functionCallFilter = null)
    {
        foreach (AIContent content in contents)
        {
            if (content is ToolApprovalRequestContent userInputRequest)
            {
                if (this._userInputRequests.TryGetValue(userInputRequest.RequestId, out ToolApprovalRequestContent? recordedRequest))
                {
                    // The approval's ID is derived from the call it guards, so a different call under the
                    // same ID is a different request rather than a re-emission of this one.
                    this.NoteDisplacedRequest(
                        userInputRequest.RequestId,
                        string.Equals(recordedRequest.ToolCall.CallId, userInputRequest.ToolCall.CallId, StringComparison.Ordinal));
                }
                else
                {
                    this._userInputRequests.Add(userInputRequest.RequestId, userInputRequest);
                }
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
                    if (this._functionCalls.TryGetValue(functionCall.CallId, out FunctionCallContent? recordedCall))
                    {
                        // A same-named call under one ID is taken to be a re-emission. Comparing arguments
                        // instead would report a legitimate re-emission whose arguments were rebuilt.
                        this.NoteDisplacedRequest(
                            functionCall.CallId,
                            string.Equals(recordedCall.Name, functionCall.Name, StringComparison.Ordinal));
                    }
                    else
                    {
                        this._functionCalls.Add(functionCall.CallId, functionCall);
                    }
                }
            }
            else if (content is FunctionResultContent functionResult)
            {
                _ = this._functionCalls.Remove(functionResult.CallId);
            }
        }
    }

    private void NoteDisplacedRequest(string requestId, bool isSameRequest)
    {
        if (!isSameRequest && !this._displacedRequestIds.Contains(requestId, StringComparer.Ordinal))
        {
            this._displacedRequestIds.Add(requestId);
        }
    }
}
