// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use HyperlightCodeActProvider as a sandboxed Python
// code interpreter: the model can write and execute arbitrary Python code to
// answer quantitative questions without calling any additional tools.

using Azure.AI.OpenAI;
using Azure.Identity;
using HyperlightSandbox.Api;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hyperlight;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-5.4-mini";
var guestPath = Environment.GetEnvironmentVariable("HYPERLIGHT_PYTHON_GUEST_PATH") ?? throw new InvalidOperationException("HYPERLIGHT_PYTHON_GUEST_PATH is not set.");

using var codeAct = new HyperlightCodeActProvider(new HyperlightCodeActProviderOptions
{
    Backend = SandboxBackend.Wasm,
    ModulePath = guestPath,
});

AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new DefaultAzureCredential())
    .GetChatClient(deploymentName)
    .AsAIAgent(new ChatClientAgentOptions()
    {
        ChatOptions = new() { Instructions = "You are a helpful assistant. When the user asks something quantitative, write Python and call `execute_code` instead of guessing." },
        AIContextProviders = [codeAct],
    });

Console.WriteLine(await agent.RunAsync("What is the 20th Fibonacci number?"));
Console.WriteLine(await agent.RunAsync("Compute the mean and standard deviation of [1, 4, 9, 16, 25, 36]."));
