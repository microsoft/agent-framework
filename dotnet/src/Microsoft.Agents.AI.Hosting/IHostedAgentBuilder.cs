// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Represents a builder for configuring AI agents within a hosting environment.
/// </summary>
public interface IHostedAgentBuilder
{
    /// <summary>
    /// Gets the name of the agent being configured.
    /// </summary>
    string Name { get; }

    /// <summary>
    /// Gets the application host builder for configuring additional services.
    /// </summary>
    IHostApplicationBuilder HostApplicationBuilder { get; }
}
