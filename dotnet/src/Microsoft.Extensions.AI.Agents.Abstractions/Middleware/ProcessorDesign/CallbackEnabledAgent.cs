// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Base abstraction for all agents. An agent instance may participate in one or more conversations.
/// A conversation may include one or more agents.
/// </summary>
public sealed class CallbackEnabledAgent : DelegatingAIAgent
{
    private readonly CallbackMiddlewareProcessor _callbacksProcessor;

    /// <summary>
    /// Initializes a new instance of the <see cref="AIAgent"/> class with default settings.
    /// </summary>
    public CallbackEnabledAgent(AIAgent agent, CallbackMiddlewareProcessor? callbackMiddlewareProcessor) : base(agent)
    {
        this._callbacksProcessor = callbackMiddlewareProcessor ?? new();
    }

    /// <inheritdoc/>
    public override object? GetService(Type serviceType, object? serviceKey = null)
    {
        _ = Throw.IfNull(serviceType);

        return serviceKey is null && serviceType == typeof(CallbackEnabledAgent)
            ? this
            : this.InnerAgent.GetService(serviceType, serviceKey);
    }

    /// <summary>
    /// Run the agent with the provided message and arguments.
    /// </summary>
    /// <param name="messages">The messages to pass to the agent.</param>
    /// <param name="thread">
    /// The conversation thread to continue with this invocation. If not provided, creates a new thread.
    /// The thread will be mutated with the provided messages and agent response.
    /// </param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="AgentRunResponse"/> containing the list of <see cref="ChatMessage"/> items.</returns>
    public override async Task<AgentRunResponse> RunAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(messages);

        // The roaming context is used to hold into the context that was passed through the middleware chain.
        // This allows us to capture any specialized AgentInvokeCallbackContext context that may have been passed through the chain
        AgentRunContext roamingContext = null!;

        async Task CoreLogic(AgentRunContext ctx)
        {
            // There's a possibility that the provided context was customized by a specialized AgentInvokeCallbackContext context 
            roamingContext ??= ctx;
            var result = await this.InnerAgent.RunAsync(ctx.Messages, ctx.Thread, ctx.Options, ctx.CancellationToken)
                .ConfigureAwait(false);

            ctx.SetRunResponse(result);
        }

        await this._callbacksProcessor.ProcessAsync<AgentRunContext>(
            // Starting context
            new AgentRunContext(
                agent: this,
                messages: messages,
                thread,
                options,
                isStreaming: false,
                cancellationToken),
            CoreLogic,
            cancellationToken)
            .ConfigureAwait(false);

        return roamingContext.RawResponse as AgentRunResponse ?? throw new InvalidOperationException("The Result object provided in the agent invocation context must be a AgentRunResponse type.");
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(messages);

        // The context is used through the middleware chain.
        AgentRunContext roamingContext = new(
                agent: this,
                messages: messages,
                thread: thread,
                options: options,
                isStreaming: true,
                cancellationToken: cancellationToken);

        Task CoreLogic(AgentRunContext ctx)
        {
            var enumerable = this.InnerAgent.RunStreamingAsync(ctx.Messages, ctx.Thread, ctx.Options, ctx.CancellationToken);
            ctx.SetRunStreamingResponse(enumerable);

            return Task.CompletedTask;
        }

        await this._callbacksProcessor.ProcessAsync<AgentRunContext>(
            roamingContext,
            CoreLogic,
            cancellationToken)
            .ConfigureAwait(false);

        var result = roamingContext.RawResponse as IAsyncEnumerable<AgentRunResponseUpdate>
            ?? throw new InvalidOperationException("The Result object provided in the agent invocation context must be a IAsyncEnumerable<AgentRunResponseUpdate> type.");

        await foreach (var update in result.WithCancellation(cancellationToken).ConfigureAwait(false))
        {
            yield return update;
        }
    }

    /// <summary>
    /// Add a <see cref="ICallbackMiddleware"/> to the agent.
    /// </summary>
    /// <param name="callback">A callback implementation that the agent will be aware of.</param>
    public void AddCallback(ICallbackMiddleware<AgentRunContext> callback)
        => CallbackMiddlewareProcessorExtensions.AddCallback(this._callbacksProcessor, callback);
}
