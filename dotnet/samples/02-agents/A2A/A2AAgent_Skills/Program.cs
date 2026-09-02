// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to expose each skill advertised by an A2A agent as a separate function tool.

using System.Text.RegularExpressions;
using A2A;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var model = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";
var a2aAgentHost = Environment.GetEnvironmentVariable("A2A_AGENT_HOST") ?? throw new InvalidOperationException("A2A_AGENT_HOST is not set.");

// Resolve the remote A2A agent and its advertised skills.
A2ACardResolver agentCardResolver = new(new Uri(a2aAgentHost));
AgentCard agentCard = await agentCardResolver.GetAgentCardAsync();
AIAgent a2aAgent = agentCard.AsAIAgent();

// Create the main agent, and provide each A2A skill as a separate function tool.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIAgent agent = new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential())
    .AsAIAgent(
        model: model,
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
