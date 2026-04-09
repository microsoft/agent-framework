// Copyright (c) Microsoft. All rights reserved.

// AG-UI MCP App Host Conformance Tests
// Verifies integration-level concerns that cannot be covered by unit tests:
//   1. The HTTP response carries Content-Type: text/event-stream (hosting layer).
//   2. An actual LLM routes "What time is it?" to the get-time MCP tool (E2E routing).
//   3. Proxied MCP resources/read and tools/call requests are handled without invoking the agent.
//
// All protocol-level output behaviour (event ordering, field values, wire format) is
// covered by the unit tests in Microsoft.Agents.AI.AGUI.UnitTests.
//
// Environment variables:
//   AG_UI_HOST       - URL of the AG-UI host under test (default: http://localhost:5253)
//   AG_UI_AGENT_ID   - Override the auto-detected agent ID used in the CopilotKit envelope.
//                      When absent the format is detected automatically on the first request.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using xRetry.v3;
using Xunit;

namespace Step06_McpApps.Tests;

public sealed class ConformanceTests
{
    private const string SkipConformanceReason = "Conformance tests are skipped during regular dotnet test runs.";

    /// <summary>URL of the AG-UI host under test.</summary>
    private static readonly string s_agUiHost = System.Environment.GetEnvironmentVariable("AG_UI_HOST") ?? "http://localhost:5253";

    /// <summary>Resource URI exposed by the get-time MCP App.</summary>
    private const string GetTimeResourceUri = "ui://get-time.html";

    /// <summary>Tool name exposed by the MCP server and used by the MCP App.</summary>
    private const string GetTimeToolName = "get-time";

    /// <summary>Expected MIME type for MCP App resources.</summary>
    private const string McpAppMimeType = "text/html;profile=mcp-app";

    /// <summary>Per-test timeout. LLM + MCP tool round-trips can be slow.</summary>
    private static readonly TimeSpan s_testTimeout = TimeSpan.FromSeconds(60);

    /// <summary>Network operation timeout so hung SSE/HTTP work fails instead of idling.</summary>
    private static readonly TimeSpan s_operationTimeout = TimeSpan.FromSeconds(20);

    private static readonly HttpClient s_httpClient = new();

    private static readonly string[] s_expectedProxyEventSequence = ["RUN_STARTED", "RUN_FINISHED"];

    // ---------------------------------------------------------------------------
    // CancellationTokenSource factory
    // ---------------------------------------------------------------------------

    /// <summary>
    /// Creates a <see cref="CancellationTokenSource"/> that cancels on whichever comes first:
    /// <paramref name="timeout"/> expiring, or the test runner signalling shutdown (Ctrl+C, etc.).
    /// Using a linked source ensures tests abort immediately when the runner is cancelled,
    /// rather than waiting for the full timeout to elapse.
    /// </summary>
    private static CancellationTokenSource CreateLinkedCts(TimeSpan timeout)
    {
        // Link to the framework token so Ctrl+C cancels us immediately.
        var cts = CancellationTokenSource.CreateLinkedTokenSource(
            TestContext.Current.CancellationToken);
        // Also cancel after the per-test wall-clock limit.
        cts.CancelAfter(timeout);
        return cts;
    }

    // ---------------------------------------------------------------------------
    // Request-format detection — plain AG-UI vs. CopilotKit envelope
    // ---------------------------------------------------------------------------

    /// <summary>
    /// Cached task that resolves to the agent ID to use in the CopilotKit envelope, or
    /// <see langword="null"/> when the endpoint accepts plain AG-UI bodies directly.
    /// Detected by probing the endpoint once; <see cref="Environment"/> variable
    /// <c>AG_UI_AGENT_ID</c> overrides detection.
    /// </summary>
    private static Task<string?>? s_agentIdTask;
    private static readonly object s_agentIdLock = new();

