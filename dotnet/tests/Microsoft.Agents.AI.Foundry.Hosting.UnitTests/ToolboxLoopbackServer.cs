// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

/// <summary>
/// A loopback Streamable HTTP MCP server standing in for the Foundry toolbox proxy.
/// </summary>
/// <remarks>
/// Every <c>initialize</c> issues a new <c>Mcp-Session-Id</c>, and the server remembers which platform call id
/// opened each session. Tests use that record to prove which caller identity an MCP session belongs to and
/// whether a session was ended.
/// </remarks>
internal sealed class ToolboxLoopbackServer : IAsyncDisposable
{
    private const string CallIdHeader = "x-agent-foundry-call-id";
    private const string SessionIdHeader = "Mcp-Session-Id";
    private static readonly TimeSpan s_initializeHoldLimit = TimeSpan.FromSeconds(2);

    private readonly WebApplication _app;
    private readonly ConcurrentQueue<RecordedToolboxRequest> _requests = new();
    private readonly ConcurrentDictionary<string, string> _sessionCallIds = new(StringComparer.Ordinal);
    private int _sessionCount;
    private int _activeInitializes;
    private int _maxConcurrentInitializes;

    private ToolboxLoopbackServer(WebApplication app)
    {
        this._app = app;
    }

    /// <summary>Gets the base URL to use as the toolbox project endpoint.</summary>
    internal string Endpoint => this._app.Urls.Single();

    /// <summary>Gets every request the server received, in arrival order.</summary>
    internal IReadOnlyList<RecordedToolboxRequest> Requests => [.. this._requests];

    /// <summary>Gets the session ids issued so far.</summary>
    internal IReadOnlyCollection<string> IssuedSessionIds => [.. this._sessionCallIds.Keys];

    /// <summary>Gets the session ids the client ended with an HTTP <c>DELETE</c>.</summary>
    internal IReadOnlyCollection<string> EndedSessionIds =>
        [.. this._requests
            .Where(static request => request.HttpMethod == "DELETE" && request.SessionId is not null)
            .Select(static request => request.SessionId!)];

    /// <summary>Gets the largest number of <c>initialize</c> requests that were in flight at the same time.</summary>
    internal int MaxConcurrentInitializes => Volatile.Read(ref this._maxConcurrentInitializes);

    /// <summary>
    /// Gets or sets the name of the single tool advertised to a caller, from the toolbox name and call id.
    /// </summary>
    internal Func<string, string?, string> ToolNameFor { get; set; } = static (_, _) => "get_weather";

    /// <summary>
    /// Gets or sets the JSON-RPC error that <c>tools/list</c> returns to a caller, or <see langword="null"/> to list tools.
    /// </summary>
    internal Func<string, string?, JsonObject?> ToolsListErrorFor { get; set; } = static (_, _) => null;

    /// <summary>
    /// Gets or sets how many <c>initialize</c> requests each one waits for (bounded) before it answers.
    /// Used to observe whether a client opens toolboxes concurrently.
    /// </summary>
    internal int? InitializeConcurrencyTarget { get; set; }

    /// <summary>Gets the requests for one JSON-RPC method, in arrival order.</summary>
    internal IReadOnlyList<RecordedToolboxRequest> RequestsFor(string rpcMethod) =>
        [.. this._requests.Where(request => string.Equals(request.RpcMethod, rpcMethod, StringComparison.Ordinal))];

    /// <summary>Gets the platform call id carried by the <c>initialize</c> that opened a session.</summary>
    /// <remarks>Returns an empty string when the session was opened without a call id.</remarks>
    internal string CallIdThatOpened(string? sessionId) =>
        sessionId is not null && this._sessionCallIds.TryGetValue(sessionId, out var callId)
            ? callId
            : throw new InvalidOperationException($"Session '{sessionId}' was never issued by this server.");

    internal static async Task<ToolboxLoopbackServer> StartAsync()
    {
        var builder = WebApplication.CreateBuilder();
        builder.WebHost.UseUrls("http://127.0.0.1:0");
        builder.Logging.ClearProviders();
        var app = builder.Build();
        var server = new ToolboxLoopbackServer(app);
        app.Run(server.HandleAsync);
        await app.StartAsync();
        return server;
    }

    public ValueTask DisposeAsync() => this._app.DisposeAsync();

