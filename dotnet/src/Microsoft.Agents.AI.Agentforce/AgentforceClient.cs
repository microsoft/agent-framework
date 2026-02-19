// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.Json.Serialization.Metadata;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Agentforce;

/// <summary>
/// HTTP client for the Salesforce Agentforce REST API.
/// Handles OAuth authentication, token caching, session lifecycle, and messaging.
/// </summary>
public sealed class AgentforceClient : IDisposable
{
    private const string AgentApiBaseUrl = "https://api.salesforce.com/einstein/ai-agent/v1";
    private static readonly TimeSpan s_tokenRefreshInterval = TimeSpan.FromMinutes(110);

    private readonly AgentforceConfig _config;
    private readonly HttpClient _httpClient;
    private readonly bool _ownsHttpClient;
    private readonly SemaphoreSlim _tokenLock = new(1, 1);

    private CachedToken? _cachedToken;
    private bool _disposed;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentforceClient"/> class.
    /// </summary>
    /// <param name="config">The Agentforce configuration containing credentials and agent identity.</param>
    /// <param name="httpClient">
    /// An optional <see cref="HttpClient"/> to use for HTTP requests.
    /// If not provided, a new instance will be created and owned by this client.
    /// </param>
    public AgentforceClient(AgentforceConfig config, HttpClient? httpClient = null)
    {
        this._config = Throw.IfNull(config);

        if (httpClient is not null)
        {
            this._httpClient = httpClient;
            this._ownsHttpClient = false;
        }
        else
        {
            this._httpClient = new HttpClient();
            this._ownsHttpClient = true;
        }
    }

    /// <summary>
    /// Creates a new conversation session with the Agentforce agent.
    /// </summary>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A <see cref="CreateSessionResponse"/> containing the Salesforce-assigned session ID and any greeting messages.</returns>
    /// <exception cref="AgentforceApiException">Thrown when the Agentforce API returns an error response.</exception>
    public async Task<CreateSessionResponse> CreateSessionAsync(CancellationToken cancellationToken = default)
    {
        string accessToken = await this.GetAccessTokenAsync(cancellationToken).ConfigureAwait(false);
        string externalSessionKey = Guid.NewGuid().ToString();

        var requestBody = new CreateSessionRequest
        {
            ExternalSessionKey = externalSessionKey,
            InstanceConfig = new InstanceConfig { Endpoint = this._config.InstanceEndpoint.ToString() },
            StreamingCapabilities = new StreamingCapabilities { ChunkTypes = new[] { "Text" } },
            BypassUser = true,
        };

        string url = $"{AgentApiBaseUrl}/agents/{this._config.AgentId}/sessions";

        using var request = new HttpRequestMessage(HttpMethod.Post, url);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", accessToken);
        request.Content = CreateJsonContent(requestBody);

        using HttpResponseMessage response = await this._httpClient.SendAsync(request, cancellationToken).ConfigureAwait(false);
        string responseBody = await response.Content.ReadAsStringAsync(
#if !NETSTANDARD2_0 && !NET472
            cancellationToken
#endif
        ).ConfigureAwait(false);

        if (!response.IsSuccessStatusCode)
        {
            await ThrowApiExceptionAsync(response, responseBody).ConfigureAwait(false);
        }

        return (CreateSessionResponse?)JsonSerializer.Deserialize(responseBody, AgentforceJsonUtilities.DefaultOptions.GetTypeInfo(typeof(CreateSessionResponse)))
            ?? throw new AgentforceApiException("Failed to deserialize session creation response.");
    }

