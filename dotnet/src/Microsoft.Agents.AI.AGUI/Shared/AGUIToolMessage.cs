// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

internal sealed class AGUIToolMessage : AGUIMessage
{
    public AGUIToolMessage()
    {
        this.Role = AGUIRoles.Tool;
    }

    [JsonPropertyName("toolCallId")]
    public string ToolCallId { get; set; } = string.Empty;

    [JsonPropertyName("error")]
    public string? Error { get; set; }
}
