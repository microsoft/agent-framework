// Copyright (c) Microsoft. All rights reserved.

using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AGUI;
using Microsoft.Extensions.AI;

string serverUrl = Environment.GetEnvironmentVariable("AGUI_SERVER_URL") ?? "http://localhost:5253";

Console.WriteLine($"Connecting to AG-UI server at: {serverUrl}\n");

// Create the AG-UI client agent
using HttpClient httpClient = new()
{
    Timeout = TimeSpan.FromSeconds(60)
};

AGUIChatClient chatClient = new(httpClient, serverUrl);

AIAgent agent = chatClient.AsAIAgent(
    name: "agui-client",
    description: "AG-UI Client Agent");

AgentSession session = await agent.CreateSessionAsync();
List<ChatMessage> messages =
[
    new(ChatRole.System, "You are a helpful assistant.")
];

try
{
    while (true)
    {
        // Get user input
        Console.Write("\nUser (:q or quit to exit): ");
        string? message = Console.ReadLine();

        if (string.IsNullOrWhiteSpace(message))
        {
            Console.WriteLine("Request cannot be empty.");
            continue;
        }

        if (message is ":q" or "quit")
        {
            break;
        }

        messages.Add(new ChatMessage(ChatRole.User, message));

        // Stream the response
        bool isFirstUpdate = true;
        string? sessionId = null;
        List<ChatResponseUpdate> responseUpdates = [];

        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync(messages, session))
        {
            ChatResponseUpdate chatUpdate = update.AsChatResponseUpdate();

            if (ShouldPersistResponseUpdate(chatUpdate))
            {
                responseUpdates.Add(chatUpdate);
            }

            // First update indicates run started
            if (isFirstUpdate)
            {
                sessionId = chatUpdate.ConversationId;
                Console.ForegroundColor = ConsoleColor.Yellow;
                Console.WriteLine($"\n[Run Started - Session: {chatUpdate.ConversationId}, Run: {chatUpdate.ResponseId}]");
                Console.ResetColor();
                isFirstUpdate = false;
            }

            // Display streaming content
            foreach (AIContent content in update.Contents)
            {
                if (content is TextContent textContent)
                {
                    Console.ForegroundColor = ConsoleColor.Cyan;
                    Console.Write(textContent.Text);
                    Console.ResetColor();
                }
                else if (content is DataContent dataContent &&
                         chatUpdate.AdditionalProperties?.TryGetValue("is_activity_snapshot", out bool isSnapshot) is true &&
                         isSnapshot)
                {
                    await HandleActivitySnapshotAsync(httpClient, serverUrl, dataContent);
                }
                else if (content is ErrorContent errorContent)
                {
                    Console.ForegroundColor = ConsoleColor.Red;
                    Console.WriteLine($"\n[Error: {errorContent.Message}]");
                    Console.ResetColor();
                }
            }
        }

        AppendResponseMessages(messages, responseUpdates);

        Console.ForegroundColor = ConsoleColor.Green;
        Console.WriteLine($"\n[Run Finished - Session: {sessionId}]");
        Console.ResetColor();
    }
}
catch (Exception ex)
{
    Console.WriteLine($"\nAn error occurred: {ex.Message}");
}

