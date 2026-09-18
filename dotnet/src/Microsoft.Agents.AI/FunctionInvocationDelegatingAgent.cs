// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Internal agent wrapper that gives callbacks control over function calls.
/// </summary>
internal sealed class FunctionInvocationDelegatingAgent : DelegatingAIAgent
{
    private readonly Func<AIAgent, FunctionInvocationContext, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>>, CancellationToken, ValueTask<object?>> _delegateFunc;

    internal FunctionInvocationDelegatingAgent(AIAgent innerAgent, Func<AIAgent, FunctionInvocationContext, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>>, CancellationToken, ValueTask<object?>> delegateFunc) : base(innerAgent)
    {
        this._delegateFunc = delegateFunc;
    }

    protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        => this.InnerAgent.RunAsync(messages, session, this.AgentRunOptionsWithFunctionMiddleware(options), cancellationToken);

    protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        => this.InnerAgent.RunStreamingAsync(messages, session, this.AgentRunOptionsWithFunctionMiddleware(options), cancellationToken);

    // Work on a per-run copy so adding callback support does not change options that the caller may reuse.
    private ChatClientAgentRunOptions AgentRunOptionsWithFunctionMiddleware(AgentRunOptions? options)
    {
        if (options is null || options.GetType() == typeof(AgentRunOptions))
        {
            // Plain agent options cannot hold a chat-client factory, so copy their shared values to chat-specific options.
            options = new ChatClientAgentRunOptions()
            {
                ResponseFormat = options?.ResponseFormat,
                AllowBackgroundResponses = options?.AllowBackgroundResponses,
                ContinuationToken = options?.ContinuationToken,
                AdditionalProperties = options?.AdditionalProperties,
            };
        }
        else if (options is ChatClientAgentRunOptions chatOptions)
        {
            options = chatOptions.Clone();
        }

        if (options is not ChatClientAgentRunOptions aco)
        {
            throw new NotSupportedException($"Function Invocation Middleware is only supported without options or with {nameof(ChatClientAgentRunOptions)}.");
        }

        var originalFactory = aco.ChatClientFactory;
        // Apply the original factory before adding our wrapper so even a replacement client keeps these callbacks.
        aco.ChatClientFactory = chatClient => FunctionMiddlewarePreservingChatClient.Build(chatClient, originalFactory, this);

        return aco;
    }

    /// <summary>
    /// Preserves the function middleware chain when tools are added or replaced during a run.
    /// </summary>
    private sealed class FunctionMiddlewarePreservingChatClient(
        IChatClient innerClient, FunctionInvocationDelegatingAgent[] middlewareChain) : DelegatingChatClient(innerClient)
    {
        // Concurrent runs must not combine the callbacks collected while their clients are built.
        private static readonly AsyncLocal<PipelineBuildScope?> s_buildScope = new();
        private readonly FunctionInvocationDelegatingAgent[] _middlewareChain = middlewareChain;

        internal static FunctionMiddlewarePreservingChatClient Build(
            IChatClient chatClient, Func<IChatClient, IChatClient>? originalFactory, FunctionInvocationDelegatingAgent middleware)
        {
            var previous = s_buildScope.Value;
            // Nested agent wrappers build one client synchronously. Share their list only within the same run.
            var scope = previous is not null && ReferenceEquals(previous.RunContext, CurrentRunContext)
                ? previous
                : new PipelineBuildScope(CurrentRunContext);
            // Function wrapping reverses this list, so insert at the front to keep callbacks in registration order.
            scope.Middleware.Insert(0, middleware);
            s_buildScope.Value = scope;
            try
            {
                var builder = chatClient.AsBuilder();
                if (originalFactory is not null)
                {
                    builder.Use(originalFactory);
                }

                return new FunctionMiddlewarePreservingChatClient(builder.Build(), [.. scope.Middleware]);
            }
            finally
            {
                // Restore the previous list so a later client build cannot reuse callbacks from this one.
                s_buildScope.Value = previous;
            }
        }

        public override async Task<ChatResponse> GetResponseAsync(
            IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
            => await this.InnerClient.GetResponseAsync(messages, this.ConfigureOptions(options), cancellationToken).ConfigureAwait(false);

        public override async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
            IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await foreach (var update in this.InnerClient.GetStreamingResponseAsync(messages, this.ConfigureOptions(options), cancellationToken).ConfigureAwait(false))
            {
                yield return update;
            }
        }

        private ChatOptions ConfigureOptions(ChatOptions? options)
        {
            // Each request gets its own options object, leaving caller-owned options unchanged.
            options = options?.Clone() ?? new();
            if (options.Tools is { } tools)
            {
                // This collection also wraps functions that are added or replaced later in the same run.
                options.Tools = new MiddlewareEnabledTools(tools, this._middlewareChain);
            }

            return options;
        }

        private sealed class PipelineBuildScope(AgentRunContext? runContext)
        {
            internal AgentRunContext? RunContext { get; } = runContext;
            internal List<FunctionInvocationDelegatingAgent> Middleware { get; } = [];
        }
    }

