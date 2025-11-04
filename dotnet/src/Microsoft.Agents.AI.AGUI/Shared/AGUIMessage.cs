// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

/// <summary>
/// Base class for AG-UI protocol messages.
/// Uses the "role" property as a discriminator for polymorphic serialization.
/// </summary>
[JsonConverter(typeof(AGUIMessageJsonConverter))]
internal abstract class AGUIMessage
{
    [JsonPropertyName("id")]
    public string? Id { get; set; }

    [JsonPropertyName("role")]
    public string Role { get; set; } = string.Empty;
}
