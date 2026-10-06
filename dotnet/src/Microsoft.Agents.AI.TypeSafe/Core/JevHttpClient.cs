// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Globalization;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Sends a <see cref="JevRequest"/> to <c>POST /v1/systemone</c> of the TypeSafe API through a System.ClientModel pipeline,
/// like <c>systemOne</c> of the official TypeSafe SDK.
/// </summary>
internal sealed class JevHttpClient
{
    private const int MaxErrorDetailLength = 500;

    private readonly ClientPipeline _pipeline;

    public JevHttpClient(ApiKeyCredential credential, ClientPipelineOptions options, Uri? endpoint, string modelId)
    {
        this.Endpoint = endpoint ?? new Uri(JevPipelineDefaults.DefaultEndpoint);
        this.ModelId = modelId;

        // The credential is applied per try, like the OpenAI client does, so a retried request is signed again.
        // Creating the pipeline freezes the options, as with any other client built from them.
        this._pipeline = ClientPipeline.Create(
            options,
            perCallPolicies: [],
            perTryPolicies: [ApiKeyAuthenticationPolicy.CreateBearerAuthorizationPolicy(credential)],
            beforeTransportPolicies: []);
    }

    /// <summary>Gets the System One endpoint that requests are sent to.</summary>
    public Uri Endpoint { get; }

    /// <summary>Gets the model that answers requests unless a call selects another.</summary>
    public string ModelId { get; }

    /// <summary>
    /// Answers a request with the configured model. The signature matches the mapping of <see cref="JevAIToolBuilder"/>.
    /// </summary>
    public Task<JevResult> SystemOneAsync(JevRequest request, IServiceProvider? services, CancellationToken cancellationToken) =>
        this.SystemOneAsync(request, this.ModelId, cancellationToken);

    /// <summary>
    /// Answers a request with the given model.
    /// </summary>
    public async Task<JevResult> SystemOneAsync(JevRequest request, string modelId, CancellationToken cancellationToken)
    {
        using PipelineMessage message = this._pipeline.CreateMessage();
        message.ResponseClassifier = JevResponseClassifier.Instance;
        message.Apply(new RequestOptions { CancellationToken = cancellationToken });

        PipelineRequest httpRequest = message.Request;
        httpRequest.Method = "POST";
        httpRequest.Uri = this.Endpoint;
        httpRequest.Headers.Set("Accept", "application/json");
        httpRequest.Headers.Set("Content-Type", "application/json");
        httpRequest.Content = BinaryContent.Create(BinaryData.FromBytes(JsonSerializer.SerializeToUtf8Bytes(
            new JevApiRequest { State = request.State, Model = modelId, Questions = request.Questions },
            JevJsonContext.Default.JevApiRequest)));

        // Transports leave the cancellation check to the HTTP handler, so a canceled call is stopped here before
        // anything is sent.
        cancellationToken.ThrowIfCancellationRequested();
        await this._pipeline.SendAsync(message).ConfigureAwait(false);

        PipelineResponse response = message.Response!;
        if (response.IsError)
        {
            // The service detail says which field was rejected, which is what the model needs to correct its
            // arguments, but the default ClientResultException message has only the status. The exception still
            // carries the response for GetRawResponse, and never the credential.
            string body = response.Content.ToString();
            string detail = body.Length > MaxErrorDetailLength ? string.Concat(body.AsSpan(0, MaxErrorDetailLength), "...") : body;
            throw new ClientResultException(
                string.Format(CultureInfo.InvariantCulture, "The Jev request failed with status {0} ({1}): {2}", response.Status, response.ReasonPhrase, detail),
                response);
        }

        return ReadResult(response.Content);
    }

    private static JevResult ReadResult(BinaryData content)
    {
        try
        {
            return JsonSerializer.Deserialize(content.ToMemory().Span, JevJsonContext.Default.JevResult)
                ?? throw new JsonException("The response body is null.");
        }
        catch (Exception ex) when (ex is JsonException or NotSupportedException)
        {
            // An answer with an unknown or missing type surfaces as NotSupportedException rather than JsonException.
            throw new JsonException($"The Jev API response could not be read: {ex.Message}", ex);
        }
    }
}
