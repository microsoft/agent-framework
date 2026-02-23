// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides a builder for creating pipelines of <see cref="AIAgent"/>s.
/// </summary>
public sealed class AIAgentBuilder
{
    private readonly Func<IServiceProvider, AIAgent> _innerAgentFactory;

    /// <summary>The registered agent factory instances.</summary>
    private List<Func<AIAgent, IServiceProvider, AIAgent>>? _agentFactories;

    /// <summary>Initializes a new instance of the <see cref="AIAgentBuilder"/> class.</summary>
    /// <param name="innerAgent">The inner <see cref="AIAgent"/> that represents the underlying backend.</param>
    /// <exception cref="ArgumentNullException"><paramref name="innerAgent"/> is <see langword="null"/>.</exception>
    public AIAgentBuilder(AIAgent innerAgent)
    {
        _ = Throw.IfNull(innerAgent);
        this._innerAgentFactory = _ => innerAgent;
    }

    /// <summary>Initializes a new instance of the <see cref="AIAgentBuilder"/> class.</summary>
    /// <param name="innerAgentFactory">A callback that produces the inner <see cref="AIAgent"/> that represents the underlying backend.</param>
    /// <exception cref="ArgumentNullException"><paramref name="innerAgentFactory"/> is <see langword="null"/>.</exception>
    public AIAgentBuilder(Func<IServiceProvider, AIAgent> innerAgentFactory)
    {
        this._innerAgentFactory = Throw.IfNull(innerAgentFactory);
    }

    /// <summary>Builds an <see cref="AIAgent"/> that represents the entire pipeline.</summary>
    /// <param name="services">
    /// The <see cref="IServiceProvider"/> that should provide services to the <see cref="AIAgent"/> instances.
    /// If <see langword="null"/>, an empty <see cref="IServiceProvider"/> will be used.
    /// </param>
    /// <returns>An instance of <see cref="AIAgent"/> that represents the entire pipeline.</returns>
    /// <remarks>
    /// Calls to the resulting instance will pass through each of the pipeline stages in turn.
    /// </remarks>
    public AIAgent Build(IServiceProvider? services = null)
    {
        services ??= EmptyServiceProvider.Instance;
        var agent = this._innerAgentFactory(services);

        // To match intuitive expectations, apply the factories in reverse order, so that the first factory added is the outermost.
        if (this._agentFactories is not null)
        {
            for (var i = this._agentFactories.Count - 1; i >= 0; i--)
            {
                agent = this._agentFactories[i](agent, services);
                if (agent is null)
                {
                    Throw.InvalidOperationException(
                        $"The {nameof(AIAgentBuilder)} entry at index {i} returned null. " +
                        $"Ensure that the callbacks passed to {nameof(Use)} return non-null {nameof(AIAgent)} instances.");
                }
            }
        }

        return agent;
    }

    /// <summary>Adds a factory for an intermediate agent to the agent pipeline.</summary>
    /// <param name="agentFactory">The agent factory function.</param>
    /// <returns>The updated <see cref="AIAgentBuilder"/> instance.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="agentFactory"/> is <see langword="null"/>.</exception>
    public AIAgentBuilder Use(Func<AIAgent, AIAgent> agentFactory)
    {
        _ = Throw.IfNull(agentFactory);

        return this.Use((innerAgent, _) => agentFactory(innerAgent));
    }

    /// <summary>Adds a factory for an intermediate agent to the agent pipeline.</summary>
    /// <param name="agentFactory">The agent factory function.</param>
    /// <returns>The updated <see cref="AIAgentBuilder"/> instance.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="agentFactory"/> is <see langword="null"/>.</exception>
    public AIAgentBuilder Use(Func<AIAgent, IServiceProvider, AIAgent> agentFactory)
    {
        _ = Throw.IfNull(agentFactory);

        (this._agentFactories ??= []).Add(agentFactory);
        return this;
    }

