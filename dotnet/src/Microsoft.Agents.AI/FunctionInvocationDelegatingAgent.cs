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
/// Internal agent decorator that adds function invocation middleware logic.
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

    // Decorate options to add the middleware function
    private ChatClientAgentRunOptions AgentRunOptionsWithFunctionMiddleware(AgentRunOptions? options)
    {
        if (options is null || options.GetType() == typeof(AgentRunOptions))
        {
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
        aco.ChatClientFactory = chatClient => FunctionMiddlewarePreservingChatClient.Build(chatClient, originalFactory, this);

        return aco;
    }

    /// <summary>
    /// Preserves the function middleware chain when tools are added or replaced during a run.
    /// </summary>
    private sealed class FunctionMiddlewarePreservingChatClient(
        IChatClient innerClient, FunctionInvocationDelegatingAgent[] middlewareChain) : DelegatingChatClient(innerClient)
    {
        private static readonly AsyncLocal<PipelineBuildScope?> s_buildScope = new();
        private readonly FunctionInvocationDelegatingAgent[] _middlewareChain = middlewareChain;

        internal static FunctionMiddlewarePreservingChatClient Build(
            IChatClient chatClient, Func<IChatClient, IChatClient>? originalFactory, FunctionInvocationDelegatingAgent middleware)
        {
            var previous = s_buildScope.Value;
            var scope = previous is not null && ReferenceEquals(previous.RunContext, CurrentRunContext)
                ? previous
                : new PipelineBuildScope(CurrentRunContext);
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
                // Factory composition is synchronous; restore its construction scope before returning.
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
            options = options?.Clone() ?? new();
            if (options.Tools is { } tools)
            {
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
            foreach (var tool in tools)
            {
                this.Add(tool);
            }
        }

        internal FunctionInvocationDelegatingAgent[] MiddlewareChain { get; }

        internal static void ApplyTo(ChatOptions options, FunctionInvocationDelegatingAgent[] middleware)
        {
            if (options.Tools is { } tools &&
                (tools is not MiddlewareEnabledTools existing || !ReferenceEquals(existing.MiddlewareChain, middleware)))
            {
                options.Tools = new MiddlewareEnabledTools(tools, middleware);
            }
        }

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
        private static readonly AsyncLocal<InvocationScope?> s_invocationScope = new();
        private readonly FunctionInvocationDelegatingAgent _middleware = middleware;
        private readonly FunctionInvocationDelegatingAgent[] _middlewareChain = middlewareChain;

        internal static AIFunction Wrap(AIFunction function, FunctionInvocationDelegatingAgent middleware, FunctionInvocationDelegatingAgent[] middlewareChain)
        {
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
                ?? new FunctionInvocationContext() // When there is no ambient context, create a new one to hold the arguments
                {
                    Arguments = arguments,
                    Function = this.InnerFunction,
                    CallContent = new(string.Empty, this.InnerFunction.Name, new Dictionary<string, object?>(arguments)),
                };

            var previous = s_invocationScope.Value;
            for (var active = previous; active is not null; active = active.Parent)
            {
                if (ReferenceEquals(active.Context, context) && ReferenceEquals(active.Middleware, this._middleware))
                {
                    return await CoreLogicAsync(context, cancellationToken).ConfigureAwait(false);
                }
            }

            // An opaque decorator can reach an already active callback for the same invocation.
            s_invocationScope.Value = new(context, this._middleware, previous);

            // Function wrappers survive ChatOptions.Clone even when the middleware-aware collection does not.
            var middlewareChain = (context.Options?.Tools as MiddlewareEnabledTools)?.MiddlewareChain ?? this._middlewareChain;
            try
            {
                return await this._middleware._delegateFunc(this._middleware.InnerAgent, context, CoreLogicAsync, cancellationToken).ConfigureAwait(false);
            }
            finally
            {
                // A function or middleware can replace the entire collection during invocation.
                if (context.Options is { } options)
                {
                    MiddlewareEnabledTools.ApplyTo(options, middlewareChain);
                }
            }

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
