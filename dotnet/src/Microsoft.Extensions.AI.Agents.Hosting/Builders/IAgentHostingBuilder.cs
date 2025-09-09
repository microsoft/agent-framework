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
    /// services
    /// </summary>
    IServiceCollection Services { get; }

    /// <summary>
    /// The actor type
    /// </summary>
    ActorType ActorType { get; }
}
