// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;

namespace Microsoft.Agents.AI.Valkey;

/// <summary>
/// Options for configuring <see cref="ValkeyStreamBuffer"/>.
/// </summary>
public sealed class ValkeyStreamBufferOptions
{
    /// <summary>
    /// Gets or sets the prefix for Valkey stream keys. Defaults to "agent_stream".
    /// </summary>
    public string KeyPrefix { get; set; } = "agent_stream";

    /// <summary>
    /// Gets or sets the maximum number of entries to retain per stream.
    /// When set, XTRIM with approximate trimming is applied after each XADD.
    /// Null means no trimming.
    /// </summary>
    public int? MaxLength { get; set; }

    /// <summary>
    /// Gets or sets optional JSON serializer options for serializing AgentResponseUpdate.
    /// </summary>
    public JsonSerializerOptions? JsonSerializerOptions { get; set; }
}
