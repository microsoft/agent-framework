// Copyright (c) Microsoft. All rights reserved.

// DevUI File-Search Agent (Azure OpenAI backend) — CU extraction + file_search RAG.
//
// This sample hosts an Azure-OpenAI–backed agent behind the DevUI middleware
// and wires the Content Understanding provider with the `FileSearchConfig.FromOpenAI`
// backend. Upload large or multi-modal files in the browser; the provider:
//   1. extracts markdown via CU (handles scanned PDFs, audio, video),
//   2. uploads the extracted markdown to an Azure OpenAI vector store,
//   3. surfaces the file_search tool on the agent's context for token-efficient RAG.
//
// The vector store is auto-expiring (`expires_after = 1 day, last_active_at`) so
// inactive sample sessions are cleaned up automatically. The CU provider's
// DisposeAsync deletes the per-file uploads at app shutdown.
//
// Environment variables:
//   AZURE_OPENAI_ENDPOINT                  — Azure OpenAI endpoint URL
//   AZURE_OPENAI_DEPLOYMENT_NAME           — Chat-model deployment name (e.g. gpt-4.1)
//   AZURE_CONTENTUNDERSTANDING_ENDPOINT    — Content Understanding endpoint URL
//
// Run:
//   dotnet run
// Then open https://localhost:50522/devui in a browser.

using System.Text;
using System.Text.Json;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI.ContentUnderstanding;
using Microsoft.Agents.AI.DevUI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Extensions.AI;
using OpenAI.Files;
using OpenAI.VectorStores;

var builder = WebApplication.CreateBuilder(args);

string openAiEndpoint = builder.Configuration["AZURE_OPENAI_ENDPOINT"]
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = builder.Configuration["AZURE_OPENAI_DEPLOYMENT_NAME"]
    ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT_NAME is not set.");
string cuEndpoint = builder.Configuration["AZURE_CONTENTUNDERSTANDING_ENDPOINT"]
    ?? throw new InvalidOperationException("AZURE_CONTENTUNDERSTANDING_ENDPOINT is not set.");

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
var credential = new DefaultAzureCredential();

// 1. Build the Azure OpenAI client used both for chat and for vector store ops.
//    NOTE: We MUST route the chat client through Azure OpenAI's Responses API
//    (GetResponsesClient), not Chat Completions (GetChatClient), because the
//    server-side `file_search` hosted tool only exists on the Responses endpoint.
//    Going through Chat Completions silently drops the HostedFileSearchTool and
//    the model has no way to retrieve indexed content.
var azureOpenAIClient = new AzureOpenAIClient(new Uri(openAiEndpoint), credential);
#pragma warning disable OPENAI001 // ResponsesClient/AsIChatClient are evaluation-only in OpenAI 2.10 — required for hosted file_search on Azure OpenAI.
var chatClient = azureOpenAIClient.GetResponsesClient().AsIChatClient(deploymentName);
#pragma warning restore OPENAI001
builder.Services.AddChatClient(chatClient);

// 2. Create a vector store up-front (auto-expires after 1 day idle so abandoned
//    DevUI sessions don't accumulate storage cost). The CU provider uploads each
//    analyzed document into this store; the file_search tool reads from it.
var vectorStoreClient = azureOpenAIClient.GetVectorStoreClient();
var vectorStoreResult = await vectorStoreClient.CreateVectorStoreAsync(
    new VectorStoreCreationOptions
    {
        Name = "devui_cu_file_search",
        ExpirationPolicy = new VectorStoreExpirationPolicy(VectorStoreExpirationAnchor.LastActiveAt, days: 1),
    });
string vectorStoreId = vectorStoreResult.Value.Id;

// 3. Build the file_search tool that the agent will use to query the vector store.
HostedFileSearchTool fileSearchTool = new() { Inputs = [new HostedVectorStoreContent(vectorStoreId)] };

