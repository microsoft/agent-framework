// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

internal sealed class ReasoningMessageStartEvent : BaseEvent
{
    public ReasoningMessageStartEvent()
    {
        this.Type = AGUIEventTypes.ReasoningMessageStart;
    }

    [JsonPropertyName("messageId")]
    public string MessageId { get; set; } = string.Empty;

    [JsonPropertyName("role")]
    public string Role { get; set; } = AGUIRoles.Reasoning;
}
