// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use background responses with ChatClientAgent and Azure OpenAI Responses for long-running operations.
// It shows polling for completion using continuation tokens, function calling during background operations,
// and persisting/restoring agent state between polling cycles.

#pragma warning disable CA1050 // Declare types in namespaces

using System.ComponentModel;
using System.Text.Json;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-5";

var stateStore = new Dictionary<string, JsonElement?>();

AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
     .GetOpenAIResponseClient(deploymentName)
     .CreateAIAgent(
        name: "SpaceNovelWriter",
        instructions: "You are a space novel writer. Always research relevant facts and generate character profiles for the main characters before writing novels." +
                      "Write complete chapters without asking for approval or feedback. Do not ask the user about tone, style, pace, or format preferences - just write the novel based on the request.",
        tools: [AIFunctionFactory.Create(ResearchSpaceFactsAsync), AIFunctionFactory.Create(GenerateCharacterProfilesAsync)]);

// Enable background responses (only supported by {Azure}OpenAI Responses at this time).
AgentRunOptions options = new() { AllowBackgroundResponses = true };

AgentThread thread = agent.GetNewThread();

// Start the initial run.
AgentRunResponse response = await agent.RunAsync("Write a very long novel about a team of astronauts exploring an uncharted galaxy.", thread, options);

// Poll for background responses until complete.
while (response.ContinuationToken is not null)
{
    PersistAgentState(thread, response.ContinuationToken);

    await Task.Delay(TimeSpan.FromSeconds(10));

    RestoreAgentState(agent, out thread, out object? continuationToken);

    options.ContinuationToken = continuationToken;
    response = await agent.RunAsync(thread, options);
}

Console.WriteLine(response.Text);

void PersistAgentState(AgentThread thread, object? continuationToken)
{
    stateStore["thread"] = thread.Serialize();
    stateStore["continuationToken"] = JsonSerializer.SerializeToElement(continuationToken, AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(ResponseContinuationToken)));
}

void RestoreAgentState(AIAgent agent, out AgentThread thread, out object? continuationToken)
{
    JsonElement serializedThread = stateStore["thread"] ?? throw new InvalidOperationException("No serialized thread found in state store.");
    JsonElement? serializedToken = stateStore["continuationToken"];

    thread = agent.DeserializeThread(serializedThread);
    continuationToken = serializedToken?.Deserialize(AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(ResponseContinuationToken)));
}

[Description("Researches relevant space facts and scientific information for writing a science fiction novel")]
async Task<string> ResearchSpaceFactsAsync(string topic)
{
    Console.WriteLine($"[ResearchSpaceFacts] Researching topic: {topic}");

    // Simulate a research operation
    await Task.Delay(TimeSpan.FromSeconds(10));

    string result = topic.ToUpperInvariant() switch
    {
        var t when t.Contains("GALAXY") => "Research findings: Galaxies contain billions of stars. Uncharted galaxies may have unique stellar formations, exotic matter, and unexplored phenomena like dark energy concentrations.",
        var t when t.Contains("SPACE") || t.Contains("TRAVEL") => "Research findings: Interstellar travel requires advanced propulsion systems. Challenges include radiation exposure, life support, and navigation through unknown space.",
        var t when t.Contains("ASTRONAUT") => "Research findings: Astronauts undergo rigorous training in zero-gravity environments, emergency protocols, spacecraft systems, and team dynamics for long-duration missions.",
        _ => $"Research findings: General space exploration facts related to {topic}. Deep space missions require advanced technology, crew resilience, and contingency planning for unknown scenarios."
    };

    Console.WriteLine("[ResearchSpaceFacts] Research complete");
    return result;
}

[Description("Generates character profiles for the main astronaut characters in the novel")]
async Task<IEnumerable<string>> GenerateCharacterProfilesAsync()
{
    Console.WriteLine("[GenerateCharacterProfiles] Generating character profiles...");

    // Simulate a character generation operation
    await Task.Delay(TimeSpan.FromSeconds(10));

    string[] profiles = [
        "Captain Elena Voss: A seasoned mission commander with 15 years of experience. Strong-willed and decisive, she struggles with the weight of responsibility for her crew. Former military pilot turned astronaut.",
            "Dr. James Chen: Chief science officer and astrophysicist. Brilliant but socially awkward, he finds solace in data and discovery. His curiosity often pushes the mission into uncharted territory.",
            "Lieutenant Maya Torres: Navigation specialist and youngest crew member. Optimistic and tech-savvy, she brings fresh perspective and innovative problem-solving to challenges.",
            "Commander Marcus Rivera: Chief engineer with expertise in spacecraft systems. Pragmatic and resourceful, he can fix almost anything with limited resources. Values crew safety above all.",
            "Dr. Amara Okafor: Medical officer and psychologist. Empathetic and observant, she helps maintain crew morale and mental health during the long journey. Expert in space medicine."
    ];

    Console.WriteLine($"[GenerateCharacterProfiles] Generated {profiles.Length} character profiles");
    return profiles;
}
