// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using ServerFunctionApproval;

/// <summary>
/// A delegating agent that handles function approval requests on the server side.
/// Transforms between FunctionApprovalRequestContent/FunctionApprovalResponseContent
/// and the request_approval tool call pattern for client communication.
/// </summary>
internal sealed class ServerFunctionApprovalAgent : DelegatingAIAgent
{
    private readonly JsonSerializerOptions _jsonSerializerOptions;

    public ServerFunctionApprovalAgent(AIAgent innerAgent, JsonSerializerOptions jsonSerializerOptions)
        : base(innerAgent)
    {
        this._jsonSerializerOptions = jsonSerializerOptions;
    }

    public override Task<AgentRunResponse> RunAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        return this.RunStreamingAsync(messages, thread, options, cancellationToken)
            .ToAgentRunResponseAsync(cancellationToken);
    }

    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        // Process and transform incoming approval responses from client, creating a new message list
        var processedMessages = ProcessIncomingFunctionApprovals(messages.ToList(), this._jsonSerializerOptions);

        // Run the inner agent and intercept any approval requests
        await foreach (var update in this.InnerAgent.RunStreamingAsync(
            processedMessages, thread, options, cancellationToken).ConfigureAwait(false))
        {
            yield return ProcessOutgoingApprovalRequests(update, this._jsonSerializerOptions);
        }
    }

#pragma warning disable MEAI001 // Type is for evaluation purposes only
    private static FunctionApprovalRequestContent ConvertToolCallToApprovalRequest(FunctionCallContent toolCall, JsonSerializerOptions jsonSerializerOptions)
    {
        if (toolCall.Name != "request_approval" || toolCall.Arguments == null)
        {
            throw new InvalidOperationException("Invalid request_approval tool call");
        }

        var request = toolCall.Arguments.TryGetValue("request", out var reqObj) &&
            reqObj is JsonElement argsElement &&
            argsElement.Deserialize(jsonSerializerOptions.GetTypeInfo(typeof(ApprovalRequest))) is ApprovalRequest approvalRequest &&
            approvalRequest != null ? approvalRequest : null;

        if (request == null)
        {
            throw new InvalidOperationException("Failed to deserialize approval request from tool call");
        }

        return new FunctionApprovalRequestContent(
            id: request.ApprovalId,
            new FunctionCallContent(
                callId: request.ApprovalId,
                name: request.FunctionName,
                arguments: request.FunctionArguments));
    }

    private static FunctionApprovalResponseContent ConvertToolResultToApprovalResponse(FunctionResultContent result, FunctionApprovalRequestContent approval, JsonSerializerOptions jsonSerializerOptions)
    {
        var approvalResponse = result.Result is JsonElement je ?
            (ApprovalResponse?)je.Deserialize(jsonSerializerOptions.GetTypeInfo(typeof(ApprovalResponse))) :
            result.Result is string str ?
                (ApprovalResponse?)JsonSerializer.Deserialize(str, jsonSerializerOptions.GetTypeInfo(typeof(ApprovalResponse))) :
                result.Result as ApprovalResponse;

        if (approvalResponse == null)
        {
            throw new InvalidOperationException("Failed to deserialize approval response from tool result");
        }

        return approval.CreateResponse(approvalResponse.Approved);
    }
