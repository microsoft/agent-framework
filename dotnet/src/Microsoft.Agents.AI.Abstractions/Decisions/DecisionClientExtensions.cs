// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides extension methods for <see cref="IDecisionClient"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public static class DecisionClientExtensions
{
    /// <summary>
    /// Evaluates <paramref name="questions"/> against strongly typed <paramref name="state"/>, serializing the state with
    /// the supplied <paramref name="stateTypeInfo"/> so that the client's <see cref="JsonElement"/> boundary stays
    /// trimming and Native AOT friendly.
    /// </summary>
    /// <typeparam name="TState">The type of the state.</typeparam>
    /// <param name="client">The decision client.</param>
    /// <param name="state">The state to evaluate.</param>
    /// <param name="stateTypeInfo">The serialization metadata for <typeparamref name="TState"/>.</param>
    /// <param name="questions">The questions to ask about the state.</param>
    /// <param name="options">Optional per-call options.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>One answer per question, keyed by <see cref="DecisionQuestion.Id"/>.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="client"/>, <paramref name="stateTypeInfo"/>, or <paramref name="questions"/> is <see langword="null"/>.</exception>
    public static Task<DecisionResponse> GetResponseAsync<TState>(
        this IDecisionClient client,
        TState state,
        JsonTypeInfo<TState> stateTypeInfo,
        IEnumerable<DecisionQuestion> questions,
        DecisionOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(client);
        _ = Throw.IfNull(stateTypeInfo);
        _ = Throw.IfNull(questions);

        JsonElement element = JsonSerializer.SerializeToElement(state, stateTypeInfo);
        return client.GetResponseAsync(new DecisionRequest(element, questions), options, cancellationToken);
    }

    /// <summary>Asks the client for an object of the specified type.</summary>
    /// <typeparam name="TService">The type of the object to be retrieved.</typeparam>
    /// <param name="client">The decision client.</param>
    /// <param name="serviceKey">An optional key that can be used to help identify the target service.</param>
    /// <returns>The found object, otherwise <see langword="null"/>.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="client"/> is <see langword="null"/>.</exception>
    public static TService? GetService<TService>(this IDecisionClient client, object? serviceKey = null)
    {
        _ = Throw.IfNull(client);
        return client.GetService(typeof(TService), serviceKey) is TService service ? service : default;
    }
}
