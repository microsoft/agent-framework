// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;
using System.Threading;
using System.Threading.Tasks;
using Azure.Core;
using Microsoft.Agents.AI.Purview.Models.Common;
using Microsoft.Agents.AI.Purview.Models.Requests;
using Microsoft.Agents.AI.Purview.Models.Responses;
using Microsoft.Agents.AI.Purview.Serialization;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Microsoft.Agents.AI.Purview;

/// <summary>
/// Client for calling Purview APIs.
/// </summary>
internal sealed class PurviewClient : IPurviewClient
{
    private readonly TokenCredential _tokenCredential;
    private readonly HttpClient _httpClient;
    private readonly string[] _scopes;
    private readonly string _graphUri;
    private readonly ILogger _logger;

    private static PurviewException CreateExceptionForStatusCode(HttpStatusCode statusCode, string endpointName)
    {
        // .net framework does not support TooManyRequests, so we have to convert to an int.
        switch ((int)statusCode)
        {
            case 429:
                return new PurviewRateLimitException($"Rate limit exceeded for {endpointName}.");
            case 401:
            case 403:
                return new PurviewAuthenticationException($"Unauthorized access to {endpointName}. Status code: {statusCode}");
            case 402:
                return new PurviewPaymentRequiredException($"Payment required for {endpointName}. Status code: {statusCode}");
            default:
                return new PurviewRequestException(statusCode, endpointName);
        }
    }

    /// <summary>
    /// Creates a new <see cref="PurviewClient"/> instance.
    /// </summary>
    /// <param name="tokenCredential">The token credential used to authenticate with Purview.</param>
    /// <param name="purviewSettings">The settings used for purview requests.</param>
    /// <param name="httpClient">The HttpClient used to make network requests to Purview.</param>
    /// <param name="logger">The logger used to log information from the middleware.</param>
    public PurviewClient(TokenCredential tokenCredential, PurviewSettings purviewSettings, HttpClient httpClient, ILogger logger)
    {
        this._tokenCredential = tokenCredential;
        this._httpClient = httpClient;

        this._scopes = new string[] { $"https://{purviewSettings.GraphBaseUri.Host}/.default" };
        this._graphUri = purviewSettings.GraphBaseUri.ToString().TrimEnd('/');
        this._logger = logger ?? NullLogger.Instance;
    }

    private static TokenInfo ExtractTokenInfo(string tokenString)
    {
        // Split JWT and decode payload
        string[] parts = tokenString.Split('.');
        if (parts.Length < 2)
        {
            throw new PurviewRequestException("Invalid JWT access token format.");
        }

        string payload = parts[1];
        // Pad base64 string if needed
        int mod4 = payload.Length % 4;
        if (mod4 > 0)
        {
            payload += new string('=', 4 - mod4);
        }

        byte[] bytes = Convert.FromBase64String(payload.Replace('-', '+').Replace('_', '/'));
        string json = Encoding.UTF8.GetString(bytes);

        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;

        string? objectId = root.TryGetProperty("oid", out var oidProp) ? oidProp.GetString() : null;
        string? idType = root.TryGetProperty("idtyp", out var idtypProp) ? idtypProp.GetString() : null;
        string? tenant = root.TryGetProperty("tid", out var tidProp) ? tidProp.GetString() : null;
        string? clientId = root.TryGetProperty("appid", out var appidProp) ? appidProp.GetString() : null;

        string? userId = idType == "user" ? objectId : null;

        return new TokenInfo
        {
            UserId = userId,
            TenantId = tenant,
            ClientId = clientId
        };
    }

    /// <inheritdoc/>
    public async Task<TokenInfo> GetUserInfoFromTokenAsync(CancellationToken cancellationToken, string? tenantId = default)
    {
        TokenRequestContext tokenRequestContext = tenantId == null ? new(this._scopes) : new(this._scopes, tenantId: tenantId);
        AccessToken token = await this._tokenCredential.GetTokenAsync(tokenRequestContext, cancellationToken).ConfigureAwait(false);

        string tokenString = token.Token;

        return ExtractTokenInfo(tokenString);
    }

