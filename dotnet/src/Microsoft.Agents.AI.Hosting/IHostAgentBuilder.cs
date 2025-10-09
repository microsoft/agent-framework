// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Represents a builder for configuring AI agents within a hosting environment.
/// </summary>
public interface IHostAgentBuilder
{
    /// <summary>
    /// Agent name.
    /// </summary>
    string Name { get; }

    /// <summary>
    /// Application host builder.
    /// </summary>
    IHostApplicationBuilder HostApplicationBuilder { get; }
}
