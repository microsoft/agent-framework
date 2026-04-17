// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to wire up CodeAct manually using
// HyperlightExecuteCodeFunction rather than the AIContextProvider. Use this
// when you want a fixed tool surface for the agent's lifetime and don't need
// the per-run snapshot/registry semantics of HyperlightCodeActProvider.

using Azure.AI.OpenAI;
using Azure.Identity;
using HyperlightSandbox.Api;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hyperlight;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-5.4-mini";
var guestPath = Environment.GetEnvironmentVariable("HYPERLIGHT_PYTHON_GUEST_PATH") ?? throw new InvalidOperationException("HYPERLIGHT_PYTHON_GUEST_PATH is not set.");

AIFunction calculate = AIFunctionFactory.Create(
    (double a, double b) => a * b,
    name: "multiply",
    description: "Multiply two numbers.");

using var executeCode = new HyperlightExecuteCodeFunction(new HyperlightCodeActProviderOptions
{
    Backend = SandboxBackend.Wasm,
    ModulePath = guestPath,
    Tools = [calculate],
});

var instructions =
    "You are a helpful assistant. When math is involved, solve it by writing Python "
    + "and calling `execute_code` instead of computing values yourself.\n\n"
    + executeCode.BuildInstructions(toolsVisibleToModel: false);

AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new DefaultAzureCredential())
    .GetChatClient(deploymentName)
    .AsAIAgent(instructions: instructions, tools: [executeCode.AsAIFunction()]);

Console.WriteLine(await agent.RunAsync("What is 12.3 * 4.5? Use the multiply tool from within `execute_code`."));