#pragma warning restore MEAI001

    private static List<ChatMessage> CopyMessagesUpToIndex(List<ChatMessage> messages, int index)
    {
        var result = new List<ChatMessage>(index);
        for (int i = 0; i < index; i++)
        {
            result.Add(messages[i]);
        }
        return result;
    }

    private static List<AIContent> CopyContentsUpToIndex(IList<AIContent> contents, int index)
    {
        var result = new List<AIContent>(index);
        for (int i = 0; i < index; i++)
        {
            result.Add(contents[i]);
        }
        return result;
    }

    private static List<ChatMessage> ProcessIncomingFunctionApprovals(
        List<ChatMessage> messages,
        JsonSerializerOptions jsonSerializerOptions)
    {
        List<ChatMessage>? result = null;

        // Track approval ID to original call ID mapping
        _ = new Dictionary<string, string>();
#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
        Dictionary<string, FunctionApprovalRequestContent> trackedRequestApprovalToolCalls = new(); // Remote approvals
        for (int messageIndex = 0; messageIndex < messages.Count; messageIndex++)
        {
            var message = messages[messageIndex];
            List<AIContent>? transformedContents = null;
            for (int j = 0; j < message.Contents.Count; j++)
            {
                var content = message.Contents[j];
                if (content is FunctionCallContent { Name: "request_approval" } toolCall)
                {
                    result ??= CopyMessagesUpToIndex(messages, messageIndex);
                    transformedContents ??= CopyContentsUpToIndex(message.Contents, j);
                    var approvalRequest = ConvertToolCallToApprovalRequest(toolCall, jsonSerializerOptions);
                    transformedContents.Add(approvalRequest);
                    trackedRequestApprovalToolCalls[toolCall.CallId] = approvalRequest;
                    result.Add(new ChatMessage(message.Role, transformedContents)
                    {
                        AuthorName = message.AuthorName,
                        MessageId = message.MessageId,
                        CreatedAt = message.CreatedAt,
                        RawRepresentation = message.RawRepresentation,
                        AdditionalProperties = message.AdditionalProperties
                    });
                }
                else if (content is FunctionResultContent toolResult &&
                    trackedRequestApprovalToolCalls.TryGetValue(toolResult.CallId, out var approval) == true)
                {
                    result ??= CopyMessagesUpToIndex(messages, messageIndex);
                    transformedContents ??= CopyContentsUpToIndex(message.Contents, j);
                    var approvalResponse = ConvertToolResultToApprovalResponse(toolResult, approval, jsonSerializerOptions);
                    transformedContents.Add(approvalResponse);
                    result.Add(new ChatMessage(message.Role, transformedContents)
                    {
                        AuthorName = message.AuthorName,
                        MessageId = message.MessageId,
                        CreatedAt = message.CreatedAt,
                        RawRepresentation = message.RawRepresentation,
                        AdditionalProperties = message.AdditionalProperties
                    });
                }
                else if (result != null)
                {
                    result.Add(message);
                }
            }
        }
#pragma warning restore MEAI001

        return result ?? messages;
    }

    private static AgentRunResponseUpdate ProcessOutgoingApprovalRequests(
        AgentRunResponseUpdate update,
        JsonSerializerOptions jsonSerializerOptions)
    {
        IList<AIContent>? updatedContents = null;
        for (var i = 0; i < update.Contents.Count; i++)
        {
            var content = update.Contents[i];
#pragma warning disable MEAI001 // Type is for evaluation purposes only
            if (content is FunctionApprovalRequestContent request)
            {
                updatedContents ??= [.. update.Contents];
                var functionCall = request.FunctionCall;
                var approvalId = request.Id;

                var approvalData = new ApprovalRequest
                {
                    ApprovalId = approvalId,
                    FunctionName = functionCall.Name,
                    FunctionArguments = functionCall.Arguments,
                    Message = $"Approve execution of '{functionCall.Name}'?"
                };

                updatedContents[i] = new FunctionCallContent(
                    callId: approvalId,
                    name: "request_approval",
                    arguments: new Dictionary<string, object?> { ["request"] = approvalData });
            }
#pragma warning restore MEAI001
        }

        if (updatedContents is not null)
        {
            var chatUpdate = update.AsChatResponseUpdate();
            // Yield a tool call update that represents the approval request
            return new AgentRunResponseUpdate(new ChatResponseUpdate()
            {
                Role = chatUpdate.Role,
                Contents = updatedContents,
                MessageId = chatUpdate.MessageId,
                AuthorName = chatUpdate.AuthorName,
                CreatedAt = chatUpdate.CreatedAt,
                RawRepresentation = chatUpdate.RawRepresentation,
                ResponseId = chatUpdate.ResponseId,
                AdditionalProperties = chatUpdate.AdditionalProperties
            })
            {
                AgentId = update.AgentId,
                ContinuationToken = update.ContinuationToken
            };
        }

        return update;
    }
}

namespace ServerFunctionApproval
{
    // Define approval models
    public sealed class ApprovalRequest
    {
        [JsonPropertyName("approval_id")]
        public required string ApprovalId { get; init; }

        [JsonPropertyName("function_name")]
        public required string FunctionName { get; init; }

        [JsonPropertyName("function_arguments")]
        public IDictionary<string, object?>? FunctionArguments { get; init; }

        [JsonPropertyName("message")]
        public string? Message { get; init; }
    }

    public sealed class ApprovalResponse
    {
        [JsonPropertyName("approval_id")]
        public required string ApprovalId { get; init; }

        [JsonPropertyName("approved")]
        public required bool Approved { get; init; }
    }

    [JsonSerializable(typeof(ApprovalRequest))]
    [JsonSerializable(typeof(ApprovalResponse))]
    [JsonSerializable(typeof(Dictionary<string, object?>))]
    public sealed partial class ApprovalJsonContext : JsonSerializerContext;
}