// 4. CU provider with file_search wiring. Singleton — its lifecycle and any
//    background analyses span the lifetime of the web host. DisposeAsync runs
//    on app shutdown and deletes the files the provider uploaded.
builder.Services.AddSingleton(_ => new ContentUnderstandingContextProvider(
    new ContentUnderstandingContextProviderOptions(new Uri(cuEndpoint), credential)
    {
        // Foreground budget for both CU analysis polling AND vector-store upload polling.
        // Sample workloads (multi-page PDFs) typically need 10–20 s CU + 5–15 s vector-store
        // ingestion, so a 60 s budget covers the common case in a single turn. Longer media
        // (audio/video) that exceeds this budget gets a rehydration token stored on the entry
        // and resumes on the next turn; the upload then runs in that follow-up turn against a
        // fresh budget.
        MaxWait = TimeSpan.FromSeconds(60),

        // DevUI's HostedAgentResponseExecutor creates a fresh AgentSession every
        // turn, so per-session state would be lost. PerAgent keys state on the
        // agent instance instead — fine here because each DevUI agent is single-
        // user. Production multi-tenant hosts MUST keep the default PerSession.
        StateScope = StateScope.PerAgent,

        // NOTE: We cannot use FileSearchConfig.FromOpenAI(...) here because the default
        // OpenAIFileSearchBackend uploads files with purpose=user_data, which Azure OpenAI
        // rejects with `Invalid value for "purpose"`. Azure OpenAI's vector-store ingestion
        // pipeline requires purpose=assistants. We compose the FileSearchConfig manually with
        // an AzureOpenAIFileSearchBackend (defined below) that overrides Purpose accordingly.
        FileSearchConfig = new FileSearchConfig
        {
            Backend = new AzureOpenAIFileSearchBackend(azureOpenAIClient),
            VectorStoreId = vectorStoreId,
            FileSearchTool = fileSearchTool,
        },
    }));

const string AgentName = "FileSearchDocAgent";

builder.AddAIAgent(AgentName, (sp, key) =>
{
    var cu = sp.GetRequiredService<ContentUnderstandingContextProvider>();
    var client = sp.GetRequiredService<IChatClient>();
    return new ChatClientAgent(client, new ChatClientAgentOptions
    {
        Name = key,
        ChatOptions = new ChatOptions
        {
            ModelId = deploymentName,
            Instructions = "You are a helpful document analysis assistant with RAG capabilities. "
                + "When a user uploads files, they are automatically analyzed using Azure Content Understanding "
                + "and indexed in a vector store for efficient retrieval. "
                + "Analysis takes time (seconds for documents, longer for audio/video) — if a document "
                + "is still pending, let the user know and suggest they ask again shortly. "
                + "You can process PDFs, scanned documents, handwritten images, audio recordings, and video files. "
                + "Multiple files can be uploaded and queried in the same conversation. "
                + "When answering, cite specific content from the documents. "
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

Console.WriteLine($"DevUI is available at: https://localhost:50522/devui (vector store: {vectorStoreId})");
Console.WriteLine("OpenAI Responses API is available at: https://localhost:50522/v1/responses");
Console.WriteLine("Press Ctrl+C to stop the server.");

app.Run();

/// <summary>
/// Azure OpenAI–compatible file-search backend: identical to <see cref="OpenAIFileSearchBackend"/>
/// but uploads files with <see cref="FileUploadPurpose.Assistants"/> instead of
/// <c>UserData</c>. Azure OpenAI's <c>/files</c> endpoint rejects <c>user_data</c> with
/// <c>Invalid value for "purpose"</c>, so the stock <c>FileSearchConfig.FromOpenAI</c>
/// factory cannot be used against Azure OpenAI vector stores.
/// </summary>
internal sealed class AzureOpenAIFileSearchBackend : OpenAICompatFileSearchBackendBase
{
    public AzureOpenAIFileSearchBackend(AzureOpenAIClient client) : base(client) { }

    protected override FileUploadPurpose Purpose => FileUploadPurpose.Assistants;
}

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

        using JsonDocument doc = JsonDocument.Parse(body);
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