    /// <inheritdoc/>
    public async Task<ProcessContentResponse> ProcessContentAsync(ProcessContentRequest request, CancellationToken cancellationToken)
    {
        var token = await this._tokenCredential.GetTokenAsync(new TokenRequestContext(this._scopes, tenantId: request.TenantId), cancellationToken).ConfigureAwait(false);
        string userId = request.UserId;

        string uri = $"{this._graphUri}/users/{userId}/dataSecurityAndGovernance/processContent";

        using (HttpRequestMessage message = new(HttpMethod.Post, new Uri(uri)))
        {
            message.Headers.Add("Authorization", $"Bearer {token.Token}");
            message.Headers.Add("User-Agent", "agent-framework-dotnet");

            if (request.ScopeIdentifier != null)
            {
                message.Headers.Add("If-None-Match", request.ScopeIdentifier);
            }

            string content = JsonSerializer.Serialize(request, PurviewSerializationUtils.SerializationSettings.GetTypeInfo(typeof(ProcessContentRequest)));
            message.Content = new StringContent(content, Encoding.UTF8, "application/json");

            HttpResponseMessage response;
            try
            {
                response = await this._httpClient.SendAsync(message, cancellationToken).ConfigureAwait(false);
            }
            catch (HttpRequestException e)
            {
                this._logger.LogError(e, "Http error while processing content.");
                throw new PurviewRequestException("Http error occurred while processing content.", e);
            }

#if NET5_0_OR_GREATER
            // Pass the cancellation token if that method is available.
            string responseContent = await response.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
#else
            string responseContent = await response.Content.ReadAsStringAsync().ConfigureAwait(false);
#endif

            if (response.StatusCode == HttpStatusCode.OK || response.StatusCode == HttpStatusCode.Accepted)
            {
                ProcessContentResponse? deserializedResponse;
                try
                {
                    JsonTypeInfo<ProcessContentResponse> typeInfo = (JsonTypeInfo<ProcessContentResponse>)PurviewSerializationUtils.SerializationSettings.GetTypeInfo(typeof(ProcessContentResponse));
                    deserializedResponse = JsonSerializer.Deserialize(responseContent, typeInfo);
                }
                catch (JsonException jsonException)
                {
                    const string DeserializeExceptionError = "Failed to deserialize ProcessContent response.";
                    this._logger.LogError(jsonException, DeserializeExceptionError);
                    throw new PurviewRequestException(DeserializeExceptionError, jsonException);
                }

                if (deserializedResponse != null)
                {
                    return deserializedResponse;
                }

                const string DeserializeError = "Failed to deserialize ProcessContent response. Response was null.";
                this._logger.LogError(DeserializeError);
                throw new PurviewRequestException(DeserializeError);
            }

            this._logger.LogError("Failed to process content. Status code: {StatusCode}", response.StatusCode);
            throw CreateExceptionForStatusCode(response.StatusCode, "processContent");
        }
    }

