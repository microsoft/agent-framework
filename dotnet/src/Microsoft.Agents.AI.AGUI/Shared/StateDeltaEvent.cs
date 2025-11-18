// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

internal sealed class StateDeltaEvent : BaseEvent
{
    public StateDeltaEvent()
    {
        this.Type = AGUIEventTypes.StateDelta;
    }

    [JsonPropertyName("delta")]
    public JsonElement? Delta { get; set; }
}
