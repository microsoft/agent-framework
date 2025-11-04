// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

internal sealed class AGUIAssistantMessage : AGUIMessage
{
    public AGUIAssistantMessage()
    {
        this.Role = AGUIRoles.Assistant;
    }

    [JsonPropertyName("name")]
    public string? Name { get; set; }

    [JsonPropertyName("toolCalls")]
    public AGUIToolCall[]? ToolCalls { get; set; }
}