    private static Task<string?> GetAgentIdAsync(CancellationToken cancellationToken)
    {
        // Explicit override always wins — no probe needed.
        var overrideId = System.Environment.GetEnvironmentVariable("AG_UI_AGENT_ID");
        if (overrideId is not null)
        {
            return Task.FromResult<string?>(overrideId);
        }

        lock (s_agentIdLock)
        {
            // Reuse a running or successfully completed detection; restart if cancelled/faulted.
            if (s_agentIdTask is { IsCompleted: false } or { IsCompletedSuccessfully: true })
            {
                return s_agentIdTask;
            }

            return s_agentIdTask = DetectAgentIdAsync(cancellationToken);
        }
    }

    /// <summary>
    /// Probes <see cref="s_agUiHost"/> with a minimal direct-format POST.
    /// <list type="bullet">
    ///   <item>Plain AG-UI server → <c>200 text/event-stream</c> → returns <see langword="null"/> (use direct format).</item>
    ///   <item>Non-success response (for example CopilotKit returning <c>400</c> "Missing method field") → returns <c>"default"</c> (use envelope).</item>
    /// </list>
    /// </summary>
    private static async Task<string?> DetectAgentIdAsync(CancellationToken cancellationToken)
    {
        // Use an empty messages array so the probe does not trigger a real LLM call.
        var probeJson = JsonSerializer.Serialize(new
        {
            threadId = "format-probe",
            runId = "format-probe",
            messages = Array.Empty<object>(),
            tools = Array.Empty<object>(),
            context = Array.Empty<object>(),
            state = new { },
            forwardedProps = new { }
        });

        using var request = new HttpRequestMessage(HttpMethod.Post, s_agUiHost)
        {
            Content = new StringContent(probeJson, Encoding.UTF8, "application/json")
        };
        request.Headers.Accept.ParseAdd("text/event-stream");

        // Read headers only — we only need the status code and content-type.
        using var response = await s_httpClient.SendAsync(
            request, HttpCompletionOption.ResponseHeadersRead, cancellationToken)
            .WaitAsync(s_operationTimeout, cancellationToken);

        // 200 text/event-stream → plain AG-UI server.
        if (response.IsSuccessStatusCode)
        {
            return null;
        }

        // Any non-success response falls back to CopilotKit-style envelope mode;
        // "default" is the standard agent ID.
        return "default";
    }

    // ---------------------------------------------------------------------------
    // MCP server info — auto-discovered once from ACTIVITY_SNAPSHOT
    // ---------------------------------------------------------------------------

    /// <summary>
    /// Cached task for MCP server identity (serverHash + serverId). Resolved on first access by
    /// running the agent once and extracting the values from the <c>ACTIVITY_SNAPSHOT</c> event.
    /// Only needed for hosts that validate server identity in proxied requests (e.g. CopilotKit).
    /// A cancelled or faulted task is discarded so the next caller can retry.
    /// </summary>
    private static Task<(string Hash, string Id)>? s_mcpServerInfoTask;
    private static readonly object s_mcpServerInfoLock = new();

    private static Task<(string Hash, string Id)> GetMcpServerInfoAsync(CancellationToken cancellationToken)
    {
        lock (s_mcpServerInfoLock)
        {
            // Reuse a running or successfully completed discovery; discard cancelled/faulted ones.
            if (s_mcpServerInfoTask is { IsCompleted: false } or { IsCompletedSuccessfully: true })
            {
                return s_mcpServerInfoTask;
            }

            return s_mcpServerInfoTask = DiscoverMcpServerInfoAsync(cancellationToken);
        }
    }

    /// <summary>
    /// Runs the agent with a time query and extracts <c>serverHash</c>/<c>serverId</c> from the
    /// resulting <c>ACTIVITY_SNAPSHOT</c>. Retries up to 3 times in case the LLM doesn't call
    /// the tool on the first attempt.
    /// </summary>
    private static async Task<(string Hash, string Id)> DiscoverMcpServerInfoAsync(
        CancellationToken cancellationToken)
    {
        for (int attempt = 0; attempt < 3; attempt++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var (_, events) = await SendAgUiRequestAsync(
                BuildAgentRunBody("what time is it?"), cancellationToken);

            foreach (var evt in events)
            {
                if (GetEventType(evt) != "ACTIVITY_SNAPSHOT") { continue; }
                if (!evt.TryGetProperty("content", out var content)) { continue; }

                var hash = content.TryGetProperty("serverHash", out var h) ? h.GetString() ?? "" : "";
                var id = content.TryGetProperty("serverId", out var s) ? s.GetString() ?? "" : "";

                if (!string.IsNullOrEmpty(hash))
                {
                    return (hash, id);
                }
            }
        }

        // No ACTIVITY_SNAPSHOT found — return empty strings; tests will fail with a clear message.
        return ("", "");
    }

