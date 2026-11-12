// Licensed to the .NET Foundation under one or more agreements.
// The .NET Foundation licenses this file to you under the MIT license.

#pragma warning disable SA1402 // File may only contain a single type — decision client contracts are co-located as one API surface.
#pragma warning disable SA1649 // File name should match first type name — decision client contracts are co-located as one API surface.
#pragma warning disable SA1204 // Static extension types are intentionally grouped with the client contracts.
#pragma warning disable S1128 // Unused "using" should be removed — ExperimentalAttribute is supplied by the shared API contract.
#pragma warning disable S2302 // Protocol diagnostics intentionally mention the opaque question concept.
#pragma warning disable CA1032 // Implement standard exception constructors — client exceptions expose the client-specific constructors.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.Json.Serialization.Metadata;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI;

/// <summary>Provides provider-neutral decision inference over a heterogeneous question batch.</summary>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public interface IDecisionClient : IDisposable
{
    /// <summary>Evaluates all questions against the same request state.</summary>
    /// <param name="request">The owned decision request.</param>
    /// <param name="options">Optional per-request options.</param>
    /// <param name="cancellationToken">The cancellation token to monitor.</param>
    /// <returns>A complete, correlated decision response or an exception.</returns>
    Task<DecisionResponse> GetResponseAsync(
        DecisionRequest request,
        DecisionOptions? options = null,
        CancellationToken cancellationToken = default);

    /// <summary>Retrieves a provider service for the exact requested type and key.</summary>
    /// <returns>The requested provider service, or <see langword="null"/> when unavailable.</returns>
    object? GetService(Type serviceType, object? serviceKey = null);
}

/// <summary>Provides per-request decision options.</summary>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public class DecisionOptions
{
    /// <summary>Initializes a new instance of the <see cref="DecisionOptions"/> class.</summary>
    public DecisionOptions()
    {
    }

    /// <summary>Initializes a new instance of the <see cref="DecisionOptions"/> class by copying another instance.</summary>
    protected DecisionOptions(DecisionOptions? other)
    {
        if (other is null)
        {
            return;
        }

        ModelId = other.ModelId;
        AdditionalProperties = other.AdditionalProperties?.Clone();
        RawRepresentationFactory = other.RawRepresentationFactory;
    }

    /// <summary>Gets or sets the requested model ID.</summary>
    public string? ModelId { get; set; }

    /// <summary>Gets or sets provider-specific extension properties.</summary>
    public AdditionalPropertiesDictionary? AdditionalProperties { get; set; }

    /// <summary>
    /// Gets or sets a callback that creates provider-specific raw options.
    /// The callback should return a new instance for each invocation; the provider may mutate it.
    /// </summary>
    [JsonIgnore]
    public Func<IDecisionClient, object?>? RawRepresentationFactory { get; set; }

    /// <summary>Creates a deliberate shallow clone of these options.</summary>
    /// <returns>A cloned options instance.</returns>
    public virtual DecisionOptions Clone() => new(this);
}

/// <summary>Provides metadata about an <see cref="IDecisionClient"/>.</summary>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public sealed class DecisionClientMetadata
{
    /// <summary>Initializes a new instance of the <see cref="DecisionClientMetadata"/> class.</summary>
    public DecisionClientMetadata(
        string? providerName = null,
        Uri? providerUri = null,
        string? defaultModelId = null,
        IReadOnlyList<DecisionKind>? supportedKinds = null)
    {
        ProviderName = providerName;
        ProviderUri = providerUri;
        DefaultModelId = defaultModelId;

        if (supportedKinds is not null)
        {
            DecisionKind[] copy = supportedKinds.Distinct().ToArray();
            foreach (DecisionKind kind in copy)
            {
                if (!Enum.IsDefined(typeof(DecisionKind), kind))
                {
                    Throw.ArgumentException(nameof(supportedKinds), "Supported kinds must be defined decision kinds.");
                }
            }

            SupportedKinds = Array.AsReadOnly(copy);
        }
    }

    /// <summary>Gets the provider name, when known.</summary>
    public string? ProviderName { get; }

    /// <summary>Gets the provider URI, when known.</summary>
    public Uri? ProviderUri { get; }

    /// <summary>Gets the default model ID, when known.</summary>
    public string? DefaultModelId { get; }

    /// <summary>Gets the owned supported-kind snapshot, or <see langword="null"/> when unknown.</summary>
    public IReadOnlyList<DecisionKind>? SupportedKinds { get; }
}

