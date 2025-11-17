// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AGUI;
using Microsoft.Extensions.AI;

string serverUrl = Environment.GetEnvironmentVariable("AGUI_SERVER_URL") ?? "http://localhost:8888";

Console.WriteLine($"Connecting to AG-UI server at: {serverUrl}\n");

// Create the AG-UI client agent
using HttpClient httpClient = new()
{
    Timeout = TimeSpan.FromSeconds(60)
};

AGUIChatClient chatClient = new(httpClient, serverUrl);

AIAgent agent = chatClient.CreateAIAgent(
    name: "agui-client",
    description: "AG-UI Client Agent");

AgentThread thread = agent.GetNewThread();
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
        string? threadId = null;

        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync(messages, thread))
        {
            ChatResponseUpdate chatUpdate = update.AsChatResponseUpdate();

            // First update indicates run started
            if (isFirstUpdate)
            {
                threadId = chatUpdate.ConversationId;
                Console.ForegroundColor = ConsoleColor.Yellow;
                Console.WriteLine($"\n[Run Started - Thread: {chatUpdate.ConversationId}, Run: {chatUpdate.ResponseId}]");
                Console.ResetColor();
                isFirstUpdate = false;
            }

            // Display streaming content
            foreach (AIContent content in update.Contents)
            {
                switch (content)
                {
                    case TextContent textContent:
                        Console.ForegroundColor = ConsoleColor.Cyan;
                        Console.Write(textContent.Text);
                        Console.ResetColor();
                        break;

                    case FunctionCallContent functionCallContent:
                        Console.ForegroundColor = ConsoleColor.Green;
                        Console.WriteLine($"\n[Function Call - Name: {functionCallContent.Name}]");

                        // Display individual parameters
                        if (functionCallContent.Arguments != null)
                        {
                            foreach (var kvp in functionCallContent.Arguments)
                            {
                                Console.WriteLine($"  Parameter: {kvp.Key} = {kvp.Value}");
                            }
                        }
                        Console.ResetColor();
                        break;

                    case FunctionResultContent functionResultContent:
                        Console.ForegroundColor = ConsoleColor.Magenta;
                        Console.WriteLine($"\n[Function Result - CallId: {functionResultContent.CallId}]");

                        if (functionResultContent.Exception != null)
                        {
                            Console.WriteLine($"  Exception: {functionResultContent.Exception}");
                        }
                        else
                        {
                            Console.WriteLine($"  Result: {functionResultContent.Result}");
                        }
                        Console.ResetColor();
                        break;

                    case ErrorContent errorContent:
                        Console.ForegroundColor = ConsoleColor.Red;
                        Console.WriteLine($"\n[Error: {errorContent.Message}]");
                        Console.ResetColor();
                        break;
                }
            }
        }

        Console.ForegroundColor = ConsoleColor.Green;
        Console.WriteLine($"\n[Run Finished - Thread: {threadId}]");
        Console.ResetColor();
    }
}
catch (Exception ex)
{
    Console.WriteLine($"\nAn error occurred: {ex.Message}");
}