    /// <summary>
    /// Sends a user message to the Agentforce agent within an existing session.
    /// </summary>
    /// <param name="sessionId">The session ID returned from <see cref="CreateSessionAsync"/>.</param>
    /// <param name="text">The user's message text.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A <see cref="SendMessageResponse"/> containing the agent's response messages.</returns>
    /// <exception cref="AgentforceApiException">Thrown when the Agentforce API returns an error response.</exception>
    public async Task<SendMessageResponse> SendMessageAsync(string sessionId, string text, CancellationToken cancellationToken = default)
    {
        Throw.IfNullOrWhitespace(sessionId);
        Throw.IfNullOrWhitespace(text);

        string accessToken = await this.GetAccessTokenAsync(cancellationToken).ConfigureAwait(false);

        var requestBody = new SendMessageRequest
        {
            Message = new MessagePayload
            {
                SequenceId = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
                Type = "Text",
                Text = text,
            },
        };

        string url = $"{AgentApiBaseUrl}/sessions/{sessionId}/messages";

        using var request = new HttpRequestMessage(HttpMethod.Post, url);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", accessToken);
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        request.Content = CreateJsonContent(requestBody);

        using HttpResponseMessage response = await this._httpClient.SendAsync(request, cancellationToken).ConfigureAwait(false);
        string responseBody = await response.Content.ReadAsStringAsync(
#if !NETSTANDARD2_0 && !NET472
            cancellationToken
#endif
        ).ConfigureAwait(false);

        if (!response.IsSuccessStatusCode)
        {
            // On 401, attempt token refresh and retry once.
            if (response.StatusCode == System.Net.HttpStatusCode.Unauthorized)
            {
                this.InvalidateCachedToken();
                accessToken = await this.GetAccessTokenAsync(cancellationToken).ConfigureAwait(false);

                using var retryRequest = new HttpRequestMessage(HttpMethod.Post, url);
                retryRequest.Headers.Authorization = new AuthenticationHeaderValue("Bearer", accessToken);
                retryRequest.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
                retryRequest.Content = CreateJsonContent(requestBody);

                using HttpResponseMessage retryResponse = await this._httpClient.SendAsync(retryRequest, cancellationToken).ConfigureAwait(false);
                string retryBody = await retryResponse.Content.ReadAsStringAsync(
#if !NETSTANDARD2_0 && !NET472
                    cancellationToken
#endif
                ).ConfigureAwait(false);

                if (!retryResponse.IsSuccessStatusCode)
                {
                    await ThrowApiExceptionAsync(retryResponse, retryBody).ConfigureAwait(false);
                }

                return (SendMessageResponse?)JsonSerializer.Deserialize(retryBody, AgentforceJsonUtilities.DefaultOptions.GetTypeInfo(typeof(SendMessageResponse)))
                    ?? throw new AgentforceApiException("Failed to deserialize message response.");
            }

            await ThrowApiExceptionAsync(response, responseBody).ConfigureAwait(false);
        }

        return (SendMessageResponse?)JsonSerializer.Deserialize(responseBody, AgentforceJsonUtilities.DefaultOptions.GetTypeInfo(typeof(SendMessageResponse)))
            ?? throw new AgentforceApiException("Failed to deserialize message response.");
    }

    /// <summary>
    /// Terminates an active Agentforce session.
    /// </summary>
    /// <param name="sessionId">The session ID to terminate.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A task representing the asynchronous operation.</returns>
    /// <exception cref="AgentforceApiException">Thrown when the Agentforce API returns an error response.</exception>
    public async Task EndSessionAsync(string sessionId, CancellationToken cancellationToken = default)
    {
        Throw.IfNullOrWhitespace(sessionId);

        string accessToken = await this.GetAccessTokenAsync(cancellationToken).ConfigureAwait(false);

        string url = $"{AgentApiBaseUrl}/sessions/{sessionId}";

        using var request = new HttpRequestMessage(HttpMethod.Delete, url);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", accessToken);

        using HttpResponseMessage response = await this._httpClient.SendAsync(request, cancellationToken).ConfigureAwait(false);

        if (!response.IsSuccessStatusCode)
        {
            string responseBody = await response.Content.ReadAsStringAsync(
#if !NETSTANDARD2_0 && !NET472
                cancellationToken
#endif
            ).ConfigureAwait(false);

            await ThrowApiExceptionAsync(response, responseBody).ConfigureAwait(false);
        }
    }

    /// <inheritdoc />
    public void Dispose()
    {
        if (!this._disposed)
        {
            this._disposed = true;

            if (this._ownsHttpClient)
            {
                this._httpClient.Dispose();
            }

            this._tokenLock.Dispose();
        }
    }

