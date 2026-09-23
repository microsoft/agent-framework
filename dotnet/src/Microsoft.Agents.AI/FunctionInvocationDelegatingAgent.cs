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

    /// <summary>
    /// Wraps <paramref name="function"/> with the function invocation callbacks that have not yet run for the
    /// invocation of <paramref name="context"/>.
    /// </summary>
    /// <param name="context">The context of the callback that is currently running.</param>
    /// <param name="function">The function to wrap.</param>
    /// <returns>The wrapped function, or <paramref name="function"/> when no further callbacks are pending.</returns>
    /// <exception cref="InvalidOperationException">No function invocation callback is running for <paramref name="context"/>.</exception>
    internal static AIFunction WrapWithPendingMiddleware(FunctionInvocationContext context, AIFunction function)
        => MiddlewareEnabledFunction.WrapWithPendingMiddleware(context, function);

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

        internal static AIFunction WrapWithPendingMiddleware(FunctionInvocationContext context, AIFunction function)
        {
            for (var active = s_invocationScope.Value; active is not null; active = active.Parent)
            {
                // Execution contexts that escaped a callback keep a reference to its scope, so a scope is only
                // usable while its callback runs.
                if (!active.IsRunning || !ReferenceEquals(active.Context, context))
                {
                    continue;
                }

                if (active.ContinuationInvoked)
                {
                    throw new InvalidOperationException(
                        "The function invocation callbacks that have not run yet cannot be determined after the continuation was called. " +
                        $"Call {nameof(WrapWithPendingMiddleware)} before calling the continuation.");
                }

                // Functions are wrapped from the last callback to the first, so the callbacks that
                // still have to run for this invocation are the ones before the running callback.
                var chain = active.MiddlewareChain;
                var pendingCount = Array.IndexOf(chain, active.Middleware);
                for (var i = 0; i < pendingCount; i++)
                {
                    function = Wrap(function, chain[i], chain);
                }

                return function;
            }

            throw new InvalidOperationException(
                $"No function invocation callback is running for the supplied {nameof(FunctionInvocationContext)}.");
        }

        protected override async ValueTask<object?> InvokeCoreAsync(AIFunctionArguments arguments, CancellationToken cancellationToken)
        {
            var previous = s_invocationScope.Value;

            // Direct function calls have no context from FunctionInvokingChatClient, so create the values the
            // callback expects. Wrappers entered while such a call runs share the context created for it, so
            // that a callback redirecting the call to another wrapped function cannot re-enter itself endlessly.
            var ambientContext = FunctionInvokingChatClient.CurrentContext;
            bool isDirectCall = ambientContext is null;
            var context = ambientContext
                ?? FindDirectCallContext(previous)
                ?? new FunctionInvocationContext()
                {
                    Arguments = arguments,
                    Function = this.InnerFunction,
                    CallContent = new(string.Empty, this.InnerFunction.Name, new Dictionary<string, object?>(arguments)),
                };

            // The callback can redirect the call by assigning a different function to the context.
            var targetBeforeCallback = context.Function;
            InvocationScope? scope = null;

            // A custom function wrapper can lead back to this callback during the same call. Run it only once.
            for (var active = previous; active is not null; active = active.Parent)
            {
                if (ReferenceEquals(active.Context, context) && ReferenceEquals(active.Middleware, this._middleware))
                {
                    return await CoreLogicAsync(context, cancellationToken).ConfigureAwait(false);
                }
            }

            // ChatOptions.Clone keeps function wrappers but copies the tool list into a plain collection.
            // In that case, use the callback list saved on this function.
            var middlewareChain = (context.Options?.Tools as MiddlewareEnabledTools)?.MiddlewareChain ?? this._middlewareChain;

            // Record the callback while it runs, including through wrappers that do not expose their inner function.
            scope = new InvocationScope(context, this._middleware, middlewareChain, isDirectCall, previous);
            s_invocationScope.Value = scope;

            try
            {
                return await this._middleware._delegateFunc(this._middleware.InnerAgent, context, CoreLogicAsync, cancellationToken).ConfigureAwait(false);
            }
            finally
            {
                // Execution contexts that escaped the callback still reference this scope. Mark it as finished
                // so that they cannot keep using the callbacks of a callback that already returned.
                scope.IsRunning = false;

                // Leave the context with the function it had on entry, so that the callbacks around this one and
                // the function invocation loop, which reads the function for its telemetry once the invocation
                // completed, keep seeing the function they requested.
                context.Function = targetBeforeCallback;

                // A function or callback can replace the entire tool list. Wrap the replacement before the next call.
                if (context.Options is { } options)
                {
                    MiddlewareEnabledTools.ApplyTo(options, middlewareChain);
                }
            }

            // Continue with the function the callback selected, using any arguments it changed.
            // Every callback in the chain sees the same ctx.Function: the outermost wrapper that
            // FunctionInvokingChatClient resolved from the tool list. base.InvokeCoreAsync instead continues
            // with this wrapper's inner function, which is the next step of the chain. Invoking ctx.Function
            // while it still holds that wrapper would restart the chain from the top and recurse endlessly.
            async ValueTask<object?> CoreLogicAsync(FunctionInvocationContext ctx, CancellationToken cancellationToken)
            {
                if (scope is not null)
                {
                    scope.ContinuationInvoked = true;
                }

                // The callback can call its continuation more than once, and the callbacks that run during one of
                // those calls can select their own function. Start every call from the function this callback chose.
                var target = ctx.Function;
                try
                {
                    return ReferenceEquals(target, targetBeforeCallback)
                        // The callback kept the target, so continue with the next function wrapper.
                        ? await base.InvokeCoreAsync(ctx.Arguments, cancellationToken).ConfigureAwait(false)
                        // The callback replaced the target with a function outside the chain, so invoke that instead.
                        : await target.InvokeAsync(ctx.Arguments, cancellationToken).ConfigureAwait(false);
                }
                finally
                {
                    // Undo the selection of the callbacks that ran during this call so that another call to this
                    // continuation goes through them again instead of invoking the function they selected.
                    ctx.Function = target;
                }
            }
        }

        /// <summary>Gets the context created for a direct function call that is still running, if there is one.</summary>
        private static FunctionInvocationContext? FindDirectCallContext(InvocationScope? scope)
        {
            for (; scope is not null; scope = scope.Parent)
            {
                if (scope.IsRunning)
                {
                    return scope.IsDirectCall ? scope.Context : null;
                }
            }

            return null;
        }

        private sealed class InvocationScope(
            FunctionInvocationContext context,
            FunctionInvocationDelegatingAgent middleware,
            FunctionInvocationDelegatingAgent[] middlewareChain,
            bool isDirectCall,
            InvocationScope? parent)
        {
            internal FunctionInvocationContext Context { get; } = context;
            internal FunctionInvocationDelegatingAgent Middleware { get; } = middleware;
            internal FunctionInvocationDelegatingAgent[] MiddlewareChain { get; } = middlewareChain;

            /// <summary>
            /// Gets a value indicating whether the context of this scope was created for a function that was
            /// invoked without a context from <see cref="FunctionInvokingChatClient"/>.
            /// </summary>
            internal bool IsDirectCall { get; } = isDirectCall;

            /// <summary>
            /// Gets or sets a value indicating whether the callback of this scope is still running.
            /// </summary>
            /// <remarks>
            /// Execution contexts that escape the callback keep a reference to this scope, so this state
            /// tells them apart from the scope of a callback that is still running.
            /// </remarks>
            internal bool IsRunning { get; set; } = true;

            /// <summary>Gets or sets a value indicating whether the callback of this scope called its continuation.</summary>
            internal bool ContinuationInvoked { get; set; }

            internal InvocationScope? Parent { get; } = parent;
        }
    }
}
