// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Answers provider-neutral decision requests with Jev, through <c>POST /v1/systemone</c> of the TypeSafe API.
/// </summary>
/// <remarks>
/// <para>
/// Binary, Choice, and Score questions become Noul, Choice, and Score questions (see <see cref="JevDecisionMapping"/>).
/// A request is checked with the TypeSafe rules before it is sent, and the result is checked against the request before
/// it is converted, as the chat client and the tool already do. The response keeps the <see cref="JevResult"/> as its
/// raw representation, each answer keeps its <see cref="JevResponse"/>, and Choice and Score answers carry Jev's
/// confidence as the <c>confidence</c> additional property.
/// </para>
/// <para>
/// <see cref="IDecisionClient"/> is a proposed Microsoft.Extensions.AI API that this package compiles from an internal
/// copy, so this client is internal; <see cref="JevChatClient"/> is built on it. Once the API ships, this client can
/// become public.
/// </para>
/// </remarks>
internal sealed class JevDecisionClient : IDecisionClient
{
    public const string ProviderName = "typesafe.ai";

    private readonly JevHttpClient _client;
    private readonly DecisionClientMetadata _metadata;

    public JevDecisionClient(JevHttpClient client)
    {
        this._client = Throw.IfNull(client);
        this._metadata = new DecisionClientMetadata(ProviderName, client.Endpoint, client.ModelId, [DecisionKind.Binary, DecisionKind.Choice, DecisionKind.Score]);
    }

    /// <inheritdoc />
    /// <exception cref="ArgumentException">The request breaks a TypeSafe rule, such as the number of Choice alternatives.</exception>
    /// <exception cref="InvalidOperationException">The Jev result does not answer every question as asked.</exception>
    /// <exception cref="DecisionProtocolException">An answer is not a complete, correlated decision answer.</exception>
    /// <exception cref="System.ClientModel.ClientResultException">The TypeSafe API rejected the request.</exception>
    public async Task<DecisionResponse> GetResponseAsync(DecisionRequest request, DecisionOptions? options = null, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(request);

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
}
