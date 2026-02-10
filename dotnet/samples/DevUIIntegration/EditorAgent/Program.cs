// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Extensions.AI;

var builder = WebApplication.CreateBuilder(args);

builder.AddServiceDefaults();

builder.AddAzureChatCompletionsClient(connectionName: "foundry",
    configureSettings: settings =>
        {
            settings.TokenCredential = new DefaultAzureCredential();
            settings.EnableSensitiveTelemetryData = true;
        })
    .AddChatClient("gpt-4.1");

builder.AddAIAgent("editor", (sp, key) =>
{
    var chatClient = sp.GetRequiredService<IChatClient>();
    return new ChatClientAgent(
        chatClient,
        name: key,
        instructions: "You edit short stories to improve grammar and style, ensuring the stories are less than 300 words. Once finished editing, you select a title and format the story for publishing.",
        tools: [AIFunctionFactory.Create(FormatStory)]
    );
});

// Register services for OpenAI responses and conversations
builder.Services.AddOpenAIResponses();
builder.Services.AddOpenAIConversations();

var app = builder.Build();

// Map OpenAI API endpoints — DevUI aggregator routes requests here
app.MapOpenAIResponses();
app.MapOpenAIConversations();

app.MapDefaultEndpoints();

app.Run();

[Description("Formats the story for publication, revealing its title.")]
static string FormatStory(string title, string story) => $"""
    **Title**: {title}

    {story}
    """;
