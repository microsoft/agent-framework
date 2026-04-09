// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;
using Microsoft.Extensions.AI;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;
using OpenAI;
using System.Text;
using System.Text.Json;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);
builder.Services.AddHttpClient().AddLogging();
builder.Services.AddAGUI();

var openaiApiKey = builder.Configuration["OPENAI_API_KEY"] ?? throw new InvalidOperationException("OPENAI_API_KEY is not set.");
var chatClient = new OpenAIClient(openaiApiKey)
    .GetChatClient("gpt-4o")
    .AsIChatClient()
    .AsBuilder()
    .ConfigureOptions(o => o.Temperature = 0f)
    .Build();

var mcpClient = await McpClient.CreateAsync(new HttpClientTransport(new()
{
    Endpoint = new Uri("http://localhost:5177/mcp"),
    TransportMode = HttpTransportMode.StreamableHttp,
}));
var mcpTools = await mcpClient.ListToolsAsync();

WebApplication app = builder.Build();

AIAgent agent = chatClient.AsAIAgent(
    name: "AGUIAssistant",
    instructions: """
        You are a helpful assistant.
        IMPORTANT RULES:
        (1) You MUST use the get-time tool to answer any question about the current time or date — never answer from memory.
        (2) Do not guess or make up the time.
        """,
    tools: mcpTools.Cast<AITool>().ToList())
    .AsBuilder()
    .UseEmitToolMetadata(mcpTools.ToDictionary(static t => t.Name, static t => t.ProtocolTool.Meta))
    .Build()
    ;

app.MapAGUI("/", agent, proxiedResultResolver: async (forwardedProperties, cancellationToken) =>
{
    if (!TryGetProxiedRequest(forwardedProperties, out var proxiedRequest) || proxiedRequest is null)
    {
        return null;
    }

    var request = proxiedRequest.Value;

    return request.Method switch
    {
        "resources/read" when request.ResourceUri is not null =>
            BuildProxiedReadResult(
                request.ResourceUri,
                await mcpClient.ReadResourceAsync(new Uri(request.ResourceUri), cancellationToken: cancellationToken)),
        "tools/call" when request.ToolName is not null =>
            BuildProxiedToolCallResult(
                await mcpClient.CallToolAsync(
                    request.ToolName,
                    request.Arguments,
                    cancellationToken: cancellationToken)),
        _ => null,
    };
});

await app.RunAsync();

static JsonElement? BuildProxiedReadResult(string requestedResourceUri, ReadResourceResult readResult)
{
    var contentsJson = string.Join(",", readResult.Contents.Select(content => BuildProxiedReadContentJson(requestedResourceUri, content)));
    using var document = JsonDocument.Parse($"{{\"contents\":[{contentsJson}]}}");
    return document.RootElement.Clone();
}

static JsonElement? BuildProxiedToolCallResult(CallToolResult callToolResult)
{
    var contentJson = callToolResult.Content is null
        ? string.Empty
        : string.Join(",", callToolResult.Content.Select(BuildProxiedToolCallContentJson));

    var structuredContentJson = callToolResult.StructuredContent is null
        ? string.Empty
        : $",\"structuredContent\":{JsonSerializer.Serialize(callToolResult.StructuredContent)}";
    var isErrorJson = callToolResult.IsError is null
        ? string.Empty
        : $",\"isError\":{(callToolResult.IsError.Value ? "true" : "false")}";

    using var document = JsonDocument.Parse($"{{\"content\":[{contentJson}]{structuredContentJson}{isErrorJson}}}");
    return document.RootElement.Clone();
}

