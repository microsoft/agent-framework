// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Threading;
using System.Threading.Tasks;
using Azure.Core;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// An <see cref="DelegatingHandler"/> that:
/// <list type="bullet">
///   <item>Acquires a fresh Azure bearer token (scope: <c>https://ai.azure.com/.default</c>) per request, per <c>tools-integration-spec.md</c> §4.</item>
///   <item>Always injects the mandatory <c>Foundry-Features: Toolboxes=V1Preview</c> header per spec §2, merging any additional flags from <c>FOUNDRY_AGENT_TOOLSET_FEATURES</c>.</item>
///   <item>Propagates W3C trace context (<c>traceparent</c>, <c>tracestate</c>, <c>baggage</c>) from <see cref="Activity.Current"/> per spec §6.3.</item>
///   <item>Retries on HTTP 429, 500, 502, and 503 with exponential back-off (max 3 attempts, per spec §7).</item>
/// </list>
/// </summary>
internal sealed class FoundryToolboxBearerTokenHandler : DelegatingHandler
{
    private const int MaxRetries = 3;

    // Per tools-integration-spec.md §4, the container authenticates to the Foundry Toolbox
    // proxy with a bearer token whose audience is https://ai.azure.com.
    private static readonly TokenRequestContext s_tokenContext =
        new(["https://ai.azure.com/.default"]);

    // Per tools-integration-spec.md §2, every proxy request MUST include the
    // Foundry-Features: Toolboxes=V1Preview opt-in header while the service is in preview.
    private const string MandatoryFeatureFlag = "Toolboxes=V1Preview";

    private readonly TokenCredential _credential;
    private readonly string? _additionalFeaturesHeaderValue;

    internal FoundryToolboxBearerTokenHandler(TokenCredential credential, string? additionalFeaturesHeaderValue)
    {
        this._credential = credential;
        this._additionalFeaturesHeaderValue = additionalFeaturesHeaderValue;
    }

    protected override async Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request,
        CancellationToken cancellationToken)
    {
        var token = await this._credential
            .GetTokenAsync(s_tokenContext, cancellationToken)
            .ConfigureAwait(false);

        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token.Token);

        request.Headers.TryAddWithoutValidation("Foundry-Features", BuildFeaturesHeaderValue(this._additionalFeaturesHeaderValue));

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
