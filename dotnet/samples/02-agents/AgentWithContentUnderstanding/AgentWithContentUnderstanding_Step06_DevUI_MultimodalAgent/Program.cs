// Copyright (c) Microsoft. All rights reserved.

// DevUI Multi-Modal Agent — file upload + CU-powered analysis through the DevUI web UI.
//
// This sample hosts a Foundry-backed agent in an ASP.NET Core app and exposes
// it via the DevUI middleware. Users upload PDFs, scanned documents, handwritten
// images, audio, or video, and the Content Understanding context provider
// automatically analyzes them and injects the rendered markdown + fields into
// the LLM context.
//
// Environment variables:
//   AZURE_AI_PROJECT_ENDPOINT              — Azure AI Foundry project endpoint
//   AZURE_AI_MODEL_DEPLOYMENT_NAME         — Model deployment name (e.g. gpt-4.1)
//   AZURE_CONTENTUNDERSTANDING_ENDPOINT    — Content Understanding endpoint URL
//
// Run:
//   dotnet run
// Then open https://localhost:50520/devui in a browser.

using System.Text;
using System.Text.Json;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI.ContentUnderstanding;
using Microsoft.Agents.AI.DevUI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Extensions.AI;

var builder = WebApplication.CreateBuilder(args);

string projectEndpoint = builder.Configuration["AZURE_AI_PROJECT_ENDPOINT"]
    ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = builder.Configuration["AZURE_AI_MODEL_DEPLOYMENT_NAME"] ?? "gpt-4.1";
string cuEndpoint = builder.Configuration["AZURE_CONTENTUNDERSTANDING_ENDPOINT"]
    ?? throw new InvalidOperationException("AZURE_CONTENTUNDERSTANDING_ENDPOINT is not set.");

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, prefer a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency from credential probing and potential security risks from fallback mechanisms.
var credential = new DefaultAzureCredential();
var aiProjectClient = new AIProjectClient(new Uri(projectEndpoint), credential);

// The CU provider is a singleton so its session state and any background analyses
// survive across HTTP requests. DisposeAsync runs at app shutdown.
builder.Services.AddSingleton(_ => new ContentUnderstandingContextProvider(
    new ContentUnderstandingContextProviderOptions(new Uri(cuEndpoint), credential)
    {
        // For interactive DevUI use, a short timeout keeps the chat responsive —
        // the agent tells the user the file is still being analyzed and resolves
        // it on the next turn.
        MaxWait = TimeSpan.FromSeconds(5),

        // DevUI's HostedAgentResponseExecutor creates a fresh AgentSession every
        // turn, so per-session state would be lost. PerAgent keys state on the
        // agent instance instead — fine here because each DevUI agent is single-
        // user. Production multi-tenant hosts MUST keep the default PerSession.
        StateScope = StateScope.PerAgent,
    }));

const string AgentName = "MultiModalDocAgent";

builder.AddAIAgent(AgentName, (sp, key) =>
{
    var cu = sp.GetRequiredService<ContentUnderstandingContextProvider>();
    return aiProjectClient.AsAIAgent(new ChatClientAgentOptions
    {
        Name = key,
        ChatOptions = new ChatOptions
        {
            ModelId = deploymentName,
            Instructions = "You are a helpful document analysis assistant. "
                + "When a user uploads files, they are automatically analyzed using Azure Content Understanding. "
                + "Use list_documents() to check which documents are ready, pending, or failed "
                + "and to see which files are available for answering questions. "
                + "Tell the user if any documents are still being analyzed. "
                + "You can process PDFs, scanned documents, handwritten images, audio recordings, and video files. "
                + "When answering, cite specific content from the documents. "
                + "Whenever you mention a file name to the user, wrap it in backticks "
                + "(for example, `report_q1.pdf`) so the UI renders underscores correctly. "
                + "Format all responses as GitHub-flavored Markdown. When presenting tabular data, "
                + "use Markdown table syntax (| col1 | col2 |\\n|---|---|\\n| val1 | val2 |) — "
                + "never emit raw HTML tags like <table>, <tr>, or <td>, since the chat UI does not render HTML.",
        },
        AIContextProviders = [cu],
    });
});

builder.Services.AddOpenAIResponses();
builder.Services.AddOpenAIConversations();
builder.AddDevUI();

var app = builder.Build();

// HACK: Microsoft.Agents.AI.Hosting.OpenAI's ItemContentConverter passes raw base64 from
// input_file.file_data straight into DataContent(string uri, ...), which requires a
// "data:" URI and throws ArgumentException otherwise. Until that's fixed upstream,
// rewrite incoming /v1/responses bodies so raw base64 is wrapped in a data: URI. The
// Content Understanding provider's MimeSniffer then detects the real media type
// (PDF / PNG / JPEG / WAV / MP3 / MP4) from the bytes.
app.Use(static async (ctx, next) =>
{
    if (HttpMethods.IsPost(ctx.Request.Method)
        && ctx.Request.Path.StartsWithSegments("/v1/responses")
        && (ctx.Request.ContentType?.Contains("application/json", StringComparison.OrdinalIgnoreCase) ?? false))
    {
        ctx.Request.EnableBuffering();
        string body;
        using (var reader = new StreamReader(ctx.Request.Body, Encoding.UTF8, leaveOpen: true))
        {
            body = await reader.ReadToEndAsync().ConfigureAwait(false);
        }
        ctx.Request.Body.Position = 0;

        if (ResponsesRawBase64Workaround.TryRewrite(body, out string rewritten))
        {
            byte[] bytes = Encoding.UTF8.GetBytes(rewritten);
            ctx.Request.Body = new MemoryStream(bytes);
            ctx.Request.ContentLength = bytes.Length;
        }
    }
    await next().ConfigureAwait(false);
});