static string BuildProxiedReadContentJson(string requestedResourceUri, ResourceContents content)
{
    var encodedUri = JsonSerializer.Serialize(requestedResourceUri);
    var encodedMimeType = content.MimeType is null ? "null" : JsonSerializer.Serialize(content.MimeType);

    return content switch
    {
        TextResourceContents text =>
            $"{{\"uri\":{encodedUri},\"mimeType\":{encodedMimeType},\"text\":{JsonSerializer.Serialize(text.Text ?? string.Empty)}}}",
        BlobResourceContents blob =>
            $"{{\"uri\":{encodedUri},\"mimeType\":{encodedMimeType},\"blob\":{JsonSerializer.Serialize(Convert.ToBase64String(blob.DecodedData.ToArray()))}}}",
        _ =>
            $"{{\"uri\":{encodedUri},\"mimeType\":{encodedMimeType},\"text\":{JsonSerializer.Serialize(content.ToString() ?? string.Empty)}}}",
    };
}

static string BuildProxiedToolCallContentJson(ContentBlock content)
{
    return content switch
    {
        TextContentBlock text =>
            $"{{\"type\":\"text\",\"text\":{JsonSerializer.Serialize(text.Text ?? string.Empty)}}}",
        ImageContentBlock image =>
            $"{{\"type\":\"image\",\"mimeType\":{JsonSerializer.Serialize(image.MimeType)},\"data\":{JsonSerializer.Serialize(Convert.ToBase64String(image.Data.ToArray()))}}}",
        AudioContentBlock audio =>
            $"{{\"type\":\"audio\",\"mimeType\":{JsonSerializer.Serialize(audio.MimeType)},\"data\":{JsonSerializer.Serialize(Convert.ToBase64String(audio.Data.ToArray()))}}}",
        _ =>
            $"{{\"type\":\"text\",\"text\":{JsonSerializer.Serialize(content.ToString() ?? string.Empty)}}}",
    };
}

static bool TryGetProxiedRequest(
    JsonElement forwardedProperties,
    out (string Method, string? ResourceUri, string? ToolName, IReadOnlyDictionary<string, object?>? Arguments)? proxiedRequest)
{
    proxiedRequest = null;

    if (forwardedProperties.ValueKind != JsonValueKind.Object ||
        !forwardedProperties.TryGetProperty("__proxiedMCPRequest", out var proxiedRequestProperty) ||
        proxiedRequestProperty.ValueKind != JsonValueKind.Object ||
        !proxiedRequestProperty.TryGetProperty("method", out var methodProperty))
    {
        return false;
    }

    var method = methodProperty.GetString();
    if (string.IsNullOrWhiteSpace(method))
    {
        return false;
    }

    if (!proxiedRequestProperty.TryGetProperty("params", out var parameters) ||
        parameters.ValueKind != JsonValueKind.Object)
    {
        proxiedRequest = (method, null, null, null);
        return true;
    }

    if (string.Equals(method, "resources/read", StringComparison.Ordinal) &&
        parameters.TryGetProperty("uri", out var uriProperty))
    {
        var resourceUri = uriProperty.GetString();
        proxiedRequest = (method, resourceUri, null, null);
        return !string.IsNullOrWhiteSpace(resourceUri);
    }

    if (string.Equals(method, "tools/call", StringComparison.Ordinal) &&
        parameters.TryGetProperty("name", out var nameProperty))
    {
        var toolName = nameProperty.GetString();
        var arguments = TryGetArguments(parameters, out var argumentsValue)
            ? argumentsValue
            : null;

        proxiedRequest = (method, null, toolName, arguments);
        return !string.IsNullOrWhiteSpace(toolName);
    }

    proxiedRequest = (method, null, null, null);
    return true;
}

static bool TryGetArguments(JsonElement parameters, out IReadOnlyDictionary<string, object?>? arguments)
{
    arguments = null;

    if (!parameters.TryGetProperty("arguments", out var argumentsProperty) ||
        argumentsProperty.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined)
    {
        return false;
    }

    if (argumentsProperty.ValueKind != JsonValueKind.Object)
    {
        return false;
    }

    using var document = JsonDocument.Parse(argumentsProperty.GetRawText());
    arguments = JsonSerializer.Deserialize<Dictionary<string, object?>>(document.RootElement.GetRawText());
    return arguments is not null;
}