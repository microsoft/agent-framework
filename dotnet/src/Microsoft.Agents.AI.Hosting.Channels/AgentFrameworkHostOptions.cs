// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Hosting.Channels;

/// <summary>
/// Composition-time options for <c>AddAgentFrameworkHost(...)</c>.
/// </summary>
public sealed class AgentFrameworkHostOptions
{
    /// <summary>File-system layout for the file-backed host state store.</summary>
    public HostStatePathOptions? StatePaths { get; set; }
}