    /// <inheritdoc/>
    public async Task<ProtectionScopesResponse> GetProtectionScopesAsync(ProtectionScopesRequest request, CancellationToken cancellationToken)
    {
        var token = await this._tokenCredential.GetTokenAsync(new TokenRequestContext(this._scopes), cancellationToken).ConfigureAwait(false);
        string userId = request.UserId;

        string uri = $"{this._graphUri}/users/{userId}/dataSecurityAndGovernance/protectionScopes/compute";

        using (HttpRequestMessage message = new(HttpMethod.Post, new Uri(uri)))
        {
            message.Headers.Add("Authorization", $"Bearer {token.Token}");
            message.Headers.Add("User-Agent", "agent-framework-dotnet");

            var typeinfo = PurviewSerializationUtils.SerializationSettings.GetTypeInfo(typeof(ProtectionScopesRequest));
            string content = JsonSerializer.Serialize(request, typeinfo);
            message.Content = new StringContent(content, Encoding.UTF8, "application/json");

            HttpResponseMessage response;
            try
            {
                response = await this._httpClient.SendAsync(message, cancellationToken).ConfigureAwait(false);
            }
            catch (HttpRequestException e)
            {
                this._logger.LogError(e, "Http error while retrieving protection scopes.");
                throw new PurviewRequestException("Http error occurred while retrieving protection scopes.", e);
            }

            if (response.StatusCode == HttpStatusCode.OK)
            {
#if NET5_0_OR_GREATER
                // Pass the cancellation token if that method is available.
                string responseContent = await response.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
#else
                string responseContent = await response.Content.ReadAsStringAsync().ConfigureAwait(false);
#endif
                ProtectionScopesResponse? deserializedResponse;
                try
                {
                    JsonTypeInfo<ProtectionScopesResponse> typeInfo = (JsonTypeInfo<ProtectionScopesResponse>)PurviewSerializationUtils.SerializationSettings.GetTypeInfo(typeof(ProtectionScopesResponse));
                    deserializedResponse = JsonSerializer.Deserialize(responseContent, typeInfo);
                }
                catch (JsonException jsonException)
                {
                    const string DeserializeExceptionError = "Failed to deserialize ProtectionScopes response.";
                    this._logger.LogError(jsonException, DeserializeExceptionError);
                    throw new PurviewRequestException(DeserializeExceptionError, jsonException);
                }

                if (deserializedResponse != null)
                {
                    deserializedResponse.ScopeIdentifier = response.Headers.ETag?.Tag;
                    return deserializedResponse;
                }

                const string DeserializeError = "Failed to deserialize ProtectionScopes response.";
                this._logger.LogError(DeserializeError);
                throw new PurviewRequestException(DeserializeError);
            }

            this._logger.LogError("Failed to retrieve protection scopes. Status code: {StatusCode}", response.StatusCode);
            throw CreateExceptionForStatusCode(response.StatusCode, "protectionScopes/compute");
        }
    }

    /// <inheritdoc/>
    public async Task<ContentActivitiesResponse> SendContentActivitiesAsync(ContentActivitiesRequest request, CancellationToken cancellationToken)
    {
        var token = await this._tokenCredential.GetTokenAsync(new TokenRequestContext(this._scopes), cancellationToken).ConfigureAwait(false);
        string userId = request.UserId;

        string uri = $"{this._graphUri}/{userId}/dataSecurityAndGovernance/activities/contentActivities";

        using (HttpRequestMessage message = new(HttpMethod.Post, new Uri(uri)))
        {
            message.Headers.Add("Authorization", $"Bearer {token.Token}");
            message.Headers.Add("User-Agent", "agent-framework-dotnet");
            string content = JsonSerializer.Serialize(request, PurviewSerializationUtils.SerializationSettings.GetTypeInfo(typeof(ContentActivitiesRequest)));
            message.Content = new StringContent(content, Encoding.UTF8, "application/json");
            HttpResponseMessage response;

            try
            {
                response = await this._httpClient.SendAsync(message, cancellationToken).ConfigureAwait(false);
            }
            catch (HttpRequestException e)
            {
                this._logger.LogError(e, "Http error while creating content activities.");
                throw new PurviewRequestException("Http error occurred while creating content activities.", e);
            }

            if (response.StatusCode == HttpStatusCode.Created)
            {
#if NET5_0_OR_GREATER
                // Pass the cancellation token if that method is available.
                string responseContent = await response.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
#else
                string responseContent = await response.Content.ReadAsStringAsync().ConfigureAwait(false);
#endif
                ContentActivitiesResponse? deserializedResponse;

                try
                {
                    JsonTypeInfo<ContentActivitiesResponse> typeInfo = (JsonTypeInfo<ContentActivitiesResponse>)PurviewSerializationUtils.SerializationSettings.GetTypeInfo(typeof(ContentActivitiesResponse));
                    deserializedResponse = JsonSerializer.Deserialize(responseContent, typeInfo);
                }
                catch (JsonException jsonException)
                {
                    const string DeserializeExceptionError = "Failed to deserialize ContentActivities response.";
                    this._logger.LogError(jsonException, DeserializeExceptionError);
                    throw new PurviewRequestException(DeserializeExceptionError, jsonException);
                }

                if (deserializedResponse != null)
                {
                    return deserializedResponse;
                }

                const string DeserializeError = "Failed to deserialize ContentActivities response.";
                this._logger.LogError(DeserializeError);
                throw new PurviewRequestException(DeserializeError);
            }

            this._logger.LogError("Failed to create content activities. Status code: {StatusCode}", response.StatusCode);
            throw CreateExceptionForStatusCode(response.StatusCode, "contentActivities");
        }
    }
}