    // ---------------------------------------------------------------------------
    // Request building
    // ---------------------------------------------------------------------------

    /// <summary>
    /// Serialises <paramref name="body"/> as the AG-UI request payload. Wraps it in the
    /// CopilotKit envelope when <paramref name="agentId"/> is non-null.
    /// </summary>
    private static string SerializePayload(object body, string? agentId)
    {
        var bodyJson = JsonSerializer.Serialize(body);

        if (agentId is null)
        {
            return bodyJson;
        }

        // Embed the pre-serialized body as a raw JsonElement so it is not double-serialized.
        using var doc = JsonDocument.Parse(bodyJson);
        return JsonSerializer.Serialize(new
        {
            method = "agent/run",
            @params = new { agentId },
            body = doc.RootElement
        });
    }

    private static object BuildAgentRunBody(string userContent) => new
    {
        threadId = Guid.NewGuid().ToString(),
        runId = Guid.NewGuid().ToString(),
        messages = new[] { new { id = Guid.NewGuid().ToString(), role = "user", content = userContent } },
        tools = Array.Empty<object>(),
        context = Array.Empty<object>(),
        state = new { },
        forwardedProps = new { }
    };

    private static object BuildProxiedReadBody(string resourceUri, string threadId, string runId,
        string serverHash, string serverId) =>
        BuildProxiedBody(
            threadId,
            runId,
            serverHash,
            serverId,
            "resources/read",
            new { uri = resourceUri });

    private static object BuildProxiedToolCallBody(string toolName, string threadId, string runId,
        string serverHash, string serverId) =>
        BuildProxiedBody(
            threadId,
            runId,
            serverHash,
            serverId,
            "tools/call",
            new { name = toolName, arguments = new { } });

    private static object BuildProxiedBody(string threadId, string runId, string serverHash,
        string serverId, string method, object parameters) => new
        {
            threadId,
            runId,
            messages = BuildCompletedTimeConversation(),
            tools = Array.Empty<object>(),
            context = Array.Empty<object>(),
            state = new { },
            forwardedProps = new
            {
                __proxiedMCPRequest = new
                {
                    serverHash,
                    serverId,
                    method,
                    @params = parameters
                }
            }
        };

    private static object[] BuildCompletedTimeConversation() =>
    [
        new { id = Guid.NewGuid().ToString(), role = "user", content = "what time is it?" },
        new
        {
            id = Guid.NewGuid().ToString(),
            role = "assistant",
            toolCalls = new[]
            {
                new { id = "call_test", type = "function", function = new { name = GetTimeToolName, arguments = "{}" } }
            }
        },
        new
        {
            id = Guid.NewGuid().ToString(),
            toolCallId = "call_test",
            role = "tool",
            content = DateTimeOffset.UtcNow.ToString("o")
        }
    ];

    // ---------------------------------------------------------------------------
    // HTTP helpers
    // ---------------------------------------------------------------------------

    private static async Task<string> SendAgUiRequestForHeadersAsync(
        object body,
        CancellationToken cancellationToken)
    {
        var agentId = await GetAgentIdAsync(cancellationToken);

        using var request = new HttpRequestMessage(HttpMethod.Post, s_agUiHost)
        {
            Content = new StringContent(SerializePayload(body, agentId), Encoding.UTF8, "application/json")
        };
        request.Headers.Accept.ParseAdd("text/event-stream");

        using var response = await s_httpClient.SendAsync(
            request, HttpCompletionOption.ResponseHeadersRead, cancellationToken)
            .WaitAsync(s_operationTimeout, cancellationToken);

        return response.Content.Headers.ContentType?.ToString() ?? "";
    }

