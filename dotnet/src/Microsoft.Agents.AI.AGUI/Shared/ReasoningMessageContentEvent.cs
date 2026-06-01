// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

internal sealed class ReasoningMessageContentEvent : BaseEvent
{
    public ReasoningMessageContentEvent()
    {
        this.Type = AGUIEventTypes.ReasoningMessageContent;
    }

    [JsonPropertyName("messageId")]
    public string MessageId { get; set; } = string.Empty;

    [JsonPropertyName("delta")]
    public string Delta { get; set; } = string.Empty;
}
