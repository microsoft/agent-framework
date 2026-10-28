// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides JSON conversion for skill-list and individual-skill responses.
/// </summary>
[JsonSourceGenerationOptions(
    JsonSerializerDefaults.Web,
    PropertyNameCaseInsensitive = false,
    RespectNullableAnnotations = true,
    AllowTrailingCommas = true,
    ReadCommentHandling = JsonCommentHandling.Skip)]
[JsonSerializable(typeof(McpSkillsListResult))]
[JsonSerializable(typeof(McpSkillsGetResult))]
[JsonSerializable(typeof(McpSkillEntry))]
[JsonSerializable(typeof(McpSkillFrontmatter))]
[JsonSerializable(typeof(McpSkillResourceEntry))]
internal sealed partial class McpSkillsJsonContext : JsonSerializerContext;
