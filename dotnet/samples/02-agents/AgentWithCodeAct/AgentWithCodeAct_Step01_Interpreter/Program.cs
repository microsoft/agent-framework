// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use HyperlightCodeActProvider as a sandboxed Python
// code interpreter: the model can write and execute arbitrary Python code to
// answer quantitative questions without calling any additional tools.

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hyperlight;

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";
var guestPath = Environment.GetEnvironmentVariable("HYPERLIGHT_PYTHON_GUEST_PATH") ?? throw new InvalidOperationException("HYPERLIGHT_PYTHON_GUEST_PATH is not set.");

using var codeAct = new HyperlightCodeActProvider(HyperlightCodeActProviderOptions.CreateForWasm(guestPath));

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIAgent agent = new AIProjectClient(
    new Uri(endpoint),
    new DefaultAzureCredential())
    .AsAIAgent(new ChatClientAgentOptions()
    {
        ChatOptions = new() { ModelId = deploymentName, Instructions = "You are a helpful assistant. When the user asks something quantitative, write Python and call `execute_code` instead of guessing." },
        AIContextProviders = [codeAct],
    });

Console.WriteLine(await agent.RunAsync("What is the 20th Fibonacci number?"));
Console.WriteLine(await agent.RunAsync("Compute the mean and standard deviation of [1, 4, 9, 16, 25, 36]."));
