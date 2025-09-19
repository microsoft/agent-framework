// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Defines a builder for creating and configuring an <see cref="AIAgent"/> pipeline.
/// </summary>
/// <remarks>The <see cref="IAIAgentBuilder{TAgent}"/> interface provides methods to construct an <see
/// cref="AIAgent"/> pipeline by adding intermediate agents and configuring the pipeline stages. The resulting pipeline
/// processes requests sequentially through the configured stages.</remarks>
/// <typeparam name="TAgent">The type of <see cref="AIAgent"/> produced by the builder. This type must derive from <see cref="AIAgent"/>.</typeparam>
public interface IAIAgentBuilder<out TAgent> where TAgent : AIAgent
{
    /// <summary>Builds an <see cref="AIAgent"/> that represents the entire pipeline. Calls to this instance will pass through each of the pipeline stages in turn.</summary>
    /// <param name="services">
    /// The <see cref="IServiceProvider"/> that should provide services to the <see cref="AIAgent"/> instances.
    /// If <see langword="null"/>, an empty <see cref="IServiceProvider"/> will be used.
    /// </param>
    /// <returns>An instance of <see cref="AIAgent"/> that represents the entire pipeline.</returns>
    TAgent Build(IServiceProvider? services = null);

    /// <summary>Adds a factory for an intermediate agent to the agent pipeline.</summary>
    /// <param name="agentFactory">The agent factory function.</param>
    /// <returns>The updated <see cref="AIAgentBuilder"/> instance.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="agentFactory"/> is <see langword="null"/>.</exception>
    /// <related type="Article" href="https://learn.microsoft.com/dotnet/ai/microsoft-extensions-ai#functionality-pipelines">Pipelines of functionality.</related>
    IAIAgentBuilder<TAgent> Use(Func<AIAgent, IServiceProvider, AIAgent> agentFactory);
}