    /// <summary>
    /// Adds to the agent pipeline an anonymous delegating agent based on a delegate that provides
    /// an implementation for both <see cref="AIAgent.RunAsync(IEnumerable{ChatMessage}, AgentSession?, AgentRunOptions?, CancellationToken)"/> and <see cref="AIAgent.RunStreamingAsync(IEnumerable{ChatMessage}, AgentSession?, AgentRunOptions?, CancellationToken)"/>.
    /// </summary>
    /// <param name="sharedFunc">
    /// A delegate that provides the implementation for both <see cref="AIAgent.RunAsync(IEnumerable{ChatMessage}, AgentSession?, AgentRunOptions?, CancellationToken)"/> and
    /// <see cref="AIAgent.RunStreamingAsync(IEnumerable{ChatMessage}, AgentSession?, AgentRunOptions?, CancellationToken)"/>. This delegate is invoked with the list of messages, the agent
    /// session, the run options, a delegate that represents invoking the inner agent, and a cancellation token. The delegate should be passed
    /// whatever messages, session, options, and cancellation token should be passed along to the next stage in the pipeline.
    /// It will handle both the non-streaming and streaming cases.
    /// </param>
    /// <returns>The updated <see cref="AIAgentBuilder"/> instance.</returns>
    /// <remarks>
    /// This overload can be used when the anonymous implementation needs to provide pre-processing and/or post-processing, but doesn't
    /// need to interact with the results of the operation, which will come from the inner agent.
    /// </remarks>
    /// <exception cref="ArgumentNullException"><paramref name="sharedFunc"/> is <see langword="null"/>.</exception>
    public AIAgentBuilder Use(Func<IEnumerable<ChatMessage>, AgentSession?, AgentRunOptions?, Func<IEnumerable<ChatMessage>, AgentSession?, AgentRunOptions?, CancellationToken, Task>, CancellationToken, Task> sharedFunc)
    {
        _ = Throw.IfNull(sharedFunc);

        return this.Use((innerAgent, _) => new AnonymousDelegatingAIAgent(innerAgent, sharedFunc));
    }

    /// <summary>
    /// Adds to the agent pipeline an anonymous delegating agent based on a delegate that provides
    /// an implementation for both <see cref="AIAgent.RunAsync(IEnumerable{ChatMessage}, AgentSession?, AgentRunOptions?, CancellationToken)"/> and <see cref="AIAgent.RunStreamingAsync(IEnumerable{ChatMessage}, AgentSession?, AgentRunOptions?, CancellationToken)"/>.
    /// </summary>
    /// <param name="runFunc">
    /// A delegate that provides the implementation for <see cref="AIAgent.RunAsync(IEnumerable{ChatMessage}, AgentSession?, AgentRunOptions?, CancellationToken)"/>. When <see langword="null"/>,
    /// <paramref name="runStreamingFunc"/> must be non-null, and the implementation of <see cref="AIAgent.RunAsync(IEnumerable{ChatMessage}, AgentSession?, AgentRunOptions?, CancellationToken)"/>
    /// will use <paramref name="runStreamingFunc"/> for the implementation.
    /// </param>
    /// <param name="runStreamingFunc">
    /// A delegate that provides the implementation for <see cref="AIAgent.RunStreamingAsync(IEnumerable{ChatMessage}, AgentSession?, AgentRunOptions?, CancellationToken)"/>. When <see langword="null"/>,
    /// <paramref name="runFunc"/> must be non-null, and the implementation of <see cref="AIAgent.RunStreamingAsync(IEnumerable{ChatMessage}, AgentSession?, AgentRunOptions?, CancellationToken)"/>
    /// will use <paramref name="runFunc"/> for the implementation.
    /// </param>
    /// <returns>The updated <see cref="AIAgentBuilder"/> instance.</returns>
    /// <remarks>
    /// One or both delegates can be provided. If both are provided, they will be used for their respective methods:
    /// <paramref name="runFunc"/> will provide the implementation of <see cref="AIAgent.RunAsync(IEnumerable{ChatMessage}, AgentSession?, AgentRunOptions?, CancellationToken)"/>, and
    /// <paramref name="runStreamingFunc"/> will provide the implementation of <see cref="AIAgent.RunStreamingAsync(IEnumerable{ChatMessage}, AgentSession?, AgentRunOptions?, CancellationToken)"/>.
    /// If only one of the delegates is provided, it will be used for both methods. That means that if <paramref name="runFunc"/>
    /// is supplied without <paramref name="runStreamingFunc"/>, the implementation of <see cref="AIAgent.RunStreamingAsync(IEnumerable{ChatMessage}, AgentSession?, AgentRunOptions?, CancellationToken)"/>
    /// will employ limited streaming, as it will be operating on the batch output produced by <paramref name="runFunc"/>. And if
    /// <paramref name="runStreamingFunc"/> is supplied without <paramref name="runFunc"/>, the implementation of
    /// <see cref="AIAgent.RunAsync(IEnumerable{ChatMessage}, AgentSession?, AgentRunOptions?, CancellationToken)"/> will be implemented by combining the updates from <paramref name="runStreamingFunc"/>.
    /// </remarks>
    /// <exception cref="ArgumentNullException">Both <paramref name="runFunc"/> and <paramref name="runStreamingFunc"/> are <see langword="null"/>.</exception>
    public AIAgentBuilder Use(
        Func<IEnumerable<ChatMessage>, AgentSession?, AgentRunOptions?, AIAgent, CancellationToken, Task<AgentResponse>>? runFunc,
        Func<IEnumerable<ChatMessage>, AgentSession?, AgentRunOptions?, AIAgent, CancellationToken, IAsyncEnumerable<AgentResponseUpdate>>? runStreamingFunc)
    {
        AnonymousDelegatingAIAgent.ThrowIfBothDelegatesNull(runFunc, runStreamingFunc);

        return this.Use((innerAgent, _) => new AnonymousDelegatingAIAgent(innerAgent, runFunc, runStreamingFunc));
    }