    /// <summary>
    /// Gets a valid access token, refreshing if necessary.
    /// Thread-safe with lock to prevent thundering herd on token refresh.
    /// </summary>
    private async Task<string> GetAccessTokenAsync(CancellationToken cancellationToken)
    {
        // Fast path: check if cached token is still valid without acquiring lock.
        CachedToken? cached = this._cachedToken;
        if (cached is not null && DateTimeOffset.UtcNow < cached.ExpiresAt)
        {
            return cached.AccessToken;
        }

        await this._tokenLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            // Double-check after acquiring lock.
            cached = this._cachedToken;
            if (cached is not null && DateTimeOffset.UtcNow < cached.ExpiresAt)
            {
                return cached.AccessToken;
            }

            // Acquire a new token.
            var tokenResponse = await this.RequestAccessTokenAsync(cancellationToken).ConfigureAwait(false);
            this._cachedToken = new CachedToken(
                tokenResponse.AccessToken ?? throw new AgentforceApiException("OAuth response did not contain an access token."),
                DateTimeOffset.UtcNow.Add(s_tokenRefreshInterval));

            return this._cachedToken.AccessToken;
        }
        finally
        {
            this._tokenLock.Release();
        }
    }

    /// <summary>
    /// Requests a new access token from the Salesforce OAuth endpoint.
    /// </summary>
    private async Task<OAuthTokenResponse> RequestAccessTokenAsync(CancellationToken cancellationToken)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, this._config.TokenEndpoint);
        request.Content = new FormUrlEncodedContent(new[]
        {
            new KeyValuePair<string, string>("grant_type", "client_credentials"),
            new KeyValuePair<string, string>("client_id", this._config.ConsumerKey),
            new KeyValuePair<string, string>("client_secret", this._config.ConsumerSecret),
        });

        using HttpResponseMessage response = await this._httpClient.SendAsync(request, cancellationToken).ConfigureAwait(false);
        string responseBody = await response.Content.ReadAsStringAsync(
#if !NETSTANDARD2_0 && !NET472
            cancellationToken
#endif
        ).ConfigureAwait(false);

        if (!response.IsSuccessStatusCode)
        {
            await ThrowApiExceptionAsync(response, responseBody).ConfigureAwait(false);
        }

        return (OAuthTokenResponse?)JsonSerializer.Deserialize(responseBody, AgentforceJsonUtilities.DefaultOptions.GetTypeInfo(typeof(OAuthTokenResponse)))
            ?? throw new AgentforceApiException("Failed to deserialize OAuth token response.");
    }

    /// <summary>
    /// Invalidates the currently cached token, forcing a refresh on the next request.
    /// </summary>
    private void InvalidateCachedToken()
    {
        this._cachedToken = null;
    }

    private static StringContent CreateJsonContent<T>(T value)
    {
        return new StringContent(
            JsonSerializer.Serialize(value, (JsonTypeInfo<T>)AgentforceJsonUtilities.DefaultOptions.GetTypeInfo(typeof(T))),
            System.Text.Encoding.UTF8,
            "application/json");
    }

    private static Task ThrowApiExceptionAsync(HttpResponseMessage response, string responseBody)
    {
        AgentforceErrorResponse? error = null;
        try
        {
            error = (AgentforceErrorResponse?)JsonSerializer.Deserialize(responseBody, AgentforceJsonUtilities.DefaultOptions.GetTypeInfo(typeof(AgentforceErrorResponse)));
        }
#pragma warning disable CA1031 // Do not catch general exception types
        catch
#pragma warning restore CA1031
        {
            // If we can't parse the error, throw with raw body.
        }

        throw new AgentforceApiException(
            error?.ErrorDescription ?? responseBody,
            response.StatusCode,
            error?.Error);
    }

    private sealed class CachedToken
    {
        public CachedToken(string accessToken, DateTimeOffset expiresAt)
        {
            this.AccessToken = accessToken;
            this.ExpiresAt = expiresAt;
        }

        public string AccessToken { get; }

        public DateTimeOffset ExpiresAt { get; }
    }

    #region API Request/Response Models

    internal sealed class CreateSessionRequest
    {
        [JsonPropertyName("externalSessionKey")]
        public string ExternalSessionKey { get; set; } = string.Empty;

        [JsonPropertyName("instanceConfig")]
        public InstanceConfig? InstanceConfig { get; set; }

        [JsonPropertyName("streamingCapabilities")]
        public StreamingCapabilities? StreamingCapabilities { get; set; }

        [JsonPropertyName("bypassUser")]
        public bool BypassUser { get; set; }
    }

    internal sealed class SendMessageRequest
    {
        [JsonPropertyName("message")]
        public MessagePayload? Message { get; set; }
    }

    internal sealed class OAuthTokenResponse
    {
        [JsonPropertyName("access_token")]
        public string? AccessToken { get; set; }

        [JsonPropertyName("instance_url")]
        public string? InstanceUrl { get; set; }

        [JsonPropertyName("token_type")]
        public string? TokenType { get; set; }

        [JsonPropertyName("issued_at")]
        public string? IssuedAt { get; set; }
    }

    #endregion
}

