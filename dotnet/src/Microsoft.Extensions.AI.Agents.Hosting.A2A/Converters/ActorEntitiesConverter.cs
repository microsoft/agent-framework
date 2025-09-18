// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using A2A;
using Microsoft.Extensions.AI.Agents.Runtime;

namespace Microsoft.Extensions.AI.Agents.Hosting.A2A.Converters;

internal static class ActorEntitiesConverter
{
    public static Message ToMessage(this ActorResponse response)
    {
        var agentRunResponse =
            response.Data.Deserialize(AgentHostingJsonUtilities.DefaultOptions.GetTypeInfo(typeof(AgentRunResponse))) as AgentRunResponse ??
            throw new ArgumentException("The ActorResponse data could not be deserialized to an AgentRunResponse.", nameof(response));

        var contextId = response.ActorId.Key;
        var parts = agentRunResponse.Messages.ToParts();

        return new Message
        {
            MessageId = response.MessageId ?? Guid.NewGuid().ToString(),
            ContextId = contextId,
            Role = MessageRole.Agent,
            Parts = parts
        };
    }

    public static ActorRequestUpdate ToActorRequestUpdate(this Message message, RequestStatus status = RequestStatus.Completed)
    {
        // maybe we need to split to chatmessage-per-part, but the idea to map is clear
        var chatMessage =
            message.ToChatMessage() ??
            throw new ArgumentException("The Message could not be converted to a ChatMessage.", nameof(message));

        var agentRunResponseUpdate = new AgentRunResponseUpdate(ChatRole.Assistant, chatMessage.Contents);
        var updateTypeInfo = AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(AgentRunResponseUpdate));
        var jsonElement = JsonSerializer.SerializeToElement(agentRunResponseUpdate, updateTypeInfo);
        return new ActorRequestUpdate(status, jsonElement);
    }

    public static AgentRunResponse ToAgentRunResponse(this Message message)
    {
        // maybe we need to split to chatmessage-per-part, but the idea to map is clear
        var chatMessage =
            message.ToChatMessage() ??
            throw new ArgumentException("The Message could not be converted to a ChatMessage.", nameof(message));

        return new AgentRunResponse(chatMessage);
    }
}
