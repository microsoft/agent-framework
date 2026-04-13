// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

internal sealed class ActivitySnapshotEvent : BaseEvent
{
    public ActivitySnapshotEvent()
    {
        this.Type = AGUIEventTypes.ActivitySnapshot;
    }

    [JsonPropertyName("messageId")]
    public string? MessageId { get; set; }

    [JsonPropertyName("activityType")]
    public string ActivityType { get; set; } = string.Empty;

    [JsonPropertyName("replace")]
    public bool Replace { get; set; }

    [JsonPropertyName("content")]
    public JsonElement? Content { get; set; }
}
