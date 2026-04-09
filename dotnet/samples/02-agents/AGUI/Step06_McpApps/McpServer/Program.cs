// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using ModelContextProtocol.Protocol;
using ModelContextProtocol.Server;
using Step06_McpApps.McpServer;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddMcpServer()
    .WithHttpTransport(o => o.Stateless = true)
    .WithTools<GetTimeApp>()
    .WithResources<GetTimeApp>()
    ;

var app = builder.Build();

app.MapGet("/", () => "Hello World!");
app.MapMcp("/mcp");

app.Run();

namespace Step06_McpApps.McpServer
{
    public class GetTimeApp()
    {
        private const string URI = "ui://get-time.html";

        [McpServerTool(Name = "get-time"), Description("Gets the current time.")]
        [McpMeta("ui", JsonValue = $$"""{"resourceUri":"{{URI}}"}""")]
        [McpMeta("ui/resourceUri", URI)]
        public async Task<IEnumerable<ContentBlock>> GetTimeAsync()
        {
            await Task.Yield();
            return [new TextContentBlock { Text = DateTime.UtcNow.ToString("O") }];
        }

        [McpServerResource(UriTemplate = URI, MimeType = "text/html;profile=mcp-app")]
        public async Task<string> GetTimeUIResourceAsync() => await File.ReadAllTextAsync("./dist/get-time.html");
    }
}