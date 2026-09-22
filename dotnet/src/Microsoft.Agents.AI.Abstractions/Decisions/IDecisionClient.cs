// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents a decision-oriented inference client: a model or service that evaluates a piece of application state
/// against one or more bounded, typed questions and returns structured probabilistic answers.
/// </summary>
/// <remarks>
/// <para>
/// This is a different capability from generative inference. An <see cref="Microsoft.Extensions.AI.IChatClient"/>
/// produces content; an <see cref="IDecisionClient"/> produces, for each question, a probability
/// (<see cref="BinaryDecisionQuestion"/>), a selection with a probability distribution over caller-defined choices
/// (<see cref="ChoiceDecisionQuestion"/>), or a position on a caller-defined ordered scale with a distribution over its
/// levels (<see cref="ScoreDecisionQuestion"/>). The output domain of every question is declared before inference, so
/// application code consumes the answers directly instead of parsing generated text.
/// </para>
/// <para>
/// All questions in a <see cref="DecisionRequest"/> are evaluated against the same <see cref="DecisionRequest.State"/>
/// in one call. Batching heterogeneous questions is a first-class part of the contract; how a provider executes them
/// is not prescribed.
/// </para>
/// <para>
/// This abstraction is a reference implementation of the shape proposed for <c>Microsoft.Extensions.AI</c> in
/// <see href="https://github.com/dotnet/extensions/issues/7764">dotnet/extensions#7764</see>. It is experimental and is
/// expected to be replaced by the <c>Microsoft.Extensions.AI</c> type when one ships; consumers should treat the names
/// here as provisional. A model-reported probability is not an empirically calibrated accuracy unless the specific
/// provider and workload establish that property, and a probability is never an authorization decision.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public interface IDecisionClient : IDisposable
{
    /// <summary>Evaluates every question in <paramref name="request"/> against its state.</summary>
    /// <param name="request">The state to judge and the questions to ask about it.</param>
    /// <param name="options">Optional per-call options, such as a model override.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>One answer per question, keyed by <see cref="DecisionQuestion.Id"/>.</returns>
    /// <exception cref="DecisionClientException">The provider refused the request or returned an unusable response.</exception>
    Task<DecisionResponse> GetResponseAsync(DecisionRequest request, DecisionOptions? options = null, CancellationToken cancellationToken = default);

    /// <summary>Asks the client for an object of the specified type.</summary>
    /// <param name="serviceType">The type of object being requested.</param>
    /// <param name="serviceKey">An optional key that can be used to help identify the target service.</param>
    /// <returns>The found object, otherwise <see langword="null"/>.</returns>
    /// <remarks>
    /// The purpose of this method is to allow for the retrieval of strongly typed services that may be provided by the
    /// client, including itself, its <see cref="DecisionClientMetadata"/>, or any services it wraps.
    /// </remarks>
    object? GetService(Type serviceType, object? serviceKey = null);
}
