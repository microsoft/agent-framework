// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use Computer Use Tool with AI Agents.

using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

namespace Demo.ComputerUse;

internal sealed class Program
{
    private static async Task Main(string[] args)
    {
        string endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
        string deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "computer-use-preview";

        // Get a client to create/retrieve/delete server side agents with Azure Foundry Agents.
        AIProjectClient aiProjectClient = new(new Uri(endpoint), new AzureCliCredential());
        const string AgentInstructions = @"
                    You are a computer automation assistant. 
                    
                    Be direct and efficient. When you reach the search results page, read and describe the actual search result titles and descriptions you can see.
                ";

        const string AgentNameMEAI = "ComputerAgent-MEAI";
        const string AgentNameNative = "ComputerAgent-NATIVE";

        // Option 1 - Using ComputerUseTool + AgentOptions (MEAI + AgentFramework)
        // Create AIAgent directly
        AIAgent agentOption1 = await aiProjectClient.CreateAIAgentAsync(
            name: AgentNameMEAI,
            model: deploymentName,
            instructions: AgentInstructions,
            description: "Computer automation agent with screen interaction capabilities.",
            tools: [
                    ResponseTool.CreateComputerTool(ComputerToolEnvironment.Browser, 1026, 769).AsAITool(),
                ]);

        // Option 2 - Using PromptAgentDefinition SDK native type
        // Create the server side agent version
        AIAgent agentOption2 = await aiProjectClient.CreateAIAgentAsync(
            name: AgentNameNative,
            creationOptions: new AgentVersionCreationOptions(
                new PromptAgentDefinition(model: deploymentName)
                {
                    Instructions = AgentInstructions,
                    Tools = { ResponseTool.CreateComputerTool(
                environment: new ComputerToolEnvironment("windows"),
                displayWidth: 1026,
                displayHeight: 769) }
                })
        );

        // Either invoke option1 or option2 agent, should have same result
        // Option 1
        await InvokeComputerUseAgentAsync(agentOption1);

        // Option 2
        //await InvokeComputerUseAgentAsync(agentOption2);

        // Cleanup by agent name removes the agent version created.
        await aiProjectClient.Agents.DeleteAgentAsync(agentOption1.Name);
        await aiProjectClient.Agents.DeleteAgentAsync(agentOption2.Name);
    }

    private static async Task InvokeComputerUseAgentAsync(AIAgent agent)
    {
        // Load screenshot assets
        Dictionary<string, byte[]> screenshots = ComputerUseUtil.LoadScreenshotAssets();

        ChatOptions chatOptions = new();
        ResponseCreationOptions responseCreationOptions = new()
        {
            TruncationMode = ResponseTruncationMode.Auto
        };
        chatOptions.RawRepresentationFactory = (_) => responseCreationOptions;
        ChatClientAgentRunOptions runOptions = new(chatOptions)
        {
            AllowBackgroundResponses = true,
        };

        AgentThread thread = agent.GetNewThread();

        ChatMessage message = new(ChatRole.User, [
            new TextContent("I need you to help me search for 'OpenAI news'. Please type 'OpenAI news' and submit the search. Once you see search results, the task is complete."),
            new DataContent(new BinaryData(screenshots["browser_search"]), "image/png")
        ]);

        // Initial request with screenshot - start with Bing search page
        Console.WriteLine("Starting computer automation session (initial screenshot: cua_browser_search.png)...");

        AgentRunResponse runResponse = await agent.RunAsync(message, thread: thread, options: runOptions);

        // Main interaction loop
        const int MaxIterations = 10;
        int iteration = 0;
        // Initialize state machine
        SearchState currentState = SearchState.Initial;
        string initialCallId = string.Empty;

        while (true)
        {
            // Poll until the response is complete.
            while (runResponse.ContinuationToken is { } token)
            {
                // Wait before polling again.
                await Task.Delay(TimeSpan.FromSeconds(2));

                // Continue with the token.
                runOptions.ContinuationToken = token;

                runResponse = await agent.RunAsync(thread, runOptions);
            }

            Console.WriteLine($"Agent response received (ID: {runResponse.ResponseId})");

            if (iteration >= MaxIterations)
            {
                Console.WriteLine($"\nReached maximum iterations ({MaxIterations}). Stopping.");
                break;
            }

            iteration++;
            Console.WriteLine($"\n--- Iteration {iteration} ---");

            // Check for computer calls in the response
            IEnumerable<ComputerCallResponseItem> computerCallResponseItems = runResponse.Messages
                .SelectMany(x => x.Contents)
                .Where(c => c.RawRepresentation is ComputerCallResponseItem and not null)
                .Select(c => (ComputerCallResponseItem)c.RawRepresentation!);

            ComputerCallResponseItem? firstComputerCall = computerCallResponseItems.FirstOrDefault();
            if (firstComputerCall is null)
            {
                Console.WriteLine("No computer call actions found. Ending interaction.");
                Console.WriteLine($"Final Response: {runResponse}");
                break;
            }

            // Process the first computer call response
            ComputerCallAction action = firstComputerCall.Action;
            string currentCallId = firstComputerCall.CallId;

            // Set the initial computer call ID for tracking and subsequent responses.
            if (string.IsNullOrEmpty(initialCallId))
            {
                initialCallId = currentCallId;
            }

            Console.WriteLine($"Processing computer call (ID: {currentCallId})");

            // Simulate executing the action and taking a screenshot
            (SearchState CurrentState, byte[] ImageBytes) screenInfo = ComputerUseUtil.HandleComputerActionAndTakeScreenshot(action, currentState, screenshots);
            currentState = screenInfo.CurrentState;

            Console.WriteLine("Sending action result back to agent...");

            AIContent content = new()
            {
                RawRepresentation = new ComputerCallOutputResponseItem(
                    initialCallId,
                    output: ComputerCallOutput.CreateScreenshotOutput(new BinaryData(screenInfo.ImageBytes), "image/png"))
            };

            // Follow-up message with action result and new screenshot
            message = new(ChatRole.User, [content]);
            runResponse = await agent.RunAsync(message, thread: thread, options: runOptions);
        }
    }
}
