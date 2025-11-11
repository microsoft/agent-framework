// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

internal sealed class StateSnapshotEvent : BaseEvent
{
    public StateSnapshotEvent()
    {
        this.Type = AGUIEventTypes.StateSnapshot;
    }

    [JsonPropertyName("snapshot")]
    public JsonElement? Snapshot { get; set; }
}