    /// <summary>
    /// Adds one or more <see cref="MessageAIContextProvider"/> instances to the agent pipeline, enabling message enrichment
    /// for any <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="providers">
    /// The <see cref="MessageAIContextProvider"/> instances to invoke before and after each agent invocation.
    /// Providers are called in sequence, with each receiving the output of the previous provider.
    /// </param>
    /// <returns>The <see cref="AIAgentBuilder"/> with the providers added, enabling method chaining.</returns>
    /// <exception cref="ArgumentException"><paramref name="providers"/> is empty.</exception>
    /// <remarks>
    /// <para>
    /// This method wraps the inner agent with a <see cref="DelegatingAIAgent"/> that calls each provider's
    /// <see cref="MessageAIContextProvider.InvokingAsync"/> in sequence before the inner agent runs,
    /// and calls <see cref="AIContextProvider.InvokedAsync"/> on each provider after the inner agent completes.
    /// </para>
    /// <para>
    /// This allows any <see cref="AIAgent"/> to benefit from <see cref="MessageAIContextProvider"/>-based
    /// context enrichment, not just agents that natively support <see cref="AIContextProvider"/> instances.
    /// </para>
    /// </remarks>
    public AIAgentBuilder UseAIContextProviders(params MessageAIContextProvider[] providers)
    {
        return this.Use((innerAgent, _) => new MessageAIContextProviderAgent(innerAgent, providers));
    }

    /// <summary>
    /// Provides an empty <see cref="IServiceProvider"/> implementation.
    /// </summary>
    private sealed class EmptyServiceProvider : IServiceProvider, IKeyedServiceProvider
    {
        /// <summary>Gets the singleton instance of <see cref="EmptyServiceProvider"/>.</summary>
        public static EmptyServiceProvider Instance { get; } = new();

        /// <inheritdoc/>
        public object? GetService(Type serviceType) => null;

        /// <inheritdoc/>
        public object? GetKeyedService(Type serviceType, object? serviceKey) => null;

        /// <inheritdoc/>
        public object GetRequiredKeyedService(Type serviceType, object? serviceKey) =>
            throw new InvalidOperationException($"No service for type '{serviceType}' has been registered.");
    }
}
