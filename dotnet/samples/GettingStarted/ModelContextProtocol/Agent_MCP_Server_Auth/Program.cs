// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with tools from an MCP Server that requires authentication.

using System;
using System.Diagnostics;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.Logging;
using ModelContextProtocol.Client;
using OpenAI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// We can customize a shared HttpClient with a custom handler if desired
using var sharedHandler = new SocketsHttpHandler
{
    PooledConnectionLifetime = TimeSpan.FromMinutes(2),
    PooledConnectionIdleTimeout = TimeSpan.FromMinutes(1)
};
using var httpClient = new HttpClient(sharedHandler);

var consoleLoggerFactory = LoggerFactory.Create(builder => builder.AddConsole());

// Create SSE client transport for the MCP server
var serverUrl = "http://localhost:7071/";
var transport = new SseClientTransport(new()
{
    Endpoint = new Uri(serverUrl),
    Name = "Secure Weather Client",
    OAuth = new()
    {
        ClientName = "ProtectedMcpClient",
        RedirectUri = new Uri("http://localhost:1179/callback"),
        AuthorizationRedirectDelegate = HandleAuthorizationUrlAsync,
    }
}, httpClient, consoleLoggerFactory);

// Create an MCPClient for the protected MCP server
await using var mcpClient = await McpClientFactory.CreateAsync(transport, loggerFactory: consoleLoggerFactory);

// Retrieve the list of tools available on the GitHub server
var mcpTools = await mcpClient.ListToolsAsync().ConfigureAwait(false);

AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
     .GetChatClient(deploymentName)
     .CreateAIAgent(instructions: "You answer questions related to the weather.", tools: [.. mcpTools]);

// Invoke the agent and output the text result.
Console.WriteLine(await agent.RunAsync("Get current weather alerts for New York?"));

// Handles the OAuth authorization URL by starting a local HTTP server and opening a browser.
// This implementation demonstrates how SDK consumers can provide their own authorization flow.
static async Task<string?> HandleAuthorizationUrlAsync(Uri authorizationUrl, Uri redirectUri, CancellationToken cancellationToken)
{
    Console.WriteLine("Starting OAuth authorization flow...");
    Console.WriteLine($"Opening browser to: {authorizationUrl}");

    var listenerPrefix = redirectUri.GetLeftPart(UriPartial.Authority);
    if (!listenerPrefix.EndsWith("/", StringComparison.InvariantCultureIgnoreCase))
    {
        listenerPrefix += "/";
    }

    using var listener = new HttpListener();
    listener.Prefixes.Add(listenerPrefix);

    try
    {
        listener.Start();
        Console.WriteLine($"Listening for OAuth callback on: {listenerPrefix}");

        OpenBrowser(authorizationUrl);

        var context = await listener.GetContextAsync();
        var query = HttpUtility.ParseQueryString(context.Request.Url?.Query ?? string.Empty);
        var code = query["code"];
        var error = query["error"];

        const string ResponseHtml = "<html><body><h1>Authentication complete</h1><p>You can close this window now.</p></body></html>";
        byte[] buffer = Encoding.UTF8.GetBytes(ResponseHtml);
        context.Response.ContentLength64 = buffer.Length;
        context.Response.ContentType = "text/html";
        context.Response.OutputStream.Write(buffer, 0, buffer.Length);
        context.Response.Close();

        if (!string.IsNullOrEmpty(error))
        {
            Console.WriteLine($"Auth error: {error}");
            return null;
        }

        if (string.IsNullOrEmpty(code))
        {
            Console.WriteLine("No authorization code received");
            return null;
        }

        Console.WriteLine("Authorization code received successfully.");
        return code;
    }
    catch (Exception ex)
    {
        Console.WriteLine($"Error getting auth code: {ex.Message}");
        return null;
    }
    finally
    {
        if (listener.IsListening)
        {
            listener.Stop();
        }
    }
}

// Opens the specified URL in the default browser.
static void OpenBrowser(Uri url)
{
    try
    {
        var psi = new ProcessStartInfo
        {
            FileName = url.ToString(),
            UseShellExecute = true
        };
        Process.Start(psi);
    }
    catch (Exception ex)
    {
        Console.WriteLine($"Error opening browser. {ex.Message}");
        Console.WriteLine($"Please manually open this URL: {url}");
    }
}