/// <summary>Classifies a provider failure without prescribing retry behavior.</summary>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public sealed class DecisionClientException : Exception
{
    /// <summary>Initializes a new instance of the <see cref="DecisionClientException"/> class.</summary>
    public DecisionClientException()
        : this(string.Empty, isTransient: false)
    {
    }

    /// <summary>Initializes a new instance of the <see cref="DecisionClientException"/> class with a message.</summary>
    public DecisionClientException(string message)
        : this(message, isTransient: false)
    {
    }

    /// <summary>Initializes a new instance of the <see cref="DecisionClientException"/> class with provider classification.</summary>
    public DecisionClientException(string message, bool isTransient, Exception? innerException = null)
        : base(message, innerException)
    {
        IsTransient = isTransient;
    }

    /// <summary>Initializes a new instance of the <see cref="DecisionClientException"/> class with a message and inner exception.</summary>
    public DecisionClientException(string message, Exception innerException)
        : this(message, isTransient: false, innerException)
    {
    }

    /// <summary>Gets a value indicating whether the provider classified the failure as transient.</summary>
    public bool IsTransient { get; }
}

/// <summary>Provides extensions for decision clients.</summary>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public static class DecisionClientExtensions
{
    /// <summary>Gets a typed provider service, or <see langword="null"/> when it is unavailable.</summary>
    /// <typeparam name="TService">The provider service type.</typeparam>
    /// <returns>The requested provider service, or <see langword="null"/> when unavailable.</returns>
    public static TService? GetService<TService>(this IDecisionClient client, object? serviceKey = null)
    {
        _ = Throw.IfNull(client);
        return client.GetService(typeof(TService), serviceKey) is TService service ? service : default;
    }

    /// <summary>Evaluates typed state using an explicit source-generated JSON contract.</summary>
    /// <typeparam name="TState">The application state type.</typeparam>
    /// <returns>A complete, correlated decision response.</returns>
    public static async Task<DecisionResponse> GetResponseAsync<TState>(
        this IDecisionClient client,
        TState state,
        JsonTypeInfo<TState> stateTypeInfo,
        IEnumerable<DecisionQuestion> questions,
        DecisionOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(client);
        _ = Throw.IfNull(stateTypeInfo);

        DecisionRequest request = DecisionRequest.Create(state, stateTypeInfo, questions);
        DecisionResponse response = await client.GetResponseAsync(request, options, cancellationToken).ConfigureAwait(false);
        response.ValidateAgainst(request);
        return response;
    }

    /// <summary>Evaluates a JSON state using a reusable typed decision definition.</summary>
    /// <typeparam name="TResult">The application-owned result type.</typeparam>
    /// <param name="client">The decision client.</param>
    /// <param name="state">The explicit JSON state evaluated by every declared question.</param>
    /// <param name="definition">The immutable typed decision definition.</param>
    /// <param name="options">Optional per-request options.</param>
    /// <param name="cancellationToken">The cancellation token to monitor.</param>
    /// <returns>The typed result and complete neutral evidence.</returns>
    public static async Task<DecisionResponse<TResult>> GetResponseAsync<TResult>(
        this IDecisionClient client,
        JsonElement state,
        DecisionDefinition<TResult> definition,
        DecisionOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(client);
        _ = Throw.IfNull(definition);

        DecisionRequest request = new(state, definition.Questions);
        DecisionResponse response = await client.GetResponseAsync(
            request,
            options,
            cancellationToken).ConfigureAwait(false);
        return definition.Bind(response, request);
    }

    /// <summary>Evaluates typed application state using a reusable typed decision definition.</summary>
    /// <typeparam name="TState">The application state type.</typeparam>
    /// <typeparam name="TResult">The application-owned result type.</typeparam>
    /// <param name="client">The decision client.</param>
    /// <param name="state">The application-owned state.</param>
    /// <param name="definition">The immutable typed decision definition.</param>
    /// <param name="options">Optional per-request options.</param>
    /// <param name="cancellationToken">The cancellation token to monitor.</param>
    /// <returns>The typed result and complete neutral evidence.</returns>
    public static Task<DecisionResponse<TResult>> GetResponseAsync<TState, TResult>(
        this IDecisionClient client,
        TState state,
        DecisionDefinition<TResult> definition,
        DecisionOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(definition);
        return GetResponseAsync(
            client,
            state,
            definition,
            definition.SerializerOptions,
            options,
            cancellationToken);
    }

    /// <summary>Evaluates typed application state using explicit source-generated state metadata.</summary>
    /// <typeparam name="TState">The application state type.</typeparam>
    /// <typeparam name="TResult">The application-owned result type.</typeparam>
    /// <param name="client">The decision client.</param>
    /// <param name="state">The application-owned state.</param>
    /// <param name="stateTypeInfo">The JSON contract for <typeparamref name="TState"/>.</param>
    /// <param name="definition">The immutable typed decision definition.</param>
    /// <param name="options">Optional per-request options.</param>
    /// <param name="cancellationToken">The cancellation token to monitor.</param>
    /// <returns>The typed result and complete neutral evidence.</returns>
    public static Task<DecisionResponse<TResult>> GetResponseAsync<TState, TResult>(
        this IDecisionClient client,
        TState state,
        JsonTypeInfo<TState> stateTypeInfo,
        DecisionDefinition<TResult> definition,
        DecisionOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(stateTypeInfo);
        return GetResponseAsync(
            client,
            state,
            definition,
            stateTypeInfo,
            options,
            cancellationToken);
    }

    private static async Task<DecisionResponse<TResult>> GetResponseAsync<TState, TResult>(
        IDecisionClient client,
        TState state,
        DecisionDefinition<TResult> definition,
        JsonSerializerOptions serializerOptions,
        DecisionOptions? options,
        CancellationToken cancellationToken)
    {
        _ = Throw.IfNull(client);
        _ = Throw.IfNull(definition);

        JsonTypeInfo stateTypeInfo = serializerOptions.GetTypeInfo(typeof(TState));
        JsonElement stateJson = JsonSerializer.SerializeToElement(state, stateTypeInfo);
        return await GetResponseAsync(client, stateJson, definition, options, cancellationToken).ConfigureAwait(false);
    }

    private static async Task<DecisionResponse<TResult>> GetResponseAsync<TState, TResult>(
        IDecisionClient client,
        TState state,
        DecisionDefinition<TResult> definition,
        JsonTypeInfo<TState> stateTypeInfo,
        DecisionOptions? options,
        CancellationToken cancellationToken)
    {
        _ = Throw.IfNull(client);
        _ = Throw.IfNull(definition);

        JsonElement stateJson = JsonSerializer.SerializeToElement(state, stateTypeInfo);
        return await GetResponseAsync(client, stateJson, definition, options, cancellationToken).ConfigureAwait(false);
    }
}

