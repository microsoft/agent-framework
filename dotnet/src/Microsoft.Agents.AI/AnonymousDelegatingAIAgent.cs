// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading;
using System.Threading.Channels;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>Represents a delegating AI agent that wraps an inner agent with implementations provided by delegates.</summary>
/// <remarks>
/// This internal class is a convenience implementation mainly used to support <see cref="AIAgentBuilder"/> Use methods that take delegates to intercept agent operations.
/// </remarks>
internal sealed class AnonymousDelegatingAIAgent : DelegatingAIAgent
{
    /// <summary>The delegate to use as the implementation of <see cref="RunCoreAsync"/>.</summary>
    private readonly Func<IEnumerable<ChatMessage>, AgentThread?, AgentRunOptions?, AIAgent, CancellationToken, Task<AgentResponse>>? _runFunc;

    /// <summary>The delegate to use as the implementation of <see cref="RunCoreStreamingAsync"/>.</summary>
    /// <remarks>
    /// When non-<see langword="null"/>, this delegate is used as the implementation of <see cref="RunCoreStreamingAsync"/> and
    /// will be invoked with the same arguments as the method itself.
    /// When <see langword="null"/>, <see cref="RunCoreStreamingAsync"/> will delegate directly to the inner agent.
    /// </remarks>
    private readonly Func<IEnumerable<ChatMessage>, AgentThread?, AgentRunOptions?, AIAgent, CancellationToken, IAsyncEnumerable<AgentResponseUpdate>>? _runStreamingFunc;

    /// <summary>The delegate to use as the implementation of both <see cref="RunCoreAsync"/> and <see cref="RunCoreStreamingAsync"/>.</summary>
    private readonly Func<IEnumerable<ChatMessage>, AgentThread?, AgentRunOptions?, Func<IEnumerable<ChatMessage>, AgentThread?, AgentRunOptions?, CancellationToken, Task>, CancellationToken, Task>? _sharedFunc;

    /// <summary>
    /// Initializes a new instance of the <see cref="AnonymousDelegatingAIAgent"/> class.
    /// </summary>
    /// <param name="innerAgent">The inner agent.</param>
    /// <param name="sharedFunc">
    /// A delegate that provides the implementation for both <see cref="RunCoreAsync"/> and <see cref="RunCoreStreamingAsync"/>.
    /// In addition to the arguments for the operation, it's provided with a delegate to the inner agent that should be
    /// used to perform the operation on the inner agent. It will handle both the non-streaming and streaming cases.
    /// </param>
    /// <remarks>
    /// This overload may be used when the anonymous implementation needs to provide pre-processing and/or post-processing, but doesn't
    /// need to interact with the results of the operation, which will come from the inner agent.
    /// </remarks>
    /// <exception cref="ArgumentNullException"><paramref name="innerAgent"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentNullException"><paramref name="sharedFunc"/> is <see langword="null"/>.</exception>
    public AnonymousDelegatingAIAgent(
        AIAgent innerAgent,
        Func<IEnumerable<ChatMessage>, AgentThread?, AgentRunOptions?, Func<IEnumerable<ChatMessage>, AgentThread?, AgentRunOptions?, CancellationToken, Task>, CancellationToken, Task> sharedFunc)
        : base(innerAgent)
    {
        _ = Throw.IfNull(sharedFunc);

        this._sharedFunc = sharedFunc;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AnonymousDelegatingAIAgent"/> class.
    /// </summary>
    /// <param name="innerAgent">The inner agent.</param>
    /// <param name="runFunc">
    /// A delegate that provides the implementation for <see cref="RunCoreAsync"/>. When <see langword="null"/>,
    /// <paramref name="runStreamingFunc"/> must be non-null, and the implementation of <see cref="RunCoreAsync"/>
    /// will use <paramref name="runStreamingFunc"/> for the implementation.
    /// </param>
    /// <param name="runStreamingFunc">
    /// A delegate that provides the implementation for <see cref="RunCoreStreamingAsync"/>. When <see langword="null"/>,
    /// <paramref name="runFunc"/> must be non-null, and the implementation of <see cref="RunCoreStreamingAsync"/>
    /// will use <paramref name="runFunc"/> for the implementation.
    /// </param>
    /// <exception cref="ArgumentNullException"><paramref name="innerAgent"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentNullException">Both <paramref name="runFunc"/> and <paramref name="runStreamingFunc"/> are <see langword="null"/>.</exception>
    public AnonymousDelegatingAIAgent(
        AIAgent innerAgent,
        Func<IEnumerable<ChatMessage>, AgentThread?, AgentRunOptions?, AIAgent, CancellationToken, Task<AgentResponse>>? runFunc,
        Func<IEnumerable<ChatMessage>, AgentThread?, AgentRunOptions?, AIAgent, CancellationToken, IAsyncEnumerable<AgentResponseUpdate>>? runStreamingFunc)
        : base(innerAgent)
    {
        ThrowIfBothDelegatesNull(runFunc, runStreamingFunc);

        this._runFunc = runFunc;
        this._runStreamingFunc = runStreamingFunc;
    }

    /// <inheritdoc/>
    protected override Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(messages);

        if (this._sharedFunc is not null)
        {
            return GetRunViaSharedAsync(messages, thread, options, cancellationToken);

            async Task<AgentResponse> GetRunViaSharedAsync(
                IEnumerable<ChatMessage> messages, AgentThread? thread, AgentRunOptions? options, CancellationToken cancellationToken)
            {
                AgentResponse? response = null;

                await this._sharedFunc(
                    messages,
                    thread,
                    options,
                    async (messages, thread, options, cancellationToken)
                        => response = await this.InnerAgent.RunAsync(messages, thread, options, cancellationToken).ConfigureAwait(false),
                    cancellationToken)
                    .ConfigureAwait(false);

                if (response is null)
                {
                    Throw.InvalidOperationException("The shared delegate completed successfully without producing an AgentResponse.");
                }

                return response;
            }
        }
        else if (this._runFunc is not null)
        {
            return this._runFunc(messages, thread, options, this.InnerAgent, cancellationToken);
        }
        else
        {
            Debug.Assert(this._runStreamingFunc is not null, "Expected non-null streaming delegate.");
            return this._runStreamingFunc!(messages, thread, options, this.InnerAgent, cancellationToken)
                .ToAgentResponseAsync(cancellationToken);
        }
    }

