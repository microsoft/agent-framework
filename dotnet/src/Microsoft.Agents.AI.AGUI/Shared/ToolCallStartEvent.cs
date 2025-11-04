// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

internal sealed class ToolCallStartEvent : BaseEvent
{
    public ToolCallStartEvent()
    {
        this.Type = AGUIEventTypes.ToolCallStart;
    }

    [JsonPropertyName("toolCallId")]
    public string ToolCallId { get; set; } = string.Empty;

    [JsonPropertyName("toolCallName")]
    public string ToolCallName { get; set; } = string.Empty;

    [JsonPropertyName("parentMessageId")]
    public string? ParentMessageId { get; set; }
}