static async Task HandleActivitySnapshotAsync(HttpClient httpClient, string serverUrl, DataContent dataContent)
{
    Console.WriteLine();
    Console.ForegroundColor = ConsoleColor.Magenta;
    Console.WriteLine("┌─────────────────────────────────────────────────────────┐");
    Console.WriteLine("│  ACTIVITY SNAPSHOT — MCP App detected                   │");
    Console.WriteLine("└─────────────────────────────────────────────────────────┘");
    Console.ResetColor();

    // Parse the activity snapshot JSON content
    JsonElement snapshot;
    try
    {
        snapshot = JsonDocument.Parse(dataContent.Data.ToArray()).RootElement;
    }
    catch (JsonException ex)
    {
        Console.ForegroundColor = ConsoleColor.Red;
        Console.WriteLine($"[Failed to parse activity snapshot: {ex.Message}]");
        Console.ResetColor();
        return;
    }

    string resourceUri = snapshot.TryGetProperty("resourceUri", out var uriProp) ? uriProp.GetString() ?? "" : "";

    Console.ForegroundColor = ConsoleColor.White;
    Console.WriteLine($"  Resource URI : {resourceUri}");

    // Show tool result from the snapshot
    if (snapshot.TryGetProperty("result", out var result))
    {
        Console.ForegroundColor = ConsoleColor.DarkYellow;
        Console.WriteLine("  Tool Result:");
        if (result.TryGetProperty("content", out var resultContent) && resultContent.ValueKind == JsonValueKind.Array)
        {
            foreach (JsonElement item in resultContent.EnumerateArray())
            {
                string type = item.TryGetProperty("type", out var t) ? t.GetString() ?? "?" : "?";
                string text = item.TryGetProperty("text", out var txt) ? txt.GetString() ?? "" : item.GetRawText();
                Console.WriteLine($"    [{type}] {text}");
            }
        }
        else
        {
            Console.WriteLine($"    {result.GetRawText()}");
        }
    }

    Console.ResetColor();

    if (string.IsNullOrEmpty(resourceUri))
    {
        Console.ForegroundColor = ConsoleColor.Red;
        Console.WriteLine("  [No resource URI — skipping fetch]");
        Console.ResetColor();
        return;
    }

    // Fetch the MCP App resource via a proxied resources/read request
    Console.ForegroundColor = ConsoleColor.White;
    Console.WriteLine($"\n  Fetching resource via proxied request: {resourceUri}");
    Console.ResetColor();

    var proxiedBody = new
    {
        threadId = Guid.NewGuid().ToString(),
        runId = Guid.NewGuid().ToString(),
        messages = Array.Empty<object>(),
        tools = Array.Empty<object>(),
        context = Array.Empty<object>(),
        state = new { },
        forwardedProps = new
        {
            __proxiedMCPRequest = new
            {
                method = "resources/read",
                @params = new { uri = resourceUri }
            }
        }
    };

    JsonElement? resourceResult = await SendProxiedRequestAsync(httpClient, serverUrl, proxiedBody);

    if (resourceResult is null)
    {
        return;
    }

    Console.ForegroundColor = ConsoleColor.Magenta;
    Console.WriteLine("┌─────────────────────────────────────────────────────────┐");
    Console.WriteLine("│  MCP App Resource Contents                              │");
    Console.WriteLine("└─────────────────────────────────────────────────────────┘");
    Console.ResetColor();

    if (resourceResult.Value.TryGetProperty("contents", out var contents) &&
        contents.ValueKind == JsonValueKind.Array)
    {
        foreach (JsonElement item in contents.EnumerateArray())
        {
            string uri = item.TryGetProperty("uri", out var uriEl) ? uriEl.GetString() ?? "" : "";
            string mimeType = item.TryGetProperty("mimeType", out var mimeEl) ? mimeEl.GetString() ?? "" : "";
            bool hasText = item.TryGetProperty("text", out var textEl);
            bool hasBlob = item.TryGetProperty("blob", out var blobEl);

            Console.ForegroundColor = ConsoleColor.White;
            Console.WriteLine($"  URI       : {uri}");
            Console.WriteLine($"  MIME Type : {mimeType}");

            if (hasText)
            {
                string text = textEl.GetString() ?? "";
                string preview = text.Length > 300 ? text[..300] + "…" : text;
                Console.ForegroundColor = ConsoleColor.Gray;
                Console.WriteLine($"  Content ({text.Length} chars):");
                Console.WriteLine($"  {preview.Replace("\n", "\n  ")}");
            }
            else if (hasBlob)
            {
                string blob = blobEl.GetString() ?? "";
                Console.ForegroundColor = ConsoleColor.Gray;
                Console.WriteLine($"  Blob (base64, {blob.Length} chars)");
            }
            else
            {
                Console.ForegroundColor = ConsoleColor.Gray;
                Console.WriteLine($"  {item.GetRawText()}");
            }

            Console.ResetColor();
        }
    }
    else
    {
        Console.ForegroundColor = ConsoleColor.Gray;
        Console.WriteLine($"  {resourceResult.Value.GetRawText()}");
        Console.ResetColor();
    }
}

static async Task<JsonElement?> SendProxiedRequestAsync(HttpClient httpClient, string serverUrl, object body)
{
    try
    {
        using HttpRequestMessage request = new(HttpMethod.Post, serverUrl)
        {
            Content = JsonContent.Create(body)
        };
        request.Headers.Accept.ParseAdd("text/event-stream");

        using HttpResponseMessage response = await httpClient.SendAsync(
            request, HttpCompletionOption.ResponseHeadersRead);
        response.EnsureSuccessStatusCode();

        await using Stream stream = await response.Content.ReadAsStreamAsync();
        using StreamReader reader = new(stream);

        string? line;
        while ((line = await reader.ReadLineAsync()) is not null)
        {
            if (!line.StartsWith("data: ", StringComparison.Ordinal))
            {
                continue;
            }

            string payload = line[6..].Trim();
            if (string.IsNullOrEmpty(payload) || payload == "[DONE]")
            {
                continue;
            }

            try
            {
                using JsonDocument doc = JsonDocument.Parse(payload);
                JsonElement evt = doc.RootElement.Clone();

                string? eventType = evt.TryGetProperty("type", out var typeProp)
                    ? typeProp.GetString()
                    : null;

                if (eventType == "RUN_FINISHED" &&
                    evt.TryGetProperty("result", out var result))
                {
                    return result.Clone();
                }

                // Stop on terminal events
                if (eventType is "RUN_FINISHED" or "RUN_ERROR")
                {
                    break;
                }
            }
            catch (JsonException) { /* skip non-JSON lines */ }
        }
    }
    catch (Exception ex)
    {
        Console.ForegroundColor = ConsoleColor.Red;
        Console.WriteLine($"  [Proxied request failed: {ex.Message}]");
        Console.ResetColor();
    }

    return null;
}

static void AppendResponseMessages(List<ChatMessage> messages, List<ChatResponseUpdate> responseUpdates)
{
    if (responseUpdates.Count == 0)
    {
        return;
    }

    ChatResponse response = responseUpdates.ToChatResponse();
    if (response.Messages.Count == 0)
    {
        return;
    }

    messages.AddRange(response.Messages);
}

static bool ShouldPersistResponseUpdate(ChatResponseUpdate update)
{
    return !HasBooleanFlag(update, "is_activity_snapshot") &&
        !HasBooleanFlag(update, "is_state_snapshot") &&
        !HasBooleanFlag(update, "is_state_delta");
}

static bool HasBooleanFlag(ChatResponseUpdate update, string key)
{
    return update.AdditionalProperties?.TryGetValue(key, out bool enabled) is true && enabled;
}
