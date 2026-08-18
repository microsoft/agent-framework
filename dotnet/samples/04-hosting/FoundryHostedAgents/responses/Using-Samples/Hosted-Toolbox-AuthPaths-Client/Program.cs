// Copyright (c) Microsoft. All rights reserved.

// Hosted Toolbox Auth Paths — OAuth consent REPL client.
//
// This REPL drives the Hosted-Toolbox-AuthPaths agent and, unlike the plain
// Using-Samples/SimpleAgent client, it understands the OAuth user-consent path.
//
// When a toolbox tool source is fronted by a per-user OAuth connection (for example a
// delegated Microsoft Graph or a Logic Apps connector), the Foundry toolbox proxy cannot
// call the tool until the end user has consented. The hosted agent surfaces that as an
// oauth_consent_request output item carrying a consent link, and marks the response
// incomplete. This is the platform-canonical consent surface (the same item the Foundry
// Bot/Teams and A2A heads render as "open link + resume"), distinct from mcp_approval_request,
// which is the generic approve/deny tool gate. This client:
//   1. Detects the oauth_consent_request and extracts the consent link.
//   2. PRINTS the consent link and waits for the user to press Enter once they have completed
//      the OAuth flow out of band. It never auto-opens a browser, so it works in headless,
//      SSH, container, and other non-GUI environments.
//   3. RE-SENDS the original prompt on the same session. The proxy now holds the user's
//      delegated token, so the retried tool call succeeds.
//
// Important: an OAuth consent request is resumed by RE-SENDING the prompt, NOT by replying
// with a ToolApprovalResponseContent. The consent request records no approval-id mapping on
// the server, so a CreateResponse(...) reply would be rejected. Only function-tool approvals
// (which this client also handles, for completeness) use the CreateResponse path.
//
// Required environment variables:
//   AZURE_AI_PROJECT_ENDPOINT  - Foundry project endpoint, or the local dev server base
//                                (e.g. http://localhost:8088/api/projects/local).
//   AZURE_AI_AGENT_NAME        - The registered server-side agent name
//                                (default: hosted-toolbox-auth-paths-agent).

using System.ClientModel.Primitives;
using System.Text.Json;
using Azure.AI.Projects;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry;
using Microsoft.Extensions.AI;

// Load .env file if present (for local development)
Env.TraversePath().Load();

Uri projectEndpoint = new(Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
    ?? Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set."));

string agentName = Environment.GetEnvironmentVariable("AZURE_AI_AGENT_NAME")
    ?? "hosted-toolbox-auth-paths-agent";

// Derive the per-agent OpenAI endpoint that hosted Foundry agents require.
Uri agentEndpoint = new($"{projectEndpoint}/agents/{agentName}/endpoint/protocols/openai");

var options = new AIProjectClientOptions();

if (projectEndpoint.Scheme == "http")
{
    // For local HTTP dev: present HTTPS to satisfy BearerTokenPolicy's TLS check, then swap
    // the scheme back to HTTP right before the request hits the wire.
    projectEndpoint = new UriBuilder(projectEndpoint) { Scheme = "https" }.Uri;
    agentEndpoint = new UriBuilder(agentEndpoint) { Scheme = "https" }.Uri;
    options.AddPolicy(new HttpSchemeRewritePolicy(), PipelinePosition.BeforeTransport);
}

var aiProjectClient = new AIProjectClient(projectEndpoint, new AzureCliCredential(), options);
FoundryAgent agent = aiProjectClient.AsAIAgent(agentEndpoint);

AgentSession session = await agent.CreateSessionAsync();

Console.ForegroundColor = ConsoleColor.Cyan;
Console.WriteLine($"""
    ══════════════════════════════════════════════════════════
    Hosted Toolbox Auth Paths — OAuth consent client
    Connected to: {agentEndpoint}
    Ask something that needs the OAuth-protected tool to trigger consent.
    Type a message or 'quit' to exit.
    ══════════════════════════════════════════════════════════
    """);
Console.ResetColor();
Console.WriteLine();

while (true)
{
    Console.ForegroundColor = ConsoleColor.Green;
    Console.Write("You> ");
    Console.ResetColor();

    string? input = Console.ReadLine();

    if (string.IsNullOrWhiteSpace(input)) { continue; }
    if (input.Equals("quit", StringComparison.OrdinalIgnoreCase)) { break; }

    try
    {
        AgentResponse response = await agent.RunAsync(input, session);

        // Resolve any consent or approval requests before showing the final answer. Each
        // round-trip either re-sends (OAuth consent) or replies with an approval decision
        // (function tools).
        while (true)
        {
            List<AIContent> contents = response.Messages
                .SelectMany(m => m.Contents)
                .ToList();

            // An OAuth consent request surfaces as an oauth_consent_request output item carrying a
            // consent link. It is resumed by RE-SENDING the prompt (no reply item), because the
            // proxy stores the user's delegated token server-side keyed to the user.
            List<string> consentUrls = contents
                .Select(TryExtractConsentUrl)
                .Where(url => url is not null)
                .Select(url => url!)
                .Distinct(StringComparer.Ordinal)
                .ToList();

            if (consentUrls.Count > 0)
            {
                Console.ForegroundColor = ConsoleColor.Magenta;
                Console.WriteLine();
                Console.WriteLine("The agent needs your OAuth consent before it can call a tool on your behalf.");
                Console.WriteLine("Open the link(s) below in any browser and complete the sign-in / consent:");
                foreach (string url in consentUrls)
                {
                    Console.WriteLine();
                    Console.WriteLine(url);
                }
                Console.WriteLine();
                Console.ResetColor();

                // Wait for the user to finish consent out of band. They can press Enter once done.
                // The value is not needed to resume — the proxy stores the delegated token
                // server-side keyed to the user.
                Console.Write("After completing consent, press Enter to continue... ");
                _ = Console.ReadLine();

                // Re-send the SAME prompt on the SAME session. The proxy now holds the user's
                // delegated token, so the retried tool call succeeds. Do NOT CreateResponse here.
                response = await agent.RunAsync(input, session);
                continue;
            }

            // Function-tool approval path (Y/N), included so the client also handles agents
            // that mix human-in-the-loop function approvals with OAuth consent.
            List<ToolApprovalRequestContent> approvals = contents
                .OfType<ToolApprovalRequestContent>()
                .ToList();

            if (approvals.Count == 0)
            {
                break;
            }

            List<ChatMessage> decisions = approvals.ConvertAll(approval =>
            {
                string name = (approval.ToolCall as FunctionCallContent)?.Name ?? "tool";
                Console.ForegroundColor = ConsoleColor.Yellow;
                Console.Write($"Approve tool call '{name}'? [Y/N] ");
                Console.ResetColor();
                bool approved = Console.ReadLine()?.Trim().Equals("Y", StringComparison.OrdinalIgnoreCase) ?? false;
                return new ChatMessage(ChatRole.User, [approval.CreateResponse(approved)]);
            });

            response = await agent.RunAsync(decisions, session);
        }

        Console.ForegroundColor = ConsoleColor.Yellow;
        Console.WriteLine($"Agent> {response}");
        Console.ResetColor();
    }
    catch (Exception ex)
    {
        Console.ForegroundColor = ConsoleColor.Red;
        Console.WriteLine($"Error: {ex.Message}");
        Console.ResetColor();
    }

    Console.WriteLine();
}

Console.WriteLine("Goodbye!");

// ── Helpers ─────────────────────────────────────────────────────────────────────

// Extracts an OAuth consent link from a response content, or returns null when the content is
// not a consent request. The canonical surface is an `oauth_consent_request` output item, which
// the high-level client exposes through AIContent.RawRepresentation (its `ConsentLink` field
// carries the URL). For resilience this also handles a consent URL surfaced inside a
// ToolApprovalRequestContent payload (the older mcp_approval_request shape). Plain
// human-in-the-loop function approvals carry no URL and return null.
static string? TryExtractConsentUrl(AIContent content)
{
    // 1) Canonical: oauth_consent_request output item via RawRepresentation.
    if (TryGetConsentLinkFromRaw(content.RawRepresentation) is { } fromRaw)
    {
        return fromRaw;
    }

    // 2) Back-compat: a consent URL carried in an approval request's arguments.
    if (content is ToolApprovalRequestContent approval)
    {
        return TryExtractConsentUrlFromApproval(approval);
    }

    return null;
}

// Reads a consent link from a raw oauth_consent_request item. The high-level client surfaces this
// item as a base AIContent whose RawRepresentation is an SDK response item: in the typed case it
// exposes a `ConsentLink` member, but the OpenAI Responses client parses the (non-OpenAI)
// oauth_consent_request as an *unknown* item, so the link only lives in the item's JSON. We try the
// typed member first, then fall back to serializing the persistable model and reading `consent_link`.
static string? TryGetConsentLinkFromRaw(object? raw)
{
    if (raw is null)
    {
        return null;
    }

    // Fast path: a typed consent item exposes ConsentLink directly (Uri or string).
    switch (raw.GetType().GetProperty("ConsentLink")?.GetValue(raw))
    {
        case Uri uri when LooksLikeUrl(uri.AbsoluteUri):
            return uri.AbsoluteUri;
        case string s when LooksLikeUrl(s):
            return s;
    }

    // General path: serialize the unknown response item back to JSON and read the wire fields.
    try
    {
        BinaryData json = ModelReaderWriter.Write(raw, new ModelReaderWriterOptions("J"));
        using JsonDocument doc = JsonDocument.Parse(json);
        JsonElement root = doc.RootElement;
        if (root.ValueKind == JsonValueKind.Object
            && root.TryGetProperty("type", out JsonElement typeProp)
            && typeProp.GetString() == "oauth_consent_request"
            && root.TryGetProperty("consent_link", out JsonElement linkProp)
            && linkProp.GetString() is string link
            && LooksLikeUrl(link))
        {
            return link;
        }
    }
    catch
    {
        // Not a persistable model, or no consent_link present — fall through.
    }

    return null;
}

// Scans an approval request's tool-call arguments for a consent URL (older wire shape, where a
// toolbox OAuth consent was surfaced as an mcp_approval_request carrying a consent_url argument).
static string? TryExtractConsentUrlFromApproval(ToolApprovalRequestContent approval)
{
    IDictionary<string, object?>? arguments = approval.ToolCall switch
    {
        McpServerToolCallContent mcpCall => mcpCall.Arguments,
        FunctionCallContent functionCall => functionCall.Arguments,
        _ => null,
    };

    // Only the explicit consent_url key counts (the legacy mcp_approval_request consent shape).
    // We deliberately do NOT scan arbitrary argument values for URLs, so a normal function-tool
    // approval that happens to carry a URL argument is never misread as an OAuth consent request.
    if (arguments is null || !arguments.TryGetValue("consent_url", out object? value))
    {
        return null;
    }

    return value switch
    {
        string s when LooksLikeUrl(s) => s,
        JsonElement { ValueKind: JsonValueKind.String } element
            when element.GetString() is string elementString && LooksLikeUrl(elementString) => elementString,
        _ => null,
    };
}

static bool LooksLikeUrl(string value) =>
    value.StartsWith("http://", StringComparison.OrdinalIgnoreCase)
    || value.StartsWith("https://", StringComparison.OrdinalIgnoreCase);

/// <summary>
/// For Local Development Only.
/// Rewrites HTTPS URIs to HTTP right before transport, allowing AIProjectClient to target a
/// local HTTP dev server while satisfying BearerTokenPolicy's TLS check.
/// </summary>
internal sealed class HttpSchemeRewritePolicy : PipelinePolicy
{
    public override void Process(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
    {
        RewriteScheme(message);
        ProcessNext(message, pipeline, currentIndex);
    }

    public override async ValueTask ProcessAsync(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
    {
        RewriteScheme(message);
        await ProcessNextAsync(message, pipeline, currentIndex).ConfigureAwait(false);
    }

    private static void RewriteScheme(PipelineMessage message)
    {
        var uri = message.Request.Uri!;
        if (uri.Scheme == Uri.UriSchemeHttps)
        {
            message.Request.Uri = new UriBuilder(uri) { Scheme = "http" }.Uri;
        }
    }
}