    private static async Task<(string ContentType, List<JsonElement> Events)> SendAgUiRequestAsync(
        object body,
        CancellationToken cancellationToken)
    {
        var agentId = await GetAgentIdAsync(cancellationToken);

        using var request = new HttpRequestMessage(HttpMethod.Post, s_agUiHost)
        {
            Content = new StringContent(SerializePayload(body, agentId), Encoding.UTF8, "application/json")
        };
        request.Headers.Accept.ParseAdd("text/event-stream");

        using var response = await s_httpClient.SendAsync(
            request, HttpCompletionOption.ResponseHeadersRead, cancellationToken)
            .WaitAsync(s_operationTimeout, cancellationToken);

        var contentType = response.Content.Headers.ContentType?.ToString() ?? "";
        var events = await CollectSseEventsAsync(response, cancellationToken);
        return (contentType, events);
    }

    private static async Task<List<JsonElement>> CollectSseEventsAsync(
        HttpResponseMessage response,
        CancellationToken cancellationToken)
    {
        var events = new List<JsonElement>();
        await using var stream = await response.Content.ReadAsStreamAsync(cancellationToken);
        using var reader = new StreamReader(stream);

        string? line;
        while ((line = await reader.ReadLineAsync(cancellationToken)
            .AsTask()
            .WaitAsync(s_operationTimeout, cancellationToken)) is not null)
        {
            if (!line.StartsWith("data: ", StringComparison.Ordinal))
            {
                continue;
            }

            var payload = line[6..].Trim();
            if (string.IsNullOrEmpty(payload) || payload == "[DONE]")
            {
                continue;
            }

            try
            {
                var evt = JsonDocument.Parse(payload).RootElement.Clone();
                events.Add(evt);

                if (IsTerminalEvent(evt))
                {
                    break;
                }
            }
            catch (JsonException) { /* skip non-JSON lines */ }
        }

        return events;
    }

    private static string GetEventType(JsonElement evt)
        => evt.TryGetProperty("type", out var t) ? t.GetString() ?? "" : "";

    private static bool IsTerminalEvent(JsonElement evt)
        => GetEventType(evt) is "RUN_FINISHED" or "RUN_ERROR";

    private static string EventSequence(List<JsonElement> events)
        => string.Join(", ", events.Select(GetEventType));

    private static async Task<List<JsonElement>> RunProxiedReadAsync(
        string resourceUri, string threadId, string runId, CancellationToken cancellationToken)
    {
        var (serverHash, serverId) = await GetMcpServerInfoAsync(cancellationToken);
        var (_, events) = await SendAgUiRequestAsync(
            BuildProxiedReadBody(resourceUri, threadId, runId, serverHash, serverId),
            cancellationToken);
        return events;
    }

    private static async Task<List<JsonElement>> RunProxiedToolCallAsync(
        string toolName, string threadId, string runId, CancellationToken cancellationToken)
    {
        var (serverHash, serverId) = await GetMcpServerInfoAsync(cancellationToken);
        var (_, events) = await SendAgUiRequestAsync(
            BuildProxiedToolCallBody(toolName, threadId, runId, serverHash, serverId),
            cancellationToken);
        return events;
    }

    private static string GetRequiredToolCallId(List<JsonElement> events, string toolCallName)
    {
        int startIdx = events.FindIndex(
            e => GetEventType(e) == "TOOL_CALL_START" &&
                 e.TryGetProperty("toolCallName", out var n) && n.GetString() == toolCallName);

        Assert.True(startIdx >= 0,
            $"Expected a TOOL_CALL_START with toolCallName \"{toolCallName}\". Full sequence: {EventSequence(events)}");
        Assert.True(
            events[startIdx].TryGetProperty("toolCallId", out var idProp) &&
            !string.IsNullOrEmpty(idProp.GetString()),
            "TOOL_CALL_START must carry a toolCallId");

        return idProp.GetString()!;
    }

    // ---------------------------------------------------------------------------
    // Conformance tests — agent / HTTP layer
    // ---------------------------------------------------------------------------

    [Fact(Skip = SkipConformanceReason)]
    public async Task HttpResponse_HasContentType_TextEventStreamAsync()
    {
        using var cts = CreateLinkedCts(s_testTimeout);
        var contentType = await SendAgUiRequestForHeadersAsync(BuildAgentRunBody("ping"), cts.Token);

        Assert.Contains("text/event-stream", contentType, StringComparison.OrdinalIgnoreCase);
    }