    private sealed class MiddlewareEnabledTools : Collection<AITool>
    {
        internal MiddlewareEnabledTools(IList<AITool> tools, FunctionInvocationDelegatingAgent[] middleware)
        {
            this.MiddlewareChain = middleware;
            // Add also wraps the functions already present, just as it will wrap functions added later.
            foreach (var tool in tools)
            {
                this.Add(tool);
            }
        }

        internal FunctionInvocationDelegatingAgent[] MiddlewareChain { get; }

        internal static void ApplyTo(ChatOptions options, FunctionInvocationDelegatingAgent[] middleware)
        {
            // Keep the current collection only when it already uses this exact callback list.
            if (options.Tools is { } tools &&
                (tools is not MiddlewareEnabledTools existing || !ReferenceEquals(existing.MiddlewareChain, middleware)))
            {
                options.Tools = new MiddlewareEnabledTools(tools, middleware);
            }
        }

        // Route later additions and replacements through the same callback wrapping.
        protected override void InsertItem(int index, AITool item) => base.InsertItem(index, this.Wrap(item));

        protected override void SetItem(int index, AITool item) => base.SetItem(index, this.Wrap(item));

        private AITool Wrap(AITool tool)
        {
            if (tool is AIFunction function)
            {
                foreach (var middleware in this.MiddlewareChain)
                {
                    function = MiddlewareEnabledFunction.Wrap(function, middleware, this.MiddlewareChain);
                }

                return function;
            }

            return tool;
        }
    }

    private sealed class MiddlewareEnabledFunction(
        AIFunction innerFunction,
        FunctionInvocationDelegatingAgent middleware,
        FunctionInvocationDelegatingAgent[] middlewareChain) : DelegatingAIFunction(innerFunction)
    {
        // Keep active callbacks with the current asynchronous operation instead of sharing process-wide state.
        private static readonly AsyncLocal<InvocationScope?> s_invocationScope = new();
        private readonly FunctionInvocationDelegatingAgent _middleware = middleware;
        private readonly FunctionInvocationDelegatingAgent[] _middlewareChain = middlewareChain;

        internal static AIFunction Wrap(AIFunction function, FunctionInvocationDelegatingAgent middleware, FunctionInvocationDelegatingAgent[] middlewareChain)
        {
            // Do not add the callback again when the function exposes an existing wrapper for it.
            for (var existing = function.GetService<MiddlewareEnabledFunction>();
                 existing is not null;
                 existing = existing.InnerFunction.GetService<MiddlewareEnabledFunction>())
            {
                if (ReferenceEquals(existing._middleware, middleware))
                {
                    return function;
                }
            }

            return new MiddlewareEnabledFunction(function, middleware, middlewareChain);
        }

        protected override async ValueTask<object?> InvokeCoreAsync(AIFunctionArguments arguments, CancellationToken cancellationToken)
        {
            var context = FunctionInvokingChatClient.CurrentContext
                // Direct function calls have no context from FunctionInvokingChatClient, so create the values the callback expects.
                ?? new FunctionInvocationContext()
                {
                    Arguments = arguments,
                    Function = this.InnerFunction,
                    CallContent = new(string.Empty, this.InnerFunction.Name, new Dictionary<string, object?>(arguments)),
                };

            var previous = s_invocationScope.Value;
            // A custom function wrapper can lead back to this callback during the same call. Run it only once.
            for (var active = previous; active is not null; active = active.Parent)
            {
                if (ReferenceEquals(active.Context, context) && ReferenceEquals(active.Middleware, this._middleware))
                {
                    return await CoreLogicAsync(context, cancellationToken).ConfigureAwait(false);
                }
            }

            // Record the callback while it runs, including through wrappers that do not expose their inner function.
            s_invocationScope.Value = new(context, this._middleware, previous);

            // ChatOptions.Clone keeps function wrappers but copies the tool list into a plain collection.
            // In that case, use the callback list saved on this function.
            var middlewareChain = (context.Options?.Tools as MiddlewareEnabledTools)?.MiddlewareChain ?? this._middlewareChain;
            try
            {
                return await this._middleware._delegateFunc(this._middleware.InnerAgent, context, CoreLogicAsync, cancellationToken).ConfigureAwait(false);
            }
            finally
            {
                // A function or callback can replace the entire tool list. Wrap the replacement before the next call.
                if (context.Options is { } options)
                {
                    MiddlewareEnabledTools.ApplyTo(options, middlewareChain);
                }
            }

            // Continue with the next function wrapper using any arguments changed by the callback.
            ValueTask<object?> CoreLogicAsync(FunctionInvocationContext ctx, CancellationToken cancellationToken)
                => base.InvokeCoreAsync(ctx.Arguments, cancellationToken);
        }

        private sealed class InvocationScope(
            FunctionInvocationContext context, FunctionInvocationDelegatingAgent middleware, InvocationScope? parent)
        {
            internal FunctionInvocationContext Context { get; } = context;
            internal FunctionInvocationDelegatingAgent Middleware { get; } = middleware;
            internal InvocationScope? Parent { get; } = parent;
        }
    }
}
