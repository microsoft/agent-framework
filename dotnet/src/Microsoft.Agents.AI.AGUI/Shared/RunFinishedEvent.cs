// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

internal sealed class RunFinishedEvent : BaseEvent
{
    public RunFinishedEvent()
    {
        this.Type = AGUIEventTypes.RunFinished;
    }

    [JsonPropertyName("threadId")]
    public string ThreadId { get; set; } = string.Empty;

    [JsonPropertyName("runId")]
    public string RunId { get; set; } = string.Empty;

    [JsonPropertyName("result")]
    public JsonElement? Result { get; set; }
}
