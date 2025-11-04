// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

/// <summary>
/// Represents a developer message in the AG-UI protocol.
/// </summary>
internal sealed class AGUIDeveloperMessage : AGUIMessage
{
    public AGUIDeveloperMessage()
    {
        Role = AGUIRoles.Developer;
    }

    [JsonPropertyName("content")]
    public string Content { get; set; } = string.Empty;
}
