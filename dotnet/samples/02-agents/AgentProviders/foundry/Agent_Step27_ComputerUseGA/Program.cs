// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use the generally available (GA) computer tool, created with the parameterless
// FoundryAITool.CreateComputerTool(), with an AIAgent. Each computer call returned by the model carries an ordered
// batch of actions; the application runs all of them and then sends back a single screenshot.
//
// Microsoft Foundry does not accept the GA "computer" tool type yet, so the sample currently runs against the public
// OpenAI Responses API. The Foundry setup is kept below, commented out: once Foundry supports the GA tool, swap the
// two agent setups and the rest of the sample works unchanged.

using Demo.ComputerUseGA;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Responses;

// Microsoft Foundry setup (see below): uncomment once Foundry supports the GA computer tool.
// using Azure.AI.Projects;
// using Azure.Identity;

// Public OpenAI Responses API (active until Microsoft Foundry supports the GA computer tool).
string apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY") ?? throw new InvalidOperationException("OPENAI_API_KEY is not set.");
string model = Environment.GetEnvironmentVariable("OPENAI_CHAT_MODEL_NAME") ?? "gpt-5.4";

AIAgent agent = new OpenAIClient(apiKey)
    .GetResponsesClient()
    .AsIChatClient(model)
    .AsAIAgent(
        name: "ComputerAgent",
        instructions: "You are a computer automation assistant.",
        tools: [FoundryAITool.CreateComputerTool()]);

// Microsoft Foundry: uncomment this block (and the Azure usings at the top) once Foundry supports the GA computer
// tool, then remove the OpenAI block above.
//
// string endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
// string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_COMPUTER_USE_DEPLOYMENT_NAME") ?? "gpt-5.4";
//
// // WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// // In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// // latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
// AIProjectClient projectClient = new(new Uri(endpoint), new DefaultAzureCredential());
//
// AIAgent agent = projectClient.AsAIAgent(
//     model: deploymentName,
//     name: "ComputerAgent",
//     instructions: "You are a computer automation assistant.",
//     tools: [FoundryAITool.CreateComputerTool()]);

Dictionary<string, BinaryData> screenshots = ComputerUseUtil.LoadScreenshots();

// Send the initial request with a screenshot of the browser.
ChatMessage message = new(ChatRole.User, [
    new TextContent("Search for 'OpenAI news'. Type it and submit. Once you see results, the task is complete."),
    new DataContent(screenshots["browser_search"].ToMemory(), "image/jpeg")
]);

Console.WriteLine("Starting computer use session...");

AgentSession session = await agent.CreateSessionAsync();
AgentResponse response = await agent.RunAsync(message, session: session);

SearchState currentState = SearchState.Initial;

for (int i = 0; i < 10; i++)
{
    // Find the next computer call.
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

        // The model may ask for confirmation before acting. Answer and continue.
        if (response.Text.Contains('?'))
        {
            Console.WriteLine($"Model asked: {response.Text}");
            response = await agent.RunAsync("Please proceed.", session);
            continue;
        }

        Console.WriteLine(response);
        break;
    }

    // Run every action of the batch in order, then capture a single screenshot.
    foreach (ComputerActionRequest action in ComputerUseUtil.GetActions(computerCall))
    {
        Console.WriteLine($"[{i + 1}] Action: {action.Type}");
        currentState = await ComputerUseUtil.ApplyAsync(action, currentState);
    }

    ComputerCallOutputResponseItem callOutput = new(
        computerCall.CallId,
        ComputerCallOutput.CreateScreenshotOutput(screenshots[ComputerUseUtil.GetScreenshotKey(currentState)], "image/jpeg"));

    // The model can flag an action as risky with pending safety checks. A real application must show them to the user
    // and acknowledge them only after the user confirms; this simulation acknowledges them automatically.
    foreach (ComputerCallSafetyCheck safetyCheck in computerCall.PendingSafetyChecks)
    {
        Console.WriteLine($"Acknowledging safety check: {safetyCheck.Code}");
        callOutput.AcknowledgedSafetyChecks.Add(safetyCheck);
    }

    // Send the screenshot back as the computer call output.
    response = await agent.RunAsync([new ChatMessage(ChatRole.User, [new AIContent { RawRepresentation = callOutput }])], session);
}
