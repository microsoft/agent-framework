// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Provides an <see cref="IDecisionClient"/> for Jev, the TypeSafe System One model, which answers typed Binary,
/// Choice, and Score questions about a state with probabilities.
/// </summary>
/// <remarks>
/// <para>
/// Binary, Choice, and Score questions become Jev Noul, Choice, and Score questions. A request is checked with the
/// TypeSafe rules before it is sent, such as at most 255 Choice alternatives and 2 to 10 Score levels, and the result is
/// checked against the request before it is converted. Jev reports probabilities rounded to two decimal places, which
/// each answer declares as <see cref="DecisionPrecision.TwoDecimalPlaces"/>.
/// </para>
/// <para>
/// The response keeps the <see cref="JevResult"/> as its <see cref="DecisionResponse.RawRepresentation"/>, each answer
/// keeps its <see cref="JevResponse"/>, and Choice and Score answers carry Jev's confidence in the <c>confidence</c>
/// entry of <see cref="DecisionAnswer.AdditionalProperties"/>.
/// </para>
/// <para>
/// <see cref="IDecisionClient"/> is the decision API proposed for Microsoft.Extensions.AI. This package carries a copy
/// of it until it ships, so this client and the API are experimental.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public sealed class JevDecisionClient : IDecisionClient
{
    internal const string ProviderName = "typesafe.ai";

    private readonly JevHttpClient _client;
    private readonly DecisionClientMetadata _metadata;

    /// <summary>
    /// Initializes a new instance of the <see cref="JevDecisionClient"/> class.
    /// </summary>
    /// <param name="credential">The TypeSafe API key, sent as a bearer token.</param>
    /// <param name="options">The client and pipeline options. Defaults are used when <see langword="null"/>.</param>
    /// <exception cref="ArgumentException">
    /// <see cref="JevDecisionClientOptions.ModelId"/> is empty, or <see cref="JevDecisionClientOptions.Endpoint"/> is
    /// not an absolute URI.
    /// </exception>
    public JevDecisionClient(ApiKeyCredential credential, JevDecisionClientOptions? options = null)
        : this(CreateHttpClient(credential, options ?? new JevDecisionClientOptions()))
    {
    }

    internal JevDecisionClient(JevHttpClient client)
    {
        this._client = Throw.IfNull(client);
        this._metadata = new DecisionClientMetadata(ProviderName, client.Endpoint, client.ModelId, [DecisionKind.Binary, DecisionKind.Choice, DecisionKind.Score]);
    }

    /// <inheritdoc />
    /// <exception cref="ArgumentException">The request breaks a TypeSafe rule, such as the number of Choice alternatives.</exception>
    /// <exception cref="InvalidOperationException">The Jev result does not answer every question as asked.</exception>
    /// <exception cref="DecisionProtocolException">An answer is not a complete, correlated decision answer.</exception>
    /// <exception cref="ClientResultException">The TypeSafe API rejected the request.</exception>
    public async Task<DecisionResponse> GetResponseAsync(DecisionRequest request, DecisionOptions? options = null, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(request);

        // A caller that has Jev's own questions, such as JevChatClient, sends them unchanged, so JSON instructions and
        // criteria keep their form; the decision questions with the same IDs then only correlate the answers.
        IReadOnlyDictionary<string, JevQuestion>? jevQuestions = (options?.RawRepresentationFactory?.Invoke(this) as JevDecisionRequestOptions)?.Questions;
        var questions = new Dictionary<string, JevQuestion>(request.Questions.Count, StringComparer.Ordinal);
        foreach (DecisionQuestion question in request.Questions)
        {
            questions[question.Id] = jevQuestions is not null && jevQuestions.TryGetValue(question.Id, out JevQuestion? jevQuestion)
                ? jevQuestion
                : JevDecisionMapping.ToJevQuestion(question);
        }

        var jevRequest = new JevRequest { State = JevDecisionMapping.ToEntry(request.State), Questions = questions };
        JevContractValidator.ValidateRequest(jevRequest);

        string modelId = string.IsNullOrWhiteSpace(options?.ModelId) ? this._client.ModelId : options!.ModelId!;
        JevResult result = await this._client.SystemOneAsync(jevRequest, modelId, cancellationToken).ConfigureAwait(false);

        // The TypeSafe checks come first, so a result that answers the wrong labels fails as it does for the tool.
        JevContractValidator.ValidateResult(jevRequest, result);

        var answers = new List<DecisionAnswer>(request.Questions.Count);
        foreach (DecisionQuestion question in request.Questions)
        {
            answers.Add(JevDecisionMapping.ToDecisionAnswer(question, result.Answers[question.Id]));
        }

        return new DecisionResponse(
            request,
            answers,
            new DecisionProvenance(ProviderName, this._client.Endpoint, result.Model, precision: JevDecisionMapping.Precision),
            JevDecisionMapping.ToUsage(result.Usage),
            rawRepresentation: result);
    }

    /// <inheritdoc />
    public object? GetService(Type serviceType, object? serviceKey = null)
    {
        _ = Throw.IfNull(serviceType);

        return serviceKey is not null ? null
            : serviceType == typeof(DecisionClientMetadata) ? this._metadata
            : serviceType.IsInstanceOfType(this) ? this
            : null;
    }

    /// <inheritdoc />
    public void Dispose()
    {
        // The pipeline owns no disposable resources; its default transport shares one HttpClient per process.
    }

    private static JevHttpClient CreateHttpClient(ApiKeyCredential credential, JevDecisionClientOptions options)
    {
        _ = Throw.IfNull(credential);

        if (string.IsNullOrWhiteSpace(options.ModelId))
        {
            Throw.ArgumentException(nameof(options), $"{nameof(JevDecisionClientOptions)}.{nameof(JevDecisionClientOptions.ModelId)} must not be empty.");
        }

        if (options.Endpoint?.IsAbsoluteUri is false)
        {
            Throw.ArgumentException(nameof(options), $"{nameof(JevDecisionClientOptions)}.{nameof(JevDecisionClientOptions.Endpoint)} must be an absolute URI.");
        }

        return new JevHttpClient(credential, options, options.Endpoint, options.ModelId);
    }
}