    [RetryFact(3, Skip = SkipConformanceReason)]
    public async Task AskingWhatTimeIsIt_CausesToolCallStart_ForGetTime_Async()
    {
        using var cts = CreateLinkedCts(s_testTimeout);
        var (_, events) = await SendAgUiRequestAsync(BuildAgentRunBody("What time is it?"), cts.Token);
        Assert.NotEmpty(events);

        _ = GetRequiredToolCallId(events, "get-time");
    }

    // ---------------------------------------------------------------------------
    // Conformance tests — proxied MCP resource reads
    // ---------------------------------------------------------------------------

    [Fact(Skip = SkipConformanceReason)]
    public async Task ProxiedResourceRead_EmitsOnlyRunStartedAndRunFinished_Async()
    {
        using var cts = CreateLinkedCts(s_testTimeout);
        var events = await RunProxiedReadAsync(
            GetTimeResourceUri, Guid.NewGuid().ToString(), Guid.NewGuid().ToString(), cts.Token);

        Assert.NotEmpty(events);
        Assert.Equal(s_expectedProxyEventSequence, events.ConvertAll(GetEventType));
    }

    [Fact(Skip = SkipConformanceReason)]
    public async Task ProxiedResourceRead_RunFinished_HasResultContents_Async()
    {
        using var cts = CreateLinkedCts(s_testTimeout);
        var events = await RunProxiedReadAsync(
            GetTimeResourceUri, Guid.NewGuid().ToString(), Guid.NewGuid().ToString(), cts.Token);

        var runFinished = events.Single(e => GetEventType(e) == "RUN_FINISHED");
        Assert.True(
            runFinished.TryGetProperty("result", out var result) &&
            result.TryGetProperty("contents", out var contents) &&
            contents.GetArrayLength() > 0,
            $"RUN_FINISHED must have result.contents with at least one entry. Event: {runFinished}");
    }

    [Fact(Skip = SkipConformanceReason)]
    public async Task ProxiedResourceRead_RunFinished_ResourceUri_MatchesRequest_Async()
    {
        using var cts = CreateLinkedCts(s_testTimeout);
        var events = await RunProxiedReadAsync(
            GetTimeResourceUri, Guid.NewGuid().ToString(), Guid.NewGuid().ToString(), cts.Token);

        var firstContent = events.Single(e => GetEventType(e) == "RUN_FINISHED")
            .GetProperty("result").GetProperty("contents")[0];

        Assert.True(
            firstContent.TryGetProperty("uri", out var uriProp) &&
            uriProp.GetString() == GetTimeResourceUri,
            $"result.contents[0].uri must equal \"{GetTimeResourceUri}\". Got: {firstContent}");
    }

    [Fact(Skip = SkipConformanceReason)]
    public async Task ProxiedResourceRead_RunFinished_MimeType_IsMcpApp_Async()
    {
        using var cts = CreateLinkedCts(s_testTimeout);
        var events = await RunProxiedReadAsync(
            GetTimeResourceUri, Guid.NewGuid().ToString(), Guid.NewGuid().ToString(), cts.Token);

        var firstContent = events.Single(e => GetEventType(e) == "RUN_FINISHED")
            .GetProperty("result").GetProperty("contents")[0];

        Assert.True(
            firstContent.TryGetProperty("mimeType", out var mimeTypeProp) &&
            mimeTypeProp.GetString() == McpAppMimeType,
            $"result.contents[0].mimeType must equal \"{McpAppMimeType}\". Got: {firstContent}");
    }

    [Fact(Skip = SkipConformanceReason)]
    public async Task ProxiedResourceRead_RunFinished_ResourceText_IsNonEmpty_Async()
    {
        using var cts = CreateLinkedCts(s_testTimeout);
        var events = await RunProxiedReadAsync(
            GetTimeResourceUri, Guid.NewGuid().ToString(), Guid.NewGuid().ToString(), cts.Token);

        var firstContent = events.Single(e => GetEventType(e) == "RUN_FINISHED")
            .GetProperty("result").GetProperty("contents")[0];

        Assert.True(
            firstContent.TryGetProperty("text", out var textProp) &&
            !string.IsNullOrWhiteSpace(textProp.GetString()),
            $"result.contents[0].text must be non-empty HTML. Got: {firstContent}");
    }

