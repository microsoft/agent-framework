// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Provides extension methods for adding <see cref="AIContextProvider"/> support to <see cref="ChatClientBuilder"/> instances.
/// </summary>
public static class AIContextProviderChatClientBuilderExtensions
{
    /// <summary>
    /// Adds one or more <see cref="AIContextProvider"/> instances to the chat client pipeline, enabling context enrichment
    /// (messages, tools, and instructions) for any <see cref="IChatClient"/>.
    /// </summary>
    /// <param name="builder">The <see cref="ChatClientBuilder"/> to which the providers will be added.</param>
    /// <param name="providers">
    /// The <see cref="AIContextProvider"/> instances to invoke before and after each chat client call.
    /// Providers are called in sequence, with each receiving the accumulated context from the previous provider.
    /// </param>
    /// <returns>The <see cref="ChatClientBuilder"/> with the providers added, enabling method chaining.</returns>
    /// <exception cref="System.ArgumentNullException"><paramref name="builder"/> or <paramref name="providers"/> is <see langword="null"/>.</exception>
    /// <exception cref="System.ArgumentException"><paramref name="providers"/> is empty.</exception>
    /// <remarks>
    /// <para>
    /// This method wraps the inner chat client with a decorator that calls each provider's
    /// <see cref="AIContextProvider.InvokingAsync"/> in sequence before the inner client is called,
    /// and calls <see cref="AIContextProvider.InvokedAsync"/> on each provider after the inner client completes.
    /// </para>
    /// <para>
    /// The chat client must be used within the context of a running <see cref="AIAgent"/>. The agent and session
    /// are retrieved from <see cref="AIAgent.CurrentRunContext"/>. An <see cref="System.InvalidOperationException"/>
    /// is thrown at invocation time if no run context is available.
    /// </para>
    /// <para>
    /// Providers can also be registered in other places, such as on the agent itself. The limitations below only apply to
    /// providers registered on the chat client pipeline with this method.
    /// </para>
    /// <para>
    /// Tools added by a provider registered this way are not supported when function invocation middleware is
    /// registered on the agent (for example, with <c>AIAgentBuilder.Use</c>). Those tools are not guaranteed to go
    /// through that middleware, so it cannot be relied on for security or policy checks on them.
    /// </para>
    /// <para>
    /// Separately, tools added by a provider registered this way are only run when a
    /// <see cref="FunctionInvokingChatClient"/> sits below this decorator in the pipeline. If it sits above,
    /// it does not know about those tools and will not run them.
    /// </para>
    /// </remarks>
    public static ChatClientBuilder UseAIContextProviders(this ChatClientBuilder builder, params AIContextProvider[] providers)
    {
        _ = Throw.IfNull(builder);

        return builder.Use(innerClient => new AIContextProviderChatClient(innerClient, providers));
    }
}
