// Copyright (c) Microsoft. All rights reserved.

// Code Interpreter Tool
// Use the hosted Code Interpreter tool for math, data analysis, and code execution.
// Shows both MEAI-based and native SDK approaches.
//
// For docs: https://learn.microsoft.com/agent-framework/agents/tools

using System.Text;
using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

string endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

AIProjectClient aiProjectClient = new(new Uri(endpoint), new AzureCliCredential());

// <code_interpreter>
AIAgent agent = await aiProjectClient.CreateAIAgentAsync(
    model: deploymentName,
    name: "CoderAgent",
    instructions: "You are a personal math tutor. When asked a math question, write and run code using the python tool to answer the question.",
    tools: [new HostedCodeInterpreterTool() { Inputs = [] }]);

AgentResponse response = await agent.RunAsync("I need to solve the equation sin(x) + x^2 = 42");
// </code_interpreter>

// <read_code_output>
CodeInterpreterToolCallContent? toolCallContent = response.Messages
    .SelectMany(m => m.Contents).OfType<CodeInterpreterToolCallContent>().FirstOrDefault();
if (toolCallContent?.Inputs is not null)
{
    DataContent? codeInput = toolCallContent.Inputs.OfType<DataContent>().FirstOrDefault();
    if (codeInput?.HasTopLevelMediaType("text") ?? false)
    {
        Console.WriteLine($"Code Input: {Encoding.UTF8.GetString(codeInput.Data.ToArray())}");
    }
}

CodeInterpreterToolResultContent? toolResultContent = response.Messages
    .SelectMany(m => m.Contents).OfType<CodeInterpreterToolResultContent>().FirstOrDefault();
if (toolResultContent?.Outputs?.OfType<TextContent>().FirstOrDefault() is { } resultOutput)
{
    Console.WriteLine($"Code Tool Result: {resultOutput.Text}");
}
// </read_code_output>

await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
