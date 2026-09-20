// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// An <see cref="IDecisionClient"/> for TypeSafe AI's System One decision models (Jev), speaking the System One HTTP
/// protocol: one <c>POST</c> carrying <c>{ model, state, questions }</c>, one reply carrying <c>{ model, answers, usage }</c>.
/// </summary>
/// <remarks>
/// <para>
/// The provider-neutral question kinds map onto the protocol's primitives: <see cref="BinaryDecisionQuestion"/> to
/// <c>noul</c>, <see cref="ChoiceDecisionQuestion"/> to <c>choice</c>, and <see cref="ScoreDecisionQuestion"/> to
/// <c>score</c>. All questions in a request are sent in one call. The protocol accepts text-only state (a string, a
/// JSON object, or an array of text) of up to roughly 32k tokens, at most 255 choices per choice question, and 2 to 10
/// levels per score question; the client rejects requests that exceed those provider limits before sending them.
/// </para>
/// <para>
/// <strong>Strict parsing.</strong> Every question must come back with an answer of the matching kind, every probability
/// must be finite and within 0 to 1, and a choice answer must select one of the requested choices; anything else is a
/// <see cref="DecisionClientException"/> with <see cref="DecisionFailureKind.InvalidResponse"/>, never a fabricated value.
/// A binary answer carries no confidence because the protocol does not return one.
/// </para>
/// <para>
/// <strong>No hidden retries.</strong> Rate limiting (429) and overload (529) are thrown with
/// <see cref="DecisionClientException.IsTransient"/> set so the caller can back off deliberately and account for it.
/// The API key is never included in an exception message; provider bodies quoted in messages are redacted and bounded.
/// </para>
/// <para>
/// <strong>Security considerations:</strong> the state of every request is sent to an external inference service. Send
/// only what the questions need, and only configure a provider you trust with that data. The returned probabilities are
/// model-reported values, not calibrated guarantees, and must not be used as an authorization decision.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class TypeSafeDecisionClient : IDecisionClient
{
    private readonly HttpClient _httpClient;
    private readonly bool _ownsHttpClient;
    private readonly string _apiKey;
    private readonly Uri _endpoint;
    private readonly string _modelId;
    private readonly DecisionClientMetadata _metadata;

    /// <summary>
    /// Initializes a new instance of the <see cref="TypeSafeDecisionClient"/> class.
    /// </summary>
    /// <param name="apiKey">The TypeSafe API key (or the relay's key when <see cref="TypeSafeDecisionClientOptions.Endpoint"/> targets a relay).</param>
    /// <param name="options">Optional configuration. When <see langword="null"/>, defaults are used.</param>
    /// <param name="httpClient">
    /// An optional caller-owned <see cref="HttpClient"/>, for example one with a resilience pipeline or a test handler.
    /// When <see langword="null"/>, the client creates and owns one with <see cref="TypeSafeDecisionClientOptions.Timeout"/>.
    /// </param>
    /// <exception cref="ArgumentNullException"><paramref name="apiKey"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException"><paramref name="apiKey"/> is empty or whitespace, or the configured endpoint or model identifier is invalid.</exception>
    public TypeSafeDecisionClient(string apiKey, TypeSafeDecisionClientOptions? options = null, HttpClient? httpClient = null)
    {
        this._apiKey = Throw.IfNullOrWhitespace(apiKey);

        Uri endpoint = options?.Endpoint ?? new Uri(TypeSafeDecisionClientOptions.DefaultEndpoint);
        if (!endpoint.IsAbsoluteUri)
        {
            throw new ArgumentException("The endpoint must be an absolute URL.", nameof(options));
        }

        if (endpoint.Scheme != Uri.UriSchemeHttps && !endpoint.IsLoopback)
        {
            throw new ArgumentException("The endpoint must use https; a loopback http address is allowed for local testing.", nameof(options));
        }

        string modelId = options?.ModelId ?? TypeSafeDecisionClientOptions.DefaultModelId;
        if (string.IsNullOrWhiteSpace(modelId))
        {
            throw new ArgumentException("The model identifier must not be empty.", nameof(options));
        }

        this._endpoint = endpoint;
        this._modelId = modelId;
        this._ownsHttpClient = httpClient is null;
        this._httpClient = httpClient ?? new HttpClient { Timeout = options?.Timeout ?? TimeSpan.FromSeconds(60) };
        this._metadata = new DecisionClientMetadata("typesafe", endpoint, modelId);

        FeatureUsageMarker.MarkUsed();
    }

    /// <summary>Gets the request URL this client posts to.</summary>
    public Uri Endpoint => this._endpoint;

    /// <summary>Gets the model identifier sent when a request does not override it.</summary>
    public string ModelId => this._modelId;

    /// <inheritdoc />
    public async Task<DecisionResponse> GetResponseAsync(DecisionRequest request, DecisionOptions? options = null, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(request);

        string modelId = options?.ModelId ?? this._modelId;
        string json = TypeSafeProtocol.SerializeRequest(request, modelId);

        using var message = new HttpRequestMessage(HttpMethod.Post, this._endpoint)
        {
            Content = new StringContent(json, Encoding.UTF8, "application/json"),
        };
        message.Headers.Authorization = new AuthenticationHeaderValue("Bearer", this._apiKey);
        message.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));

        string host = this._endpoint.Host;
        HttpResponseMessage response;
        try
        {
            response = await this._httpClient.SendAsync(message, HttpCompletionOption.ResponseContentRead, cancellationToken).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (OperationCanceledException ex)
        {
            // HttpClient reports its own timeout as a cancellation the caller did not request.
            throw new DecisionClientException(
                DecisionFailureKind.ProviderUnavailable,
                $"The decision call to {host} timed out after {this._httpClient.Timeout.TotalSeconds:F0}s without a response.",
                innerException: ex);
        }
        catch (HttpRequestException ex)
        {
            throw new DecisionClientException(DecisionFailureKind.Unknown, $"The decision call to {host} failed before a response: {ex.Message}", innerException: ex);
        }

        using (response)
        {
#if NET
            string body = await response.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
#else
            string body = await response.Content.ReadAsStringAsync().ConfigureAwait(false);
#endif

            if (!response.IsSuccessStatusCode)
            {
                // A provider that echoes the request in an error body would otherwise put the bearer token into our own
                // exception message. Only error bodies are excerpted, so only they are redacted; a success body is
                // parsed verbatim and never quoted.
                throw TypeSafeProtocol.ClassifyFailure((int)response.StatusCode, body.Replace(this._apiKey, "[redacted]"), host);
            }

            return TypeSafeProtocol.ParseResponse(body, request, host);
        }
    }

    /// <inheritdoc />
    public object? GetService(Type serviceType, object? serviceKey = null)
    {
        _ = Throw.IfNull(serviceType);

        return serviceKey is null && serviceType.IsInstanceOfType(this) ? this
            : serviceKey is null && serviceType.IsInstanceOfType(this._metadata) ? this._metadata
            : null;
    }

    /// <inheritdoc />
    public void Dispose()
    {
        if (this._ownsHttpClient)
        {
            this._httpClient.Dispose();
        }
    }
}
