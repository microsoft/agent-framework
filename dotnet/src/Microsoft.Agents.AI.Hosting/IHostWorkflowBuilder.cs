// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// todo
/// </summary>
public interface IHostWorkflowBuilder
{
    /// <summary>
    /// Workflow name.
    /// </summary>
    string Name { get; }

    /// <summary>
    /// Application host builder.
    /// </summary>
    IHostApplicationBuilder HostApplicationBuilder { get; }
}
