// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Represents a builder for configuring workflows within a hosting environment.
/// </summary>
public interface IHostedWorkflowBuilder
{
    /// <summary>
    /// Gets the name of the workflow being configured.
    /// </summary>
    string Name { get; }

    /// <summary>
    /// Gets the service collection for configuration.
    /// </summary>
    IServiceCollection Services { get; }
}
