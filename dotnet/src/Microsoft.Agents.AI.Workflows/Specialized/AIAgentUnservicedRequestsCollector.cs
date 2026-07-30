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

    public Task SubmitAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        Task userInputTask = userInputHandler != null && this._userInputRequests.Count > 0
                           ? userInputHandler.ProcessRequestContentsAsync(this._userInputRequests, context, cancellationToken)
                           : Task.CompletedTask;

        Task functionCallTask = functionCallHandler != null && this._functionCalls.Count > 0
                              ? functionCallHandler.ProcessRequestContentsAsync(this._functionCalls, context, cancellationToken)
                              : Task.CompletedTask;

        return Task.WhenAll(userInputTask, functionCallTask);
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
}
