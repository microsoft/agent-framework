// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Threading;
using System.Threading.Tasks;
using Azure.Core;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// An <see cref="DelegatingHandler"/> that:
/// <list type="bullet">
///   <item>Acquires a fresh Azure bearer token with the configured scope for requests to the configured toolbox origin, per <c>tools-integration-spec.md</c> §4.</item>
///   <item>Injects the mandatory <c>Foundry-Features: Toolboxes=V1Preview</c> header on that origin per spec §2, merging any additional flags from <c>FOUNDRY_AGENT_TOOLSET_FEATURES</c>.</item>
///   <item>Forwards the platform call id (<c>x-agent-foundry-call-id</c>) of the response that opened the connection on that origin, so every request of the connection's MCP session carries the same caller identity.</item>
///   <item>Propagates W3C trace context (<c>traceparent</c>, <c>tracestate</c>, <c>baggage</c>) from <see cref="Activity.Current"/> per spec §6.3.</item>
///   <item>Retries on HTTP 429, 500, 502, and 503 with exponential back-off (max 3 attempts, per spec §7).</item>
/// </list>
/// </summary>
internal sealed class FoundryToolboxBearerTokenHandler : DelegatingHandler
{
    private const int MaxRetries = 3;

    // Per tools-integration-spec.md §2, every proxy request MUST include the
    // Foundry-Features: Toolboxes=V1Preview opt-in header while the service is in preview.
    private const string FeaturesHeaderName = "Foundry-Features";
    private const string MandatoryFeatureFlag = "Toolboxes=V1Preview";

    private readonly TokenCredential _credential;
    private readonly TokenRequestContext _tokenContext;
    private readonly string? _additionalFeaturesHeaderValue;
    private readonly Uri _pinnedEndpoint;
    private readonly string? _callId;

    /// <summary>
    /// Initializes a new instance of the <see cref="FoundryToolboxBearerTokenHandler"/> class.
    /// </summary>
    /// <param name="credential">The credential that issues the bearer token sent to the toolbox proxy.</param>
    /// <param name="tokenScope">The scope of that token, for example <c>https://ai.azure.com/.default</c>.</param>
    /// <param name="additionalFeaturesHeaderValue">
    /// Feature flags to send in <c>Foundry-Features</c> besides the mandatory <c>Toolboxes=V1Preview</c>, taken from
    /// <c>FOUNDRY_AGENT_TOOLSET_FEATURES</c>, or <see langword="null"/> for none.
    /// </param>
    /// <param name="pinnedEndpoint">
    /// The absolute toolbox endpoint. Only requests to its origin (scheme, host and port) receive the token, the
    /// Foundry headers and trace context; a request to any other origin is passed on unchanged.
    /// </param>
    /// <param name="callId">
    /// The platform call id of the response that opened this connection, sent as <c>x-agent-foundry-call-id</c> on
    /// every request to the pinned origin. When <see langword="null"/> or whitespace, no call id is sent.
    /// </param>
    /// <exception cref="ArgumentNullException">
    /// <paramref name="credential"/>, <paramref name="tokenScope"/> or <paramref name="pinnedEndpoint"/> is <see langword="null"/>.
    /// </exception>
    /// <exception cref="ArgumentException">
    /// <paramref name="tokenScope"/> is empty or whitespace, or <paramref name="pinnedEndpoint"/> is not absolute.
    /// </exception>
    internal FoundryToolboxBearerTokenHandler(
        TokenCredential credential,
        string tokenScope,
        string? additionalFeaturesHeaderValue,
        Uri pinnedEndpoint,
        string? callId = null)
    {
        _ = Throw.IfNull(credential);
        _ = Throw.IfNullOrWhitespace(tokenScope);
        _ = Throw.IfNull(pinnedEndpoint);
        if (!pinnedEndpoint.IsAbsoluteUri)
        {
            throw new ArgumentException("The pinned endpoint must be an absolute URI.", nameof(pinnedEndpoint));
        }

        this._credential = credential;
        this._tokenContext = new([tokenScope]);
        this._additionalFeaturesHeaderValue = additionalFeaturesHeaderValue;
        this._pinnedEndpoint = pinnedEndpoint;
        this._callId = string.IsNullOrWhiteSpace(callId) ? null : callId;
    }