app.MapOpenAIResponses();
app.MapOpenAIConversations();

if (builder.Environment.IsDevelopment())
{
    app.MapDevUI();
}

Console.WriteLine("DevUI is available at: https://localhost:50520/devui");
Console.WriteLine("OpenAI Responses API is available at: https://localhost:50520/v1/responses");
Console.WriteLine("Press Ctrl+C to stop the server.");

app.Run();

/// <summary>
/// Wraps raw-base64 file_data fields in OpenAI Responses request bodies into data: URIs.
/// Workaround for Microsoft.Agents.AI.Hosting.OpenAI's ItemContentConverter, which expects
/// a data: URI form. Drop this once the upstream package handles raw base64 directly.
/// </summary>
internal static class ResponsesRawBase64Workaround
{
    public static bool TryRewrite(string body, out string rewritten)
    {
        rewritten = body;
        if (string.IsNullOrEmpty(body))
        {
            return false;
        }

        // A Try* method must never throw: a malformed body (the content-type header can lie)
        // would otherwise bubble a JsonException out of the middleware and 500 the request —
        // including requests that need no rewriting. On parse failure, leave the body untouched
        // and let the downstream endpoint handle (and properly reject) it.
        JsonDocument doc;
        try
        {
            doc = JsonDocument.Parse(body);
        }
        catch (JsonException)
        {
            return false;
        }

        using (doc)
        {
            if (!ContainsRawFileData(doc.RootElement))
            {
                return false;
            }

            using MemoryStream stream = new();
            using (Utf8JsonWriter writer = new(stream))
            {
                RewriteElement(doc.RootElement, writer);
            }
            rewritten = Encoding.UTF8.GetString(stream.ToArray());
            return true;
        }
    }

    private static bool ContainsRawFileData(JsonElement element)
    {
        switch (element.ValueKind)
        {
            case JsonValueKind.Object:
                if (IsInputFile(element)
                    && element.TryGetProperty("file_data", out JsonElement fileData)
                    && fileData.ValueKind == JsonValueKind.String
                    && fileData.GetString() is { Length: > 0 } s
                    && !s.StartsWith("data:", StringComparison.Ordinal))
                {
                    return true;
                }
                foreach (JsonProperty prop in element.EnumerateObject())
                {
                    if (ContainsRawFileData(prop.Value))
                    {
                        return true;
                    }
                }
                return false;
            case JsonValueKind.Array:
                foreach (JsonElement item in element.EnumerateArray())
                {
                    if (ContainsRawFileData(item))
                    {
                        return true;
                    }
                }
                return false;
            default:
                return false;
        }
    }

    private static bool IsInputFile(JsonElement element)
        => element.TryGetProperty("type", out JsonElement t)
            && t.ValueKind == JsonValueKind.String
            && string.Equals(t.GetString(), "input_file", StringComparison.Ordinal);

    private static void RewriteElement(JsonElement element, Utf8JsonWriter writer)
    {
        switch (element.ValueKind)
        {
            case JsonValueKind.Object:
                writer.WriteStartObject();
                bool inputFile = IsInputFile(element);
                foreach (JsonProperty prop in element.EnumerateObject())
                {
                    writer.WritePropertyName(prop.Name);
                    if (inputFile
                        && prop.Name == "file_data"
                        && prop.Value.ValueKind == JsonValueKind.String
                        && prop.Value.GetString() is { Length: > 0 } s
                        && !s.StartsWith("data:", StringComparison.Ordinal))
                    {
                        writer.WriteStringValue("data:application/octet-stream;base64," + s);
                    }
                    else
                    {
                        RewriteElement(prop.Value, writer);
                    }
                }
                writer.WriteEndObject();
                break;
            case JsonValueKind.Array:
                writer.WriteStartArray();
                foreach (JsonElement item in element.EnumerateArray())
                {
                    RewriteElement(item, writer);
                }
                writer.WriteEndArray();
                break;
            case JsonValueKind.String:
                writer.WriteStringValue(element.GetString());
                break;
            case JsonValueKind.Number:
                writer.WriteRawValue(element.GetRawText(), skipInputValidation: true);
                break;
            case JsonValueKind.True:
                writer.WriteBooleanValue(true);
                break;
            case JsonValueKind.False:
                writer.WriteBooleanValue(false);
                break;
            case JsonValueKind.Null:
                writer.WriteNullValue();
                break;
        }
    }
}
