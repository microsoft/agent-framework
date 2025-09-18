// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>Provides extensions for configuring <see cref="AgentInvokedChatClient"/> instances.</summary>
public static class AgentChatClientBuilderExtensions
{
    /// <summary>
    /// Enables automatic function call invocation on the chat pipeline.
    /// </summary>
    /// <remarks>This works by adding an instance of <see cref="AgentInvokedChatClient"/> with default options.</remarks>
    /// <param name="builder">The <see cref="ChatClientBuilder"/> being used to build the chat pipeline.</param>
    /// <returns>The supplied <paramref name="builder"/>.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="builder"/> is <see langword="null"/>.</exception>
    public static ChatClientBuilder UseAgentInvocation(
        this ChatClientBuilder builder)
    {
        _ = Throw.IfNull(builder);

        return builder.Use((innerClient, services) =>
            new AgentInvokedChatClient(innerClient));
    }
}
