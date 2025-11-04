// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

/// <summary>
/// Represents an assistant message in the AG-UI protocol.
/// </summary>
internal sealed class AGUIAssistantMessage : AGUIMessage
{
    public AGUIAssistantMessage()
    {
        Role = AGUIRoles.Assistant;
    }

    [JsonPropertyName("content")]
    public string Content { get; set; } = string.Empty;

    [JsonPropertyName("toolCalls")]
    public AGUIToolCall[]? ToolCalls { get; set; }
}
