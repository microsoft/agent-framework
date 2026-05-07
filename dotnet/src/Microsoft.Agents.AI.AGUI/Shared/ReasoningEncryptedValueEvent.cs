// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

internal sealed class ReasoningEncryptedValueEvent : BaseEvent
{
    public ReasoningEncryptedValueEvent()
    {
        this.Type = AGUIEventTypes.ReasoningEncryptedValue;
    }

    [JsonPropertyName("subtype")]
    public string Subtype { get; set; } = "message";

    [JsonPropertyName("entityId")]
    public string EntityId { get; set; } = string.Empty;

    [JsonPropertyName("encryptedValue")]
    public string EncryptedValue { get; set; } = string.Empty;
}
