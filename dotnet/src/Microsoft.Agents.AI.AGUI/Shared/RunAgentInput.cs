// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.ComponentModel.DataAnnotations;
using System.Text.Json;
using System.Text.Json.Serialization;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

internal sealed class RunAgentInput
{
    [Required]
    [JsonPropertyName("threadId")]
    public string ThreadId { get; set; } = string.Empty;

    [Required]
    [JsonPropertyName("runId")]
    public string RunId { get; set; } = string.Empty;

    [JsonPropertyName("state")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
    public JsonElement State { get; set; }

    [Required]
#pragma warning disable IL2026 // MinLengthAttribute on arrays is trim-safe
    [MinLength(1)]
#pragma warning restore IL2026
    [JsonPropertyName("messages")]
    public IEnumerable<AGUIMessage> Messages { get; set; } = [];

    [JsonPropertyName("tools")]
    public IEnumerable<AGUITool> Tools { get; set; } = [];

    [JsonPropertyName("context")]
    public Dictionary<string, string> Context { get; set; } = new(StringComparer.Ordinal);

    [JsonPropertyName("forwardedProperties")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
    public JsonElement ForwardedProperties { get; set; }
}
