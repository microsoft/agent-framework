// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use Agent Skills with script execution via the hosted code interpreter.
// When FileAgentSkillScriptExecutor.HostedCodeInterpreter() is configured, the agent can load and execute scripts
// from skill resources using the LLM provider's built-in code interpreter.
//
// This sample includes the password-generator skill:
//   - A Python script for generating secure passwords

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using OpenAI.Responses;

// --- Configuration ---
string endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// --- Skills Provider with Script Execution ---
// Discovers skills and enables script execution via the hosted code interpreter
var skillsProvider = new FileAgentSkillsProvider(
    skillPath: Path.Combine(AppContext.BaseDirectory, "skills"),
    options: new FileAgentSkillsProviderOptions
    {
        ScriptExecutor = FileAgentSkillScriptExecutor.HostedCodeInterpreter()
    });

// --- Agent Setup ---
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIAgent agent = new AzureOpenAIClient(new Uri(endpoint), new DefaultAzureCredential())
    .GetResponsesClient(deploymentName)
    .AsAIAgent(new ChatClientAgentOptions
    {
        Name = "SkillsAgent",
        ChatOptions = new()
        {
            Instructions = "You are a helpful assistant that can generate secure passwords.",
        },
        AIContextProviders = [skillsProvider],
    });

// --- Example: Password generation with script execution ---
Console.WriteLine("Example: Generating a password with a skill script");
Console.WriteLine("---------------------------------------------------");
AgentResponse response = await agent.RunAsync("Generate a secure password for my database account.");
Console.WriteLine($"Agent: {response.Text}\n");
