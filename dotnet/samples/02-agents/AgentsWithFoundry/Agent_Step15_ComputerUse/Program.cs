// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use Computer Use Tool with a ChatClientAgent.

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

namespace Demo.ComputerUse;

internal sealed class Program
{
    private static async Task Main(string[] args)
    {
        const string AgentInstructions = @"
                    You are a computer automation assistant. 
                    
                    Be direct and efficient. When you reach the search results page, read and describe the actual search result titles and descriptions you can see.
                ";

        const string AgentName = "ComputerAgent-RAPI";

        string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
        string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "computer-use-preview";

        // WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
        // In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
        // latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
        AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

        // Create a AIAgent with ComputerUseTool.
        AIAgent agent = aiProjectClient.AsAIAgent(deploymentName,
            instructions: AgentInstructions,
            name: AgentName,
            description: "Computer automation agent with screen interaction capabilities.",
            tools: [
                    FoundryAITool.CreateComputerTool(ComputerToolEnvironment.Browser, 1026, 769),
                ]);

        await InvokeComputerUseAgentAsync(agent);
    }

    private static async Task InvokeComputerUseAgentAsync(AIAgent agent)
    {
        // Load screenshot assets
        Dictionary<string, byte[]> screenshots = ComputerUseUtil.LoadScreenshotAssets();

        ChatOptions chatOptions = new();
        CreateResponseOptions responseCreationOptions = new()
        {
            TruncationMode = ResponseTruncationMode.Auto
        };
        chatOptions.RawRepresentationFactory = (_) => responseCreationOptions;
        ChatClientAgentRunOptions runOptions = new(chatOptions)
        {
            AllowBackgroundResponses = true,
        };

        ChatMessage message = new(ChatRole.User, [
            new TextContent("I need you to help me search for 'OpenAI news'. Please type 'OpenAI news' and submit the search. Once you see search results, the task is complete."),
            new DataContent(new BinaryData(screenshots["browser_search"]), "image/png")
        ]);

        // Initial request with screenshot - start with Bing search page
        Console.WriteLine("Starting computer automation session (initial screenshot: cua_browser_search.png)...");

        // We use PreviousResponseId to chain calls, sending only the new computer_call_output items
        // instead of re-sending the full context.
        AgentSession session = await agent.CreateSessionAsync();
        AgentResponse response = await agent.RunAsync(message, session: session, options: runOptions);

        // Main interaction loop
        const int MaxIterations = 10;
        int iteration = 0;
        // Initialize state machine
        SearchState currentState = SearchState.Initial;

        while (true)
        {
            // Poll until the response is complete.
            while (response.ContinuationToken is { } token)
            {
                // Wait before polling again.
                await Task.Delay(TimeSpan.FromSeconds(2));

                // Continue with the token.
                runOptions.ContinuationToken = token;

                response = await agent.RunAsync(session, runOptions);
            }

            // Clear the continuation token so the next RunAsync call is a fresh request.
            runOptions.ContinuationToken = null;

            Console.WriteLine($"Agent response received (ID: {response.ResponseId})");

            if (iteration >= MaxIterations)
            {
                Console.WriteLine($"\nReached maximum iterations ({MaxIterations}). Stopping.");
                break;
            }

            iteration++;
            Console.WriteLine($"\n--- Iteration {iteration} ---");

            // Check for computer calls in the response
            IEnumerable<ComputerCallResponseItem> computerCallResponseItems = response.Messages
                .SelectMany(x => x.Contents)
                .Where(c => c.RawRepresentation is ComputerCallResponseItem and not null)
                .Select(c => (ComputerCallResponseItem)c.RawRepresentation!);

            ComputerCallResponseItem? firstComputerCall = computerCallResponseItems.FirstOrDefault();
            if (firstComputerCall is null)
            {
                Console.WriteLine("No computer call actions found. Ending interaction.");
                Console.WriteLine($"Final Response: {response}");
                break;
            }

            // Process the first computer call response
            ComputerCallAction action = firstComputerCall.Action;
            string currentCallId = firstComputerCall.CallId;

            Console.WriteLine($"Processing computer call (ID: {currentCallId})");

            // Simulate executing the action and taking a screenshot
            (SearchState CurrentState, byte[] ImageBytes) screenInfo = ComputerUseUtil.HandleComputerActionAndTakeScreenshot(action, currentState, screenshots);
            currentState = screenInfo.CurrentState;

            Console.WriteLine("Sending action result back to agent...");

            // Send only the computer_call_output — the session carries PreviousResponseId for context continuity.
            AIContent callOutput = new()
            {
                RawRepresentation = new ComputerCallOutputResponseItem(
                    currentCallId,
                    output: ComputerCallOutput.CreateScreenshotOutput(new BinaryData(screenInfo.ImageBytes), "image/png"))
            };

            response = await agent.RunAsync([new ChatMessage(ChatRole.User, [callOutput])], session: session, options: runOptions);
        }
    }
}
