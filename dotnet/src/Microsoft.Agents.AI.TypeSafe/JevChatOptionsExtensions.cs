// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Provides extension methods that pass Jev questions through <see cref="ChatOptions"/>.
/// </summary>
public static class JevChatOptionsExtensions
{
    /// <summary>
    /// Sets the questions that a <see cref="JevChatClient"/> answers for a request.
    /// </summary>
    /// <param name="options">The chat options to configure.</param>
    /// <param name="questions">The questions to answer, keyed by an ID that the caller chooses.</param>
    /// <returns><paramref name="options"/>, for chaining.</returns>
    /// <remarks>
    /// <para>
    /// This sets <see cref="ChatOptions.RawRepresentationFactory"/> to return a <see cref="JevChatRequestOptions"/>
    /// to a <see cref="JevChatClient"/>. For any other client it calls the factory that was set before, so the same
    /// options can still carry provider options for another client. Calling this method again replaces the
    /// questions.
    /// </para>
    /// <para>
    /// With an agent, pass the options in a <c>ChatClientAgentRunOptions</c> for one run, or in the agent's
    /// <c>ChatClientAgentOptions.ChatOptions</c> for every run; the agent prefers the run's questions.
    /// </para>
    /// </remarks>
    public static ChatOptions WithJevQuestions(this ChatOptions options, IReadOnlyDictionary<string, JevQuestion> questions)
    {
        _ = Throw.IfNull(options);
        _ = Throw.IfNull(questions);

        Func<IChatClient, object?>? previous = options.RawRepresentationFactory;
        options.RawRepresentationFactory = client =>
            client is JevChatClient ? new JevChatRequestOptions { Questions = questions } : previous?.Invoke(client);
        return options;
    }
}
