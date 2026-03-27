// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

internal sealed class ReasoningMessageChunkEvent : BaseEvent
{
    public ReasoningMessageChunkEvent()
    {
        this.Type = AGUIEventTypes.ReasoningMessageChunk;
    }

    [JsonPropertyName("messageId")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? MessageId { get; set; }

    [JsonPropertyName("delta")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Delta { get; set; }
}
