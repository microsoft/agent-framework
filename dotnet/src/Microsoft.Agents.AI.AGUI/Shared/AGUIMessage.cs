// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel.DataAnnotations;
using System.Text.Json.Serialization;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

internal sealed class AGUIMessage
{
    [Required]
    [JsonPropertyName("id")]
    public string? Id { get; set; }

    [Required]
    [JsonPropertyName("role")]
    public string Role { get; set; } = string.Empty;

    [Required]
    [JsonPropertyName("content")]
    public string Content { get; set; } = string.Empty;
}
