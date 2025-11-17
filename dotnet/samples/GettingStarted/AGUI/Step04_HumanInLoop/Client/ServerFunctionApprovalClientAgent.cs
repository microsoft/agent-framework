// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using ServerFunctionApproval;

/// <summary>
/// A delegating agent that handles server function approval requests and responses.
/// Transforms between FunctionApprovalRequestContent/FunctionApprovalResponseContent
/// and the server's request_approval tool call pattern.
/// </summary>
internal sealed class ServerFunctionApprovalClientAgent : DelegatingAIAgent
{
    private readonly JsonSerializerOptions _jsonSerializerOptions;

    public ServerFunctionApprovalClientAgent(AIAgent innerAgent, JsonSerializerOptions jsonSerializerOptions)
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
        // Process and transform approval messages, creating a new message list
        var processedMessages = ProcessOutgoingServerFunctionApprovals(messages.ToList(), this._jsonSerializerOptions);

        // Run the inner agent and intercept any approval requests
        await foreach (var update in this.InnerAgent.RunStreamingAsync(
            processedMessages, thread, options, cancellationToken).ConfigureAwait(false))
        {
            yield return ProcessIncomingServerApprovalRequests(update, this._jsonSerializerOptions);
        }
    }

#pragma warning disable MEAI001 // Type is for evaluation purposes only
    private static FunctionResultContent ConvertApprovalResponseToToolResult(FunctionApprovalResponseContent approvalResponse, JsonSerializerOptions jsonOptions)
    {
        return new FunctionResultContent(
            callId: approvalResponse.Id,
            result: JsonSerializer.SerializeToElement(
                new ApprovalResponse
                {
                    ApprovalId = approvalResponse.Id,
                    Approved = approvalResponse.Approved
                },
                jsonOptions));
    }

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

    private static List<ChatMessage> ProcessOutgoingServerFunctionApprovals(
        List<ChatMessage> messages,
        JsonSerializerOptions jsonSerializerOptions)
    {
        List<ChatMessage>? result = null;

        Dictionary<string, FunctionApprovalRequestContent> approvalRequests = [];
        for (var messageIndex = 0; messageIndex < messages.Count; messageIndex++)
        {
            var message = messages[messageIndex];
            List<AIContent>? transformedContents = null;

            // Process each content item in the message
            HashSet<string> approvalCalls = [];
            for (var contentIndex = 0; contentIndex < message.Contents.Count; contentIndex++)
            {
                var content = message.Contents[contentIndex];

                // Handle pending approval requests (transform to tool call)
                if (content is FunctionApprovalRequestContent approvalRequest &&
                    approvalRequest.AdditionalProperties?.TryGetValue("original_function", out var originalFunction) == true &&
                    originalFunction is FunctionCallContent original)
                {
                    approvalRequests[approvalRequest.Id] = approvalRequest;
                    transformedContents ??= CopyContentsUpToIndex(message.Contents, contentIndex);
                    transformedContents.Add(original);
                }
                // Handle pending approval responses (transform to tool result)
                else if (content is FunctionApprovalResponseContent approvalResponse &&
                    approvalRequests.TryGetValue(approvalResponse.Id, out var correspondingRequest))
                {
                    transformedContents ??= CopyContentsUpToIndex(message.Contents, contentIndex);
                    transformedContents.Add(ConvertApprovalResponseToToolResult(approvalResponse, jsonSerializerOptions));
                    approvalRequests.Remove(approvalResponse.Id);
                    correspondingRequest.AdditionalProperties?.Remove("original_function");
                }
                // Skip historical approval content
                else if (content is FunctionCallContent { Name: "request_approval" } approvalCall)
                {
                    transformedContents ??= CopyContentsUpToIndex(message.Contents, contentIndex);
                    approvalCalls.Add(approvalCall.CallId);
                }
                else if (content is FunctionResultContent functionResult &&
                         approvalCalls.Contains(functionResult.CallId))
                {
                    transformedContents ??= CopyContentsUpToIndex(message.Contents, contentIndex);
                    approvalCalls.Remove(functionResult.CallId);
                }
                else if (transformedContents != null)
                {
                    transformedContents.Add(content);
                }
            }

            if (transformedContents?.Count == 0)
            {
                continue;
            }
            else if (transformedContents != null)
            {
                // We made changes to contents, so use transformedContents
                var newMessage = new ChatMessage(message.Role, transformedContents)
                {
                    AuthorName = message.AuthorName,
                    MessageId = message.MessageId,
                    CreatedAt = message.CreatedAt,
                    RawRepresentation = message.RawRepresentation,
                    AdditionalProperties = message.AdditionalProperties
                };
                result ??= CopyMessagesUpToIndex(messages, messageIndex);
                result.Add(newMessage);
            }
            else if (result != null)
            {
                // We're already copying messages, so copy this unchanged message too
                result.Add(message);
            }
            // If result is null, we haven't made any changes yet, so keep processing
        }

        return result ?? messages;
    }

    private static AgentRunResponseUpdate ProcessIncomingServerApprovalRequests(
        AgentRunResponseUpdate update,
        JsonSerializerOptions jsonSerializerOptions)
    {
        IList<AIContent>? updatedContents = null;
        for (var i = 0; i < update.Contents.Count; i++)
        {
            var content = update.Contents[i];
            if (content is FunctionCallContent { Name: "request_approval" } request)
            {
                updatedContents ??= [.. update.Contents];

                // Serialize the function arguments as JsonElement
                ApprovalRequest? approvalRequest;
                if (request.Arguments?.TryGetValue("request", out var reqObj) == true &&
                    reqObj is JsonElement je)
                {
                    approvalRequest = (ApprovalRequest?)je.Deserialize(jsonSerializerOptions.GetTypeInfo(typeof(ApprovalRequest)));
                }
                else
                {
                    approvalRequest = null;
                }

                if (approvalRequest == null)
                {
                    throw new InvalidOperationException("Failed to deserialize approval request.");
                }

                var functionCallArgs = (Dictionary<string, object?>?)approvalRequest.FunctionArguments?
                    .Deserialize(jsonSerializerOptions.GetTypeInfo(typeof(Dictionary<string, object?>)));

                var approvalRequestContent = new FunctionApprovalRequestContent(
                    id: approvalRequest.ApprovalId,
                    new FunctionCallContent(
                        callId: approvalRequest.ApprovalId,
                        name: approvalRequest.FunctionName,
                        arguments: functionCallArgs));

                approvalRequestContent.AdditionalProperties ??= [];
                approvalRequestContent.AdditionalProperties["original_function"] = content;

                updatedContents[i] = approvalRequestContent;
            }
        }

        if (updatedContents is not null)
        {
            var chatUpdate = update.AsChatResponseUpdate();
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
                ContinuationToken = update.ContinuationToken,
            };
        }

        return update;
    }
}
#pragma warning restore MEAI001

namespace ServerFunctionApproval
{
    public sealed class ApprovalRequest
    {
        [JsonPropertyName("approval_id")]
        public required string ApprovalId { get; init; }

        [JsonPropertyName("function_name")]
        public required string FunctionName { get; init; }

        [JsonPropertyName("function_arguments")]
        public JsonElement? FunctionArguments { get; init; }

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
}