/// <summary>Identifies provider/model provenance without inventing missing identity.</summary>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public sealed class DecisionProvenance
{
    /// <summary>Initializes a new instance of the <see cref="DecisionProvenance"/> class.</summary>
    public DecisionProvenance(
        string? providerName = null,
        Uri? providerUri = null,
        string? modelId = null,
        string? responseId = null,
        DecisionPrecision? precision = null)
    {
        ProviderName = providerName;
        ProviderUri = providerUri;
        ModelId = modelId;
        ResponseId = responseId;
        Precision = precision;
    }

    /// <summary>Gets the provider name, when reported.</summary>
    public string? ProviderName { get; }

    /// <summary>Gets the provider URI, when reported.</summary>
    public Uri? ProviderUri { get; }

    /// <summary>Gets the model ID, when reported.</summary>
    public string? ModelId { get; }

    /// <summary>Gets the provider response ID, when reported.</summary>
    public string? ResponseId { get; }

    /// <summary>Gets the reported probability precision, when available.</summary>
    public DecisionPrecision? Precision { get; }
}

/// <summary>Represents a complete response correlated to one request.</summary>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public sealed class DecisionResponse
{
    /// <summary>Initializes a new instance of the <see cref="DecisionResponse"/> class and validates it.</summary>
    [JsonConstructor]
    public DecisionResponse(
        DecisionRequest request,
        IReadOnlyList<DecisionAnswer> answers,
        DecisionProvenance? provenance = null,
        UsageDetails? usage = null,
        object? rawRepresentation = null,
        IReadOnlyDictionary<string, object?>? additionalProperties = null)
    {
        Request = Throw.IfNull(request);
        _ = Throw.IfNull(answers);

        DecisionAnswer[] copy = answers.ToArray();
        if (copy.Length != request.Questions.Count)
        {
            throw new DecisionProtocolException("A response must contain one answer for every question.");
        }

        for (int i = 0; i < copy.Length; i++)
        {
            ValidateAnswer(request.Questions[i], copy[i]);
        }

        Answers = Array.AsReadOnly(copy);
        Provenance = provenance;
        Usage = usage;
        RawRepresentation = rawRepresentation;
        AdditionalProperties = DecisionSnapshots.Properties(additionalProperties);
    }

    /// <summary>Gets the request snapshot evaluated by the provider.</summary>
    public DecisionRequest Request { get; }

    /// <summary>Gets complete answers in the exact request order.</summary>
    public IReadOnlyList<DecisionAnswer> Answers { get; }

    /// <summary>Gets provider/model provenance, when reported.</summary>
    public DecisionProvenance? Provenance { get; }

    /// <summary>Gets usage details reported by the provider.</summary>
    public UsageDetails? Usage { get; }

    /// <summary>
    /// Gets the provider-owned raw response, if available.
    /// This value is not cloned or used for semantic data and must be treated as diagnostic-only.
    /// </summary>
    [JsonIgnore]
    public object? RawRepresentation { get; }

    /// <summary>
    /// Gets an owned read-only snapshot of provider extension data.
    /// Values are shallow-copied references and must be independently safe to share.
    /// </summary>
    public IReadOnlyDictionary<string, object?>? AdditionalProperties { get; }

    /// <summary>Gets an answer by exact ordinal question ID.</summary>
    /// <returns>The answer associated with the exact question ID.</returns>
    public DecisionAnswer GetAnswer(string questionId)
    {
        _ = Throw.IfNullOrWhitespace(questionId);
        foreach (DecisionAnswer answer in Answers)
        {
            if (string.Equals(answer.QuestionId, questionId, StringComparison.Ordinal))
            {
                return answer;
            }
        }

        throw new KeyNotFoundException($"No answer exists for question ID '{questionId}'.");
    }

    internal void ValidateAgainst(DecisionRequest expectedRequest)
    {
        _ = Throw.IfNull(expectedRequest);

        if (!JsonElement.DeepEquals(Request.State, expectedRequest.State) ||
            Request.Questions.Count != expectedRequest.Questions.Count)
        {
            throw new DecisionProtocolException("The response does not correspond to the request sent by the client.");
        }

        for (int i = 0; i < Request.Questions.Count; i++)
        {
            if (!QuestionsAreEquivalent(Request.Questions[i], expectedRequest.Questions[i]))
            {
                throw new DecisionProtocolException("The response does not correspond to the request sent by the client.");
            }
        }
    }

    private static bool QuestionsAreEquivalent(DecisionQuestion actual, DecisionQuestion expected)
    {
        if (actual.Kind != expected.Kind ||
            !string.Equals(actual.Id, expected.Id, StringComparison.Ordinal) ||
            !string.Equals(actual.Instructions, expected.Instructions, StringComparison.Ordinal))
        {
            return false;
        }

        return (actual, expected) switch
        {
            (BinaryDecisionQuestion actualBinary, BinaryDecisionQuestion expectedBinary) =>
                string.Equals(actualBinary.TrueDescription, expectedBinary.TrueDescription, StringComparison.Ordinal) &&
                string.Equals(actualBinary.FalseDescription, expectedBinary.FalseDescription, StringComparison.Ordinal),

            (ChoiceDecisionQuestion actualChoice, ChoiceDecisionQuestion expectedChoice) =>
                CandidatesAreEquivalent(actualChoice.Candidates, expectedChoice.Candidates),

            (ScoreDecisionQuestion actualScore, ScoreDecisionQuestion expectedScore) =>
                LevelsAreEquivalent(actualScore.Levels, expectedScore.Levels),

            _ => false,
        };
    }

    private static bool CandidatesAreEquivalent(
        IReadOnlyList<DecisionCandidate> actual,
        IReadOnlyList<DecisionCandidate> expected)
    {
        if (actual.Count != expected.Count)
        {
            return false;
        }

        for (int i = 0; i < actual.Count; i++)
        {
            if (!string.Equals(actual[i].Id, expected[i].Id, StringComparison.Ordinal) ||
                !string.Equals(actual[i].Description, expected[i].Description, StringComparison.Ordinal))
            {
                return false;
            }
        }

        return true;
    }

    private static bool LevelsAreEquivalent(
        IReadOnlyList<DecisionScoreLevel> actual,
        IReadOnlyList<DecisionScoreLevel> expected)
    {
        if (actual.Count != expected.Count)
        {
            return false;
        }

        for (int i = 0; i < actual.Count; i++)
        {
            if (!string.Equals(actual[i].Id, expected[i].Id, StringComparison.Ordinal) ||
                !string.Equals(actual[i].Description, expected[i].Description, StringComparison.Ordinal))
            {
                return false;
            }
        }

        return true;
    }

    private static void ValidateAnswer(DecisionQuestion question, DecisionAnswer answer)
    {
        if (answer is null ||
            !string.Equals(question.Id, answer.QuestionId, StringComparison.Ordinal) ||
            question.Kind != answer.Kind)
        {
            throw new DecisionProtocolException("An answer does not exactly match its question.");
        }

        switch (question)
        {
            case BinaryDecisionQuestion when answer is BinaryDecisionAnswer:
                return;

            case ChoiceDecisionQuestion choice when answer is ChoiceDecisionAnswer choiceAnswer:
                if (choiceAnswer.Probabilities.Count != choice.Candidates.Count ||
                    !choice.Candidates.Select(static candidate => candidate.Id)
                        .SequenceEqual(
                            choiceAnswer.Probabilities.Select(static probability => probability.Id),
                            StringComparer.Ordinal))
                {
                    throw new DecisionProtocolException(
                        "Choice probabilities must contain exactly the requested candidate IDs in order.");
                }

                return;

            case ScoreDecisionQuestion score when answer is ScoreDecisionAnswer scoreAnswer:
                if (scoreAnswer.Probabilities.Count != score.Levels.Count ||
                    !score.Levels.Select(static level => level.Id)
                        .SequenceEqual(
                            scoreAnswer.Probabilities.Select(static probability => probability.Id),
                            StringComparer.Ordinal))
                {
                    throw new DecisionProtocolException(
                        "Score probabilities must contain exactly the requested level IDs in order.");
                }

                return;

            default:
                throw new DecisionProtocolException("An answer kind does not match its question.");
        }
    }
}
