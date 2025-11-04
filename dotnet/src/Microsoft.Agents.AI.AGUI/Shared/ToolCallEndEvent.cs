// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

internal sealed class ToolCallEndEvent : BaseEvent
{
    public ToolCallEndEvent()
    {
        this.Type = AGUIEventTypes.ToolCallEnd;
    }

    [JsonPropertyName("toolCallId")]
    public string ToolCallId { get; set; } = string.Empty;
}
