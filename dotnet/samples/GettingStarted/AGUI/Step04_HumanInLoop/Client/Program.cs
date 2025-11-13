// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AGUI;
using Microsoft.Extensions.AI;

string serverUrl = Environment.GetEnvironmentVariable("AGUI_SERVER_URL") ?? "http://localhost:5100";

// Connect to the AG-UI server
using HttpClient httpClient = new()
{
    Timeout = TimeSpan.FromSeconds(60)
};

AGUIChatClient chatClient = new(httpClient, serverUrl);

// Create agent
ChatClientAgent baseAgent = chatClient.CreateAIAgent(
    name: "AGUIAssistant",
    instructions: "You are a helpful assistant.");

// Use default JSON serializer options
JsonSerializerOptions jsonSerializerOptions = JsonSerializerOptions.Default;

// Wrap the agent with ServerFunctionApprovalClientAgent
ServerFunctionApprovalClientAgent agent = new(baseAgent, jsonSerializerOptions);

List<ChatMessage> messages = [];
AgentThread? thread = null;

Console.ForegroundColor = ConsoleColor.White;
Console.WriteLine("Ask a question (or type 'exit' to quit):");
Console.ResetColor();

string? input;
while ((input = Console.ReadLine()) != null && !input.Equals("exit", StringComparison.OrdinalIgnoreCase))
{
    if (string.IsNullOrWhiteSpace(input))
    {
        continue;
    }

    messages.Add(new ChatMessage(ChatRole.User, input));
    Console.WriteLine();

#pragma warning disable MEAI001
    List<AIContent> approvalResponses = [];

    do
    {
        approvalResponses.Clear();

        List<AgentRunResponseUpdate> chatResponseUpdates = [];
        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync(messages, thread, cancellationToken: default))
        {
            chatResponseUpdates.Add(update);
            foreach (AIContent content in update.Contents)
            {
                switch (content)
                {
                    case FunctionApprovalRequestContent approvalRequest:
                        DisplayApprovalRequest(approvalRequest);

                        Console.Write($"\nApprove '{approvalRequest.FunctionCall.Name}'? (yes/no): ");
                        string? userInput = Console.ReadLine();
                        bool approved = userInput?.ToUpperInvariant() is "YES" or "Y";

                        FunctionApprovalResponseContent approvalResponse = approvalRequest.CreateResponse(approved);

                        if (approvalRequest.AdditionalProperties != null)
                        {
                            approvalResponse.AdditionalProperties = new AdditionalPropertiesDictionary();
                            foreach (var kvp in approvalRequest.AdditionalProperties)
                            {
                                approvalResponse.AdditionalProperties[kvp.Key] = kvp.Value;
                            }
                        }

                        approvalResponses.Add(approvalResponse);
                        break;

                    case TextContent textContent:
                        Console.ForegroundColor = ConsoleColor.Cyan;
                        Console.Write(textContent.Text);
                        Console.ResetColor();
                        break;

                    case FunctionCallContent functionCall:
                        Console.ForegroundColor = ConsoleColor.Green;
                        Console.WriteLine($"[Tool Call - Name: {functionCall.Name}]");
                        if (functionCall.Arguments is { } arguments)
                        {
                            Console.WriteLine($"  Parameters: {JsonSerializer.Serialize(arguments)}");
                        }
                        Console.ResetColor();
                        break;

                    case FunctionResultContent functionResult:
                        Console.ForegroundColor = ConsoleColor.Magenta;
                        Console.WriteLine($"[Tool Result: {functionResult.Result}]");
                        Console.ResetColor();
                        break;

                    case ErrorContent error:
                        Console.ForegroundColor = ConsoleColor.Red;
                        Console.WriteLine($"[Error: {error.Message}]");
                        Console.ResetColor();
                        break;
                }
            }
        }

        AgentRunResponse response = chatResponseUpdates.ToAgentRunResponse();
        messages.AddRange(response.Messages);
        foreach (AIContent approvalResponse in approvalResponses)
        {
            messages.Add(new ChatMessage(ChatRole.Tool, [approvalResponse]));
        }
    }
    while (approvalResponses.Count > 0);
#pragma warning restore MEAI001

    Console.WriteLine("\n");
    Console.ForegroundColor = ConsoleColor.White;
    Console.WriteLine("Ask another question (or type 'exit' to quit):");
    Console.ResetColor();
}

#pragma warning disable MEAI001
static void DisplayApprovalRequest(FunctionApprovalRequestContent approvalRequest)
{
    Console.ForegroundColor = ConsoleColor.Yellow;
    Console.WriteLine();
    Console.WriteLine("============================================================");
    Console.WriteLine("APPROVAL REQUIRED");
    Console.WriteLine("============================================================");
    Console.WriteLine($"Function: {approvalRequest.FunctionCall.Name}");

    if (approvalRequest.FunctionCall.Arguments != null)
    {
        Console.WriteLine("Arguments:");
        foreach (var arg in approvalRequest.FunctionCall.Arguments)
        {
            Console.WriteLine($"  {arg.Key} = {arg.Value}");
        }
    }

    Console.WriteLine("============================================================");
    Console.ResetColor();
}
#pragma warning restore MEAI001