/// <summary>
/// Represents the instance configuration for a session creation request.
/// </summary>
internal sealed class InstanceConfig
{
    [JsonPropertyName("endpoint")]
    public string Endpoint { get; set; } = string.Empty;
}

/// <summary>
/// Represents the streaming capabilities for a session creation request.
/// </summary>
internal sealed class StreamingCapabilities
{
    [JsonPropertyName("chunkTypes")]
    public string[] ChunkTypes { get; set; } = Array.Empty<string>();
}

/// <summary>
/// Represents the message payload sent to the Agentforce agent.
/// </summary>
internal sealed class MessagePayload
{
    [JsonPropertyName("sequenceId")]
    public long SequenceId { get; set; }

    [JsonPropertyName("type")]
    public string Type { get; set; } = "Text";

    [JsonPropertyName("text")]
    public string Text { get; set; } = string.Empty;
}

/// <summary>
/// Represents the response from creating an Agentforce session.
/// </summary>
public sealed class CreateSessionResponse
{
    /// <summary>
    /// Gets or sets the Salesforce-assigned session ID.
    /// </summary>
    [JsonPropertyName("sessionId")]
    public string? SessionId { get; set; }

    /// <summary>
    /// Gets or sets the initial greeting messages from the agent.
    /// </summary>
    [JsonPropertyName("messages")]
    public List<AgentforceMessage>? Messages { get; set; }
}

/// <summary>
/// Represents the response from sending a message to an Agentforce agent.
/// </summary>
public sealed class SendMessageResponse
{
    /// <summary>
    /// Gets or sets the agent's response messages.
    /// </summary>
    [JsonPropertyName("messages")]
    public List<AgentforceMessage>? Messages { get; set; }
}

/// <summary>
/// Represents a single message from the Agentforce agent.
/// </summary>
public sealed class AgentforceMessage
{
    /// <summary>
    /// Gets or sets the message type (e.g., "Inform", "Text").
    /// </summary>
    [JsonPropertyName("type")]
    public string? Type { get; set; }

    /// <summary>
    /// Gets or sets the message text content.
    /// </summary>
    [JsonPropertyName("message")]
    public string? Message { get; set; }

    /// <summary>
    /// Gets or sets alternative text content (used in some response types).
    /// </summary>
    [JsonPropertyName("text")]
    public string? Text { get; set; }

    /// <summary>
    /// Gets the displayable text from this message, preferring <see cref="Message"/> over <see cref="Text"/>.
    /// </summary>
    internal string? DisplayText => this.Message ?? this.Text;
}

/// <summary>
/// Represents an error response from the Agentforce API.
/// </summary>
internal sealed class AgentforceErrorResponse
{
    [JsonPropertyName("error")]
    public string? Error { get; set; }

    [JsonPropertyName("error_description")]
    public string? ErrorDescription { get; set; }
}
