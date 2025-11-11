// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

internal sealed class ToolCallArgsEvent : BaseEvent
{
    public ToolCallArgsEvent()
    {
        this.Type = AGUIEventTypes.ToolCallArgs;
    }

    [JsonPropertyName("toolCallId")]
    public string ToolCallId { get; set; } = string.Empty;

    [JsonPropertyName("delta")]
    public string Delta { get; set; } = string.Empty;
}
