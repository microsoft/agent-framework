// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Extensions.AI.Agents.Hosting;

/// <summary>
/// Represents builder which helps to configure behavior for <see cref="AIAgent"/>.
/// </summary>
public interface IAgentHostingBuilder
{
    /// <summary>
    /// The service collection for dependency injection.
    /// </summary>
    IServiceCollection Services { get; }

    /// <summary>
    /// The actor type associated with the agent.
    /// </summary>
    ActorType ActorType { get; }
}
