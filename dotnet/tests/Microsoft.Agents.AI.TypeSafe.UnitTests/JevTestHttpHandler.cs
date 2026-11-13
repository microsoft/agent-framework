// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.TypeSafe.UnitTests;

/// <summary>
/// A fake TypeSafe endpoint that records each request and replies with queued responses, repeating the last one.
/// </summary>
internal sealed class JevTestHttpHandler : HttpMessageHandler
{
    private readonly Queue<(HttpStatusCode Status, string Body, RetryConditionHeaderValue? RetryAfter, string? RetryAfterMs, string? RetryAfterRaw)> _responses = new();
    private (HttpStatusCode Status, string Body, RetryConditionHeaderValue? RetryAfter, string? RetryAfterMs, string? RetryAfterRaw) _last = (HttpStatusCode.OK, JevTestData.ResponseJson, null, null, null);

    public List<CapturedRequest> Requests { get; } = [];

    public JevTestHttpHandler Reply(HttpStatusCode status, string body, RetryConditionHeaderValue? retryAfter = null, string? retryAfterMs = null, string? retryAfterRaw = null)
    {
        this._responses.Enqueue((status, body, retryAfter, retryAfterMs, retryAfterRaw));
        return this;
    }

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        string body = await request.Content!.ReadAsStringAsync(cancellationToken);
        var headers = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (KeyValuePair<string, IEnumerable<string>> header in request.Headers)
        {
            headers[header.Key] = string.Join(",", header.Value);
        }

        this.Requests.Add(new CapturedRequest(request.Method, request.RequestUri!, request.Headers.Authorization, body, headers));

        if (this._responses.Count > 0)
        {
            this._last = this._responses.Dequeue();
        }

        var response = new HttpResponseMessage(this._last.Status)
        {
            Content = new StringContent(this._last.Body, Encoding.UTF8, "application/json"),
        };
        response.Headers.RetryAfter = this._last.RetryAfter;
        if (this._last.RetryAfterMs is { } retryAfterMs)
        {
            response.Headers.Add("retry-after-ms", retryAfterMs);
        }

        // A raw value lets tests send Retry-After headers that HttpClient would refuse to parse.
        if (this._last.RetryAfterRaw is { } raw)
        {
            response.Headers.TryAddWithoutValidation("Retry-After", raw);
        }

        return response;
    }

    public sealed record CapturedRequest(HttpMethod Method, Uri Uri, AuthenticationHeaderValue? Authorization, string Body, IReadOnlyDictionary<string, string> Headers);
}