    private async Task HandleAsync(HttpContext context)
    {
        var toolboxName = GetToolboxName(context.Request.Path);
        var callId = GetHeader(context, CallIdHeader);
        var sessionId = GetHeader(context, SessionIdHeader);

        if (!HttpMethods.IsPost(context.Request.Method))
        {
            this._requests.Enqueue(new(context.Request.Method, toolboxName, RpcMethod: null, callId, sessionId));
            context.Response.StatusCode = HttpMethods.IsDelete(context.Request.Method)
                ? StatusCodes.Status200OK
                : StatusCodes.Status405MethodNotAllowed;
            return;
        }

        var request = (await JsonNode.ParseAsync(context.Request.Body, cancellationToken: context.RequestAborted))!;
        var rpcMethod = request["method"]?.GetValue<string>();
        this._requests.Enqueue(new("POST", toolboxName, rpcMethod, callId, sessionId));
        if (request["id"] is not { } id)
        {
            context.Response.StatusCode = StatusCodes.Status202Accepted;
            return;
        }

        JsonNode result;
        switch (rpcMethod)
        {
            case "initialize":
                await this.HoldInitializeAsync();
                var issued = $"session-{Interlocked.Increment(ref this._sessionCount)}-{toolboxName}-{callId ?? "none"}";
                this._sessionCallIds[issued] = callId ?? string.Empty;
                context.Response.Headers[SessionIdHeader] = issued;
                result = new JsonObject
                {
                    ["protocolVersion"] = request["params"]!["protocolVersion"]!.DeepClone(),
                    ["capabilities"] = new JsonObject { ["tools"] = new JsonObject() },
                    ["serverInfo"] = new JsonObject { ["name"] = "toolbox-loopback", ["version"] = "1.0" },
                };
                break;

            case "tools/list":
                if (this.ToolsListErrorFor(toolboxName, callId) is { } listError)
                {
                    await WriteErrorAsync(context, id, listError);
                    return;
                }

                result = new JsonObject
                {
                    ["tools"] = new JsonArray(new JsonObject
                    {
                        ["name"] = this.ToolNameFor(toolboxName, callId),
                        ["description"] = "Echoes the caller identity.",
                        ["inputSchema"] = JsonNode.Parse("""{"type":"object","properties":{"city":{"type":"string"}}}"""),
                    }),
                };
                break;

            case "tools/call":
                result = new JsonObject
                {
                    ["content"] = new JsonArray(new JsonObject { ["type"] = "text", ["text"] = callId ?? "none" }),
                };
                break;

            default:
                await WriteErrorAsync(context, id, new JsonObject { ["code"] = -32601, ["message"] = "Method not found" });
                return;
        }

        await context.Response.WriteAsJsonAsync(
            new JsonObject { ["jsonrpc"] = "2.0", ["id"] = id.DeepClone(), ["result"] = result },
            context.RequestAborted);
    }

    private async Task HoldInitializeAsync()
    {
        var active = Interlocked.Increment(ref this._activeInitializes);
        try
        {
            int observed;
            while (active > (observed = Volatile.Read(ref this._maxConcurrentInitializes))
                && Interlocked.CompareExchange(ref this._maxConcurrentInitializes, active, observed) != observed)
            {
            }

            if (this.InitializeConcurrencyTarget is { } target)
            {
                var deadline = DateTime.UtcNow + s_initializeHoldLimit;
                while (Volatile.Read(ref this._maxConcurrentInitializes) < target && DateTime.UtcNow < deadline)
                {
                    await Task.Delay(10);
                }
            }
        }
        finally
        {
            Interlocked.Decrement(ref this._activeInitializes);
        }
    }

    private static string GetToolboxName(PathString path)
    {
        var segments = path.Value?.Split('/', StringSplitOptions.RemoveEmptyEntries) ?? [];
        var index = Array.IndexOf(segments, "toolboxes");
        return index >= 0 && index + 1 < segments.Length ? segments[index + 1] : string.Empty;
    }

    private static string? GetHeader(HttpContext context, string name) =>
        context.Request.Headers.TryGetValue(name, out var values) && values.Count > 0 ? values.ToString() : null;

    private static Task WriteErrorAsync(HttpContext context, JsonNode id, JsonObject error) =>
        context.Response.WriteAsJsonAsync(
            new JsonObject { ["jsonrpc"] = "2.0", ["id"] = id.DeepClone(), ["error"] = error.DeepClone() },
            context.RequestAborted);
}

/// <summary>One HTTP request received by <see cref="ToolboxLoopbackServer"/>.</summary>
/// <param name="HttpMethod">The HTTP method.</param>
/// <param name="ToolboxName">The toolbox name taken from the request path.</param>
/// <param name="RpcMethod">The JSON-RPC method, or <see langword="null"/> for a non-POST request.</param>
/// <param name="CallId">The <c>x-agent-foundry-call-id</c> header, or <see langword="null"/> when absent.</param>
/// <param name="SessionId">The <c>Mcp-Session-Id</c> header, or <see langword="null"/> when absent.</param>
internal sealed record RecordedToolboxRequest(
    string HttpMethod,
    string ToolboxName,
    string? RpcMethod,
    string? CallId,
    string? SessionId);
