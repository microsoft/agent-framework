// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to represent an A2A agent as a set of function tools, where each function tool
// corresponds to a skill of the A2A agent, and register these function tools with another AI agent so
// it can leverage the A2A agent's skills.

using System.Text.RegularExpressions;
using A2A;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
var a2aAgentHost = Environment.GetEnvironmentVariable("A2A_AGENT_HOST") ?? throw new InvalidOperationException("A2A_AGENT_HOST is not set.");

// Initialize an A2ACardResolver to get an A2A agent card.
A2ACardResolver agentCardResolver = new(new Uri(a2aAgentHost));

// Get the agent card
AgentCard agentCard = await agentCardResolver.GetAgentCardAsync();

// Create an instance of the AIAgent for an existing A2A agent specified by the agent card.
AIAgent a2aAgent = agentCard.GetAIAgent();

// Create the main agent, and provide the a2a agent skills as a function tools.
AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
    .GetChatClient(deploymentName)
    .CreateAIAgent(
        instructions: "You are a helpful assistant that helps people with travel planning.",
        tools: [.. CreateFunctionTools(a2aAgent, agentCard)]
    );

// Invoke the agent and output the text result.
Console.WriteLine(await agent.RunAsync("Plan a route from '1600 Amphitheatre Parkway, Mountain View, CA' to 'San Francisco International Airport' avoiding tolls"));

static IEnumerable<AIFunction> CreateFunctionTools(AIAgent a2aAgent, AgentCard agentCard)
{
    foreach (var skill in agentCard.Skills)
    {
        // A2A agent skills don't have schemas describing the expected shape of their inputs and outputs. 
        // Schemas can be beneficial for AI models to better understand the skill's contract, generate 
        // the skill's input accordingly and to know what to expect in the skill's output.
        // However, the A2A specification defines properties such as name, description, tags, examples, 
        // inputModes, and outputModes to provide context about the skill's purpose, capabilities, usage, 
        // and supported MIME types. These properties are added to the function tool description to help 
        // the model determine the appropriate shape of the skill's input and output.
        AIFunctionFactoryOptions options = new()
        {
            Name = FunctionNameSanitizer.Sanitize(skill.Name),
            Description = $$"""
            {
                "description": "{{skill.Description}}",
                "tags": "[{{string.Join(", ", skill.Tags ?? [])}}]",
                "examples": "[{{string.Join(", ", skill.Examples ?? [])}}]",
                "inputModes": "[{{string.Join(", ", skill.InputModes ?? [])}}]",
                "outputModes": "[{{string.Join(", ", skill.OutputModes ?? [])}}]"
            }
            """,
        };

        yield return AIFunctionFactory.Create(RunAgentAsync, options);
    }

    async Task<string> RunAgentAsync(string input, CancellationToken cancellationToken)
    {
        var response = await a2aAgent.RunAsync(input, cancellationToken: cancellationToken).ConfigureAwait(false);

        return response.Text;
    }
}

internal static partial class FunctionNameSanitizer
{
    public static string Sanitize(string name)
    {
        return InvalidNameCharsRegex().Replace(name, "_");
    }

    [GeneratedRegex("[^0-9A-Za-z]+")]
    private static partial Regex InvalidNameCharsRegex();
}
