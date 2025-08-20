// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Extensions.AI.Agents.Hosting;

/// <summary>
/// Defines a contract for building AI agent instances using a configurable builder pattern.
/// </summary>
public interface IAIAgentHostingBuilder
{
    /// <summary>
    /// services
    /// </summary>
    IServiceCollection Services { get; }

    /// <summary>
    /// The actor type
    /// </summary>
    ActorType ActorType { get; }
}
