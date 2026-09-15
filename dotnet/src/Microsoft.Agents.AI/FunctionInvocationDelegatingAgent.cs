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
        aco.ChatClientFactory = chatClient => new FunctionMiddlewarePreservingChatClient(chatClient, this).Build(originalFactory);

        return aco;
    }

    /// <summary>
    /// Preserves the function middleware chain when tools are added or replaced during a run.
    /// </summary>
    private sealed class FunctionMiddlewarePreservingChatClient(IChatClient innerClient, FunctionInvocationDelegatingAgent middleware) : DelegatingChatClient(innerClient)
    {
        private readonly FunctionInvocationDelegatingAgent _middleware = middleware;
        private FunctionInvocationDelegatingAgent[] _middlewareChain = [middleware];

        internal IChatClient Build(Func<IChatClient, IChatClient>? originalFactory)
        {
            var builder = this.AsBuilder();

            if (originalFactory is not null)
            {
                builder.Use(originalFactory);
            }

            var pipeline = builder.Build();
            var chain = new List<FunctionInvocationDelegatingAgent>();
            for (var client = pipeline.GetService<FunctionMiddlewarePreservingChatClient>();
                 client is not null && !ReferenceEquals(client, this);
                 client = client.InnerClient.GetService<FunctionMiddlewarePreservingChatClient>())
            {
                chain.Add(client._middleware);
            }

            chain.Add(this._middleware);
            // Initialize only this request's decorator, never the shared client or caller's options.
            this._middlewareChain = [.. chain];
            return pipeline;
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
    }

    private sealed class MiddlewareEnabledTools : Collection<AITool>
    {
        private readonly FunctionInvocationDelegatingAgent[] _middleware;

        internal MiddlewareEnabledTools(IList<AITool> tools, FunctionInvocationDelegatingAgent[] middleware)
        {
            this._middleware = middleware;
            foreach (var tool in tools)
            {
                this.Add(tool);
            }
        }

        internal void ApplyTo(ChatOptions options)
        {
            if (options.Tools is { } tools &&
                (tools is not MiddlewareEnabledTools existing || !ReferenceEquals(existing._middleware, this._middleware)))
            {
                options.Tools = new MiddlewareEnabledTools(tools, this._middleware);
            }
        }

        protected override void InsertItem(int index, AITool item) => base.InsertItem(index, this.Wrap(item));

        protected override void SetItem(int index, AITool item) => base.SetItem(index, this.Wrap(item));

        private AITool Wrap(AITool tool)
        {
            if (tool is AIFunction function)
            {
                foreach (var middleware in this._middleware)
                {
                    function = MiddlewareEnabledFunction.Wrap(function, middleware);
                }

                return function;
            }

            return tool;
        }
    }

    private sealed class MiddlewareEnabledFunction(AIFunction innerFunction, FunctionInvocationDelegatingAgent middleware) : DelegatingAIFunction(innerFunction)
    {
        private readonly FunctionInvocationDelegatingAgent _middleware = middleware;

        internal static AIFunction Wrap(AIFunction function, FunctionInvocationDelegatingAgent middleware)
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

            return new MiddlewareEnabledFunction(function, middleware);
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

            var tools = context.Options?.Tools as MiddlewareEnabledTools;
            try
            {
                return await this._middleware._delegateFunc(this._middleware.InnerAgent, context, CoreLogicAsync, cancellationToken).ConfigureAwait(false);
            }
            finally
            {
                // A function or middleware can replace the entire collection during invocation.
                if (tools is not null && context.Options is { } options)
                {
                    tools.ApplyTo(options);
                }
            }

            ValueTask<object?> CoreLogicAsync(FunctionInvocationContext ctx, CancellationToken cancellationToken)
                => base.InvokeCoreAsync(ctx.Arguments, cancellationToken);
        }
    }
}