    protected override async Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request,
        CancellationToken cancellationToken)
    {
        // A transport-created request can target a server-selected URI. Do not acquire or
        // attach Foundry credentials or platform context unless it remains on the configured
        // toolbox origin; the inner pinning handler still strips any pre-existing credentials.
        if (!OriginPinningHandler.IsSameOrigin(request.RequestUri, this._pinnedEndpoint))
        {
            return await base.SendAsync(request, cancellationToken).ConfigureAwait(false);
        }

        var token = await this._credential
            .GetTokenAsync(this._tokenContext, cancellationToken)
            .ConfigureAwait(false);

        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token.Token);

        request.Headers.TryAddWithoutValidation(FeaturesHeaderName, BuildFeaturesHeaderValue(this._additionalFeaturesHeaderValue));

        // Per PlatformContext, forward the platform per-request call id (x-agent-foundry-call-id,
        // container protocol 2.0.0) so the toolbox proxy can resolve the server-side caller context.
        // The value is fixed when the connection is created, never read from ambient state, so the
        // MCP session and every request on it carry the identity of the response that opened it.
        if (this._callId is { } callId && !request.Headers.Contains(HostedProtocolCompatibility.CallIdHeaderName))
        {
            request.Headers.TryAddWithoutValidation(HostedProtocolCompatibility.CallIdHeaderName, callId);
        }

        PropagateTraceContext(request);

        // MaxRetries is the total number of attempts (not additional retries after the first).
        for (int attempt = 0; attempt < MaxRetries; attempt++)
        {
            // Clone the request for retries (the original request cannot be sent twice)
            HttpRequestMessage requestToSend = attempt == 0
                ? request
                : await CloneRequestAsync(request, cancellationToken).ConfigureAwait(false);

            var response = await base.SendAsync(requestToSend, cancellationToken).ConfigureAwait(false);

            if (response.StatusCode is not (HttpStatusCode.TooManyRequests
                or HttpStatusCode.InternalServerError
                or HttpStatusCode.BadGateway
                or HttpStatusCode.ServiceUnavailable))
            {
                return response;
            }

            // Last attempt exhausted — return the error response as-is.
            if (attempt == MaxRetries - 1)
            {
                return response;
            }

            response.Dispose();

            await Task.Delay(TimeSpan.FromSeconds(Math.Pow(2, attempt)), cancellationToken)
                .ConfigureAwait(false);
        }

        // Unreachable when MaxRetries > 0, but satisfies the compiler.
        throw new InvalidOperationException("Retry loop completed without returning a response.");
    }

    // Returns "Toolboxes=V1Preview" when no override is set, or
    // "Toolboxes=V1Preview,<override-value>" when an override is set and doesn't already include it.
    internal static string BuildFeaturesHeaderValue(string? additional)
    {
        if (string.IsNullOrWhiteSpace(additional))
        {
            return MandatoryFeatureFlag;
        }

        // Avoid duplicating the mandatory flag if the override happens to already include it
        // (case-insensitive, ignore surrounding whitespace).
        foreach (var part in additional!.Split(','))
        {
            if (string.Equals(part.Trim(), MandatoryFeatureFlag, StringComparison.OrdinalIgnoreCase))
            {
                return additional;
            }
        }

        return $"{MandatoryFeatureFlag},{additional}";
    }

    // Per tools-integration-spec.md §6.3, propagate W3C trace context onto outbound requests.
    // Skip headers already set on the message (callers / inner handlers may override).
    private static void PropagateTraceContext(HttpRequestMessage request)
    {
        var activity = Activity.Current;
        if (activity is null)
        {
            return;
        }

        if (!request.Headers.Contains("traceparent"))
        {
            var traceparent = activity.Id;
            if (!string.IsNullOrEmpty(traceparent))
            {
                request.Headers.TryAddWithoutValidation("traceparent", traceparent);
            }
        }

        var traceState = activity.TraceStateString;
        if (!string.IsNullOrEmpty(traceState) && !request.Headers.Contains("tracestate"))
        {
            request.Headers.TryAddWithoutValidation("tracestate", traceState);
        }

        // Baggage is a comma-separated list of key=value pairs per the W3C Baggage spec.
        if (!request.Headers.Contains("baggage"))
        {
            string? baggageHeader = null;
            foreach (var pair in activity.Baggage)
            {
                if (pair.Value is null)
                {
                    continue;
                }

                var entry = $"{Uri.EscapeDataString(pair.Key)}={Uri.EscapeDataString(pair.Value)}";
                baggageHeader = baggageHeader is null ? entry : $"{baggageHeader},{entry}";
            }

            if (baggageHeader is not null)
            {
                request.Headers.TryAddWithoutValidation("baggage", baggageHeader);
            }
        }
    }

    private static async Task<HttpRequestMessage> CloneRequestAsync(
        HttpRequestMessage original,
        CancellationToken cancellationToken)
    {
        var clone = new HttpRequestMessage(original.Method, original.RequestUri);

        foreach (var header in original.Headers)
        {
            clone.Headers.TryAddWithoutValidation(header.Key, header.Value);
        }

        if (original.Content is not null)
        {
            var contentBytes = await original.Content.ReadAsByteArrayAsync(cancellationToken).ConfigureAwait(false);
            clone.Content = new ByteArrayContent(contentBytes);

            foreach (var header in original.Content.Headers)
            {
                clone.Content.Headers.TryAddWithoutValidation(header.Key, header.Value);
            }
        }

        return clone;
    }
}
