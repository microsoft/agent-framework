// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

internal sealed class ReasoningStartEvent : BaseEvent
{
    public ReasoningStartEvent()
    {
        this.Type = AGUIEventTypes.ReasoningStart;
    }

    [JsonPropertyName("messageId")]
    public string MessageId { get; set; } = string.Empty;
}