    [Fact(Skip = SkipConformanceReason)]
    public async Task ProxiedResourceRead_RunFinished_EchoesRunId_Async()
    {
        using var cts = CreateLinkedCts(s_testTimeout);
        var runId = Guid.NewGuid().ToString();

        var events = await RunProxiedReadAsync(
            GetTimeResourceUri, Guid.NewGuid().ToString(), runId, cts.Token);

        var runFinished = events.Single(e => GetEventType(e) == "RUN_FINISHED");
        Assert.True(
            runFinished.TryGetProperty("runId", out var runIdProp) &&
            runIdProp.GetString() == runId,
            $"RUN_FINISHED.runId must echo the request runId \"{runId}\". Got: {runFinished}");
    }

    // ---------------------------------------------------------------------------
    // Conformance tests — proxied MCP tool calls from loaded MCP apps
    // ---------------------------------------------------------------------------

    [Fact(Skip = SkipConformanceReason)]
    public async Task ProxiedToolCall_EmitsOnlyRunStartedAndRunFinished_Async()
    {
        using var cts = CreateLinkedCts(s_testTimeout);
        var events = await RunProxiedToolCallAsync(
            GetTimeToolName, Guid.NewGuid().ToString(), Guid.NewGuid().ToString(), cts.Token);

        Assert.NotEmpty(events);
        Assert.Equal(s_expectedProxyEventSequence, events.ConvertAll(GetEventType));
    }

    [Fact(Skip = SkipConformanceReason)]
    public async Task ProxiedToolCall_RunFinished_HasResultContent_Async()
    {
        using var cts = CreateLinkedCts(s_testTimeout);
        var events = await RunProxiedToolCallAsync(
            GetTimeToolName, Guid.NewGuid().ToString(), Guid.NewGuid().ToString(), cts.Token);

        var runFinished = events.Single(e => GetEventType(e) == "RUN_FINISHED");
        Assert.True(
            runFinished.TryGetProperty("result", out var result) &&
            result.TryGetProperty("content", out var content) &&
            content.ValueKind == JsonValueKind.Array &&
            content.GetArrayLength() > 0,
            $"RUN_FINISHED must have result.content with at least one entry. Event: {runFinished}");
    }

    [Fact(Skip = SkipConformanceReason)]
    public async Task ProxiedToolCall_RunFinished_ResultContainsTextContent_Async()
    {
        using var cts = CreateLinkedCts(s_testTimeout);
        var events = await RunProxiedToolCallAsync(
            GetTimeToolName, Guid.NewGuid().ToString(), Guid.NewGuid().ToString(), cts.Token);

        var firstContent = events.Single(e => GetEventType(e) == "RUN_FINISHED")
            .GetProperty("result").GetProperty("content")[0];

        Assert.True(
            firstContent.TryGetProperty("type", out var typeProp) &&
            typeProp.GetString() == "text" &&
            firstContent.TryGetProperty("text", out var textProp) &&
            !string.IsNullOrWhiteSpace(textProp.GetString()),
            $"result.content[0] must be a non-empty text block. Got: {firstContent}");
    }

    [Fact(Skip = SkipConformanceReason)]
    public async Task ProxiedToolCall_RunFinished_EchoesRunId_Async()
    {
        using var cts = CreateLinkedCts(s_testTimeout);
        var runId = Guid.NewGuid().ToString();

        var events = await RunProxiedToolCallAsync(
            GetTimeToolName, Guid.NewGuid().ToString(), runId, cts.Token);

        var runFinished = events.Single(e => GetEventType(e) == "RUN_FINISHED");
        Assert.True(
            runFinished.TryGetProperty("runId", out var runIdProp) &&
            runIdProp.GetString() == runId,
            $"RUN_FINISHED.runId must echo the request runId \"{runId}\". Got: {runFinished}");
    }
}
