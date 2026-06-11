// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI;

/// <summary>
/// Source-generated JSON context for MCP-skills well-known DTOs.
/// </summary>
[JsonSourceGenerationOptions(JsonSerializerDefaults.Web, AllowTrailingCommas = true, ReadCommentHandling = JsonCommentHandling.Skip)]
[JsonSerializable(typeof(McpSkillIndex))]
[JsonSerializable(typeof(McpSkillIndexEntry))]
internal sealed partial class McpJsonContext : JsonSerializerContext;