    /// <inheritdoc/>
    protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(messages);

        if (this._sharedFunc is not null)
        {
            var updates = Channel.CreateBounded<AgentResponseUpdate>(1);

            _ = ProcessAsync();
            async Task ProcessAsync()
            {
                Exception? error = null;
                try
                {
                    await this._sharedFunc(messages, thread, options, async (messages, thread, options, cancellationToken) =>
                    {
                        await foreach (var update in this.InnerAgent.RunStreamingAsync(messages, thread, options, cancellationToken).ConfigureAwait(false))
                        {
                            await updates.Writer.WriteAsync(update, cancellationToken).ConfigureAwait(false);
                        }
                    }, cancellationToken).ConfigureAwait(false);
                }
                catch (Exception ex)
                {
                    error = ex;
                    throw;
                }
                finally
                {
                    _ = updates.Writer.TryComplete(error);
                }
            }

            return updates.Reader.ReadAllAsync(cancellationToken);
        }
        else if (this._runStreamingFunc is not null)
        {
            return this._runStreamingFunc(messages, thread, options, this.InnerAgent, cancellationToken);
        }
        else
        {
            Debug.Assert(this._runFunc is not null, "Expected non-null non-streaming delegate.");
            return GetStreamingRunAsyncViaRunAsync(this._runFunc!(messages, thread, options, this.InnerAgent, cancellationToken));

            static async IAsyncEnumerable<AgentResponseUpdate> GetStreamingRunAsyncViaRunAsync(Task<AgentResponse> task)
            {
                AgentResponse response = await task.ConfigureAwait(false);
                foreach (var update in response.ToAgentResponseUpdates())
                {
                    yield return update;
                }
            }
        }
    }

    /// <summary>Throws an exception if both of the specified delegates are <see langword="null"/>.</summary>
    /// <exception cref="ArgumentNullException">Both <paramref name="runFunc"/> and <paramref name="runStreamingFunc"/> are <see langword="null"/>.</exception>
    internal static void ThrowIfBothDelegatesNull(object? runFunc, object? runStreamingFunc)
    {
        if (runFunc is null && runStreamingFunc is null)
        {
            Throw.ArgumentNullException(nameof(runFunc), $"At least one of the {nameof(runFunc)} or {nameof(runStreamingFunc)} delegates must be non-null.");
        }
    }
}
