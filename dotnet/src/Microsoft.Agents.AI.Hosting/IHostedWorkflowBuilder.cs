// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.Hosting;

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
    /// Gets the application host builder for configuring additional services.
    /// </summary>
    IHostApplicationBuilder HostApplicationBuilder { get; }
}
