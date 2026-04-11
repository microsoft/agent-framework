// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use the Computer Use tool with AIProjectClient.AsAIAgent(...).

using Azure.AI.Projects;
using Azure.Identity;
using Demo.ComputerUse;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_COMPUTER_USE_DEPLOYMENT_NAME") ?? "computer-use-preview";

AIProjectClient projectClient = new(new Uri(endpoint), new DefaultAzureCredential());
using IHostedFileClient fileClient = projectClient.GetProjectOpenAIClient().AsIHostedFileClient();

AIAgent agent = projectClient.AsAIAgent(
    model: deploymentName,
    name: "ComputerAgent",
    instructions: "You are a computer automation assistant.",
    tools: [FoundryAITool.CreateComputerTool(ComputerToolEnvironment.Browser, 1026, 769)]);

Dictionary<string, string> screenshots = [];

try
{
    // Upload pre-captured screenshots that simulate browser state transitions.
    screenshots = await ComputerUseUtil.UploadScreenshotAssetsAsync(fileClient);

    // Enable auto-truncation for the Responses API.
    ChatClientAgentRunOptions runOptions = new()
    {
        ChatOptions = new ChatOptions
        {
            RawRepresentationFactory = (_) => new CreateResponseOptions() { TruncationMode = ResponseTruncationMode.Auto },
        }
    };

    // Send the initial request with a screenshot of the browser.
    ChatMessage message = new(ChatRole.User, [
        new TextContent("Search for 'OpenAI news'. Type it and submit. Once you see results, the task is complete."),
        new AIContent() { RawRepresentation = ResponseContentPart.CreateInputImagePart(imageFileId: screenshots["browser_search"], imageDetailLevel: ResponseImageDetailLevel.High) }
    ]);

    Console.WriteLine("Starting computer use session...");

    AgentSession session = await agent.CreateSessionAsync();
    AgentResponse response = await agent.RunAsync(message, session: session, options: runOptions);

    SearchState currentState = SearchState.Initial;

    for (int i = 0; i < 10; i++)
    {
        // Find the next computer call action.
        ComputerCallResponseItem? computerCall = response.Messages
            .SelectMany(m => m.Contents)
            .Select(c => c.RawRepresentation as ComputerCallResponseItem)
            .FirstOrDefault(item => item is not null);

        if (computerCall is null)
        {
            if (currentState == SearchState.PressedEnter)
            {
                Console.WriteLine("No more computer actions. Done.");
                Console.WriteLine(response);
                break;
            }

            // Check if the agent is asking for confirmation to proceed, and if so, respond affirmatively.
            TextContent? textContent = response.Messages
                .Where(m => m.Role == ChatRole.Assistant)
                .SelectMany(m => m.Contents.OfType<TextContent>())
                .FirstOrDefault();

            if (textContent?.Text is { } text && (
                text.Contains("Would you like me") ||
                text.Contains("Should I") ||
                text.Contains("proceed") ||
                text.Contains('?')))
            {
                response = await agent.RunAsync("Please proceed.", session, runOptions);
                continue;
            }

            break;
        }

        Console.WriteLine($"[{i + 1}] Action: {computerCall!.Action.Kind}");

        // Simulate the action and get the resulting screenshot.
        (currentState, string fileId) = await ComputerUseUtil.GetScreenshotAsync(computerCall.Action, currentState, screenshots);

        // Send the screenshot back as the computer call output.
        AIContent callOutput = new()
        {
            RawRepresentation = new ComputerCallOutputResponseItem(
                computerCall.CallId,
                output: ComputerCallOutput.CreateScreenshotOutput(screenshotImageFileId: fileId))
        };

        response = await agent.RunAsync([new ChatMessage(ChatRole.User, [callOutput])], session: session, options: runOptions);
    }
}
finally
{
    await ComputerUseUtil.EnsureDeleteScreenshotAssetsAsync(fileClient, screenshots);
}
