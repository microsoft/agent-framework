// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.DependencyInjection;

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
    /// Gets the service collection for configuration.
    /// </summary>
    IServiceCollection ServiceCollection { get; }
}
