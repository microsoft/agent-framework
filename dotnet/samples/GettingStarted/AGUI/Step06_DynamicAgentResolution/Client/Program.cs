// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AGUI;
using Microsoft.Extensions.AI;

string serverUrl = Environment.GetEnvironmentVariable("AGUI_SERVER_URL") ?? "http://localhost:8888";

Console.WriteLine("AG-UI Dynamic Agent Resolution Demo");
Console.WriteLine("====================================\n");
Console.WriteLine("Available agents: general, code, writer");
Console.WriteLine($"Server URL: {serverUrl}\n");

using HttpClient httpClient = new()
{
    Timeout = TimeSpan.FromSeconds(60)
};

while (true)
{
    // Get agent selection
    Console.Write("Select agent (general/code/writer) or 'quit': ");
    string? agentId = Console.ReadLine()?.Trim();

    if (string.IsNullOrWhiteSpace(agentId) || agentId.Equals("quit", StringComparison.OrdinalIgnoreCase) || agentId == ":q")
    {
        break;
    }

    // Create client for specific agent
    string agentUrl = $"{serverUrl.TrimEnd('/')}/agents/{agentId}";
    AGUIChatClient chatClient = new(httpClient, agentUrl);

    AIAgent agent = chatClient.CreateAIAgent(
        name: $"agui-client-{agentId}",
        description: $"AG-UI Client for {agentId} agent");

    AgentThread thread = agent.GetNewThread();
    List<ChatMessage> messages = [];

    Console.WriteLine($"\nConnected to '{agentId}' agent. Type ':back' to switch agents.\n");

    // Conversation loop for this agent
    while (true)
    {
        Console.Write($"[{agentId}] User: ");
        string? message = Console.ReadLine();

        if (string.IsNullOrWhiteSpace(message))
        {
            continue;
        }

        if (message == ":back")
        {
            Console.WriteLine();
            break;
        }

        if (message == ":q" || message == "quit")
        {
            return;
        }

        messages.Add(new ChatMessage(ChatRole.User, message));

        // Stream the response
        Console.Write($"[{agentId}] Assistant: ");

        try
        {
            await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync(messages, thread))
            {
                foreach (AIContent content in update.Contents)
                {
                    if (content is TextContent textContent)
                    {
                        Console.Write(textContent.Text);
                    }
                }
            }

            Console.WriteLine("\n");
        }
        catch (HttpRequestException ex) when (ex.StatusCode == System.Net.HttpStatusCode.NotFound)
        {
            Console.ForegroundColor = ConsoleColor.Red;
            Console.WriteLine($"\nAgent '{agentId}' not found. Please try a different agent.\n");
            Console.ResetColor();
            break;
        }
    }
}
