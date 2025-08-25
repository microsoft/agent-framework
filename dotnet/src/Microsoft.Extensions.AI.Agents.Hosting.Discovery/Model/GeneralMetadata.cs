// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI.Agents.Hosting.Discovery.Model;

/// <summary>
/// general
/// </summary>
public sealed class GeneralMetadata
{
    /// <summary>
    /// id
    /// </summary>
    public required string Name { get; init; }

    /// <summary>
    /// descr
    /// </summary>
    public string? Description { get; init; }

    /// <summary>
    /// instr
    /// </summary>
    public string? Instructions { get; init; }
}
