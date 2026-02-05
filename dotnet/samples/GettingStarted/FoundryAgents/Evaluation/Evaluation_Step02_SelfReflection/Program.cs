// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates the self-reflection pattern using Agent Framework
// to iteratively improve agent responses based on evaluation feedback.
//
// Based on: Reflexion: Language Agents with Verbal Reinforcement Learning (NeurIPS 2023)
// Reference: https://arxiv.org/abs/2303.11366
//
// NOTE: This sample demonstrates the pattern for self-reflection evaluation.
// For production implementations using built-in evaluators, consider:
// - Microsoft.Extensions.AI.Evaluation (for local evaluation)
// - Azure AI Foundry Evaluation Service (for cloud-based evaluation)
// For the most up-to-date implementation details, see:
// https://learn.microsoft.com/dotnet/ai/evaluation/libraries

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

Console.WriteLine("=" + new string('=', 79));
Console.WriteLine("SELF-REFLECTION EVALUATION PATTERN");
Console.WriteLine("=" + new string('=', 79));
Console.WriteLine();

// Initialize Azure credentials
var credential = new AzureCliCredential();

// Get a client to interact with Azure Foundry
AIProjectClient aiProjectClient = new(new Uri(endpoint), credential);

// Create the agent
AIAgent agent = (await aiProjectClient.CreateAIAgentAsync(
    name: "KnowledgeAgent",
    model: deploymentName,
    instructions: "You are a helpful assistant. Answer questions accurately based on the provided context."));

Console.WriteLine($"Created agent: {agent.Name}");
Console.WriteLine();

// Example question and context for testing
const string Question = """
    What are the main benefits of using Azure AI Foundry for building AI applications?
    """;

const string Context = """
    Azure AI Foundry is a comprehensive platform for building, deploying, and managing AI applications.
    Key benefits include:
    1. Unified development environment with support for multiple AI frameworks and models
    2. Built-in safety and security features including content filtering and red teaming tools
    3. Scalable infrastructure that handles deployment and monitoring automatically
    4. Integration with Azure services like Azure OpenAI, Cognitive Services, and Machine Learning
    5. Evaluation tools for assessing model quality, safety, and performance
    6. Support for RAG (Retrieval-Augmented Generation) patterns with vector search
    7. Enterprise-grade compliance and governance features
    """;

Console.WriteLine("Question:");
Console.WriteLine(Question);
Console.WriteLine();
Console.WriteLine("Grounding Context:");
Console.WriteLine(Context);
Console.WriteLine();

const int MaxReflections = 3;

Console.WriteLine("Self-Reflection Pattern:");
Console.WriteLine("------------------------------------------------------------");
Console.WriteLine("1. Agent generates initial response");
Console.WriteLine("2. Evaluator scores response quality (e.g., groundedness: 1-5)");
Console.WriteLine("3. If score < max, agent receives feedback");
Console.WriteLine("4. Agent reflects and generates improved response");
Console.WriteLine("5. Repeat until max score or max iterations");
Console.WriteLine();

Console.WriteLine($"Starting self-reflection loop (max {MaxReflections} iterations)...");
Console.WriteLine();

var messageHistory = new List<string> { Question };

// Simulate self-reflection iterations
for (int i = 0; i < MaxReflections; i++)
{
    Console.WriteLine($"Iteration {i + 1}/{MaxReflections}:");
    Console.WriteLine(new string('-', 40));

    // Get agent response
    AgentSession session = await agent.CreateSessionAsync();
    AgentResponse agentResponse = await agent.RunAsync(messageHistory.Last(), session);
    string responseText = agentResponse.Text;

    Console.WriteLine($"Agent response: {responseText[..Math.Min(100, responseText.Length)]}...");
    Console.WriteLine();

    // In a production implementation, you would:
    // 1. Use an evaluator (e.g., GroundednessEvaluator from Microsoft.Extensions.AI.Evaluation.Quality)
    // 2. Or call Azure AI Foundry Evaluation Service
    // 3. Get actual groundedness score (1-5 scale)

    // For demonstration, simulate evaluation
    Console.WriteLine("Evaluation (simulated):");
    Console.WriteLine("  In production: Use GroundednessEvaluator or Azure AI Evaluation");
    Console.WriteLine("  Measures: How well response is grounded in context (1-5)");
    Console.WriteLine("  Iteration {0}: Score would be calculated here", i + 1);
    Console.WriteLine();

    // Add response to conversation
    messageHistory.Add(responseText);

    // For demonstration, show the reflection prompt that would be used
    if (i < MaxReflections - 1)
    {
        const string reflectionPrompt = """
            Evaluate your response against the provided context for groundedness.
            A score of 5 means perfectly grounded (all claims supported by context).
            A score of 1 means poorly grounded (claims not in context).

            Reflect on your answer and improve it to ensure:
            1. All information comes from the provided context
            2. No information is added that isn't in the context
            3. The response directly answers the question
            4. The structure is clear and complete

            Please provide an improved response.
            """;

        messageHistory.Add(reflectionPrompt);
        Console.WriteLine("Requesting improvement with reflection prompt...");
        Console.WriteLine();
    }
}

Console.WriteLine(new string('=', 80));
Console.WriteLine("PRODUCTION IMPLEMENTATION GUIDANCE");
Console.WriteLine(new string('=', 80));
Console.WriteLine();

Console.WriteLine("For actual evaluation, use one of these approaches:");
Console.WriteLine();
Console.WriteLine("Approach 1: Microsoft.Extensions.AI.Evaluation (Local)");
Console.WriteLine("  Package: Microsoft.Extensions.AI.Evaluation.Quality");
Console.WriteLine("  Usage:");
Console.WriteLine("    var evaluator = new GroundednessEvaluator();");
Console.WriteLine("    var context = new GroundednessEvaluatorContext { GroundingContext = context };");
Console.WriteLine("    var result = await evaluator.EvaluateAsync(messages, response, config, [context]);");
Console.WriteLine();
Console.WriteLine("Approach 2: Azure AI Foundry Evaluation Service");
Console.WriteLine("  Package: Azure.AI.Projects");
Console.WriteLine("  Usage:");
Console.WriteLine("    var evalClient = aiProjectClient.GetEvaluationsClient();");
Console.WriteLine("    // Configure and run evaluation using Azure service");
Console.WriteLine();

Console.WriteLine("Key Concepts:");
Console.WriteLine("------------------------------------------------------------");
Console.WriteLine();
Console.WriteLine("Groundedness Evaluator:");
Console.WriteLine("  - Measures how well response is grounded in provided context");
Console.WriteLine("  - Returns score 1-5 (1=poor, 5=excellent)");
Console.WriteLine("  - Detects hallucinations and unsupported claims");
Console.WriteLine();
Console.WriteLine("Self-Reflection Loop:");
Console.WriteLine("  - Automatic quality improvement");
Console.WriteLine("  - No manual intervention required");
Console.WriteLine("  - Iterative refinement with feedback");
Console.WriteLine("  - Stops at perfect score or max iterations");
Console.WriteLine();
Console.WriteLine("Other Available Evaluators:");
Console.WriteLine("  - RelevanceEvaluator: Measures relevance to question");
Console.WriteLine("  - CoherenceEvaluator: Measures logical flow");
Console.WriteLine("  - FluencyEvaluator: Measures language quality");
Console.WriteLine("  - CompletenessEvaluator: Measures answer completeness");
Console.WriteLine();

Console.WriteLine("Benefits:");
Console.WriteLine("  ✓ Reduces hallucinations");
Console.WriteLine("  ✓ Ensures factual accuracy");
Console.WriteLine("  ✓ Improves RAG quality");
Console.WriteLine("  ✓ Automated quality assurance");
Console.WriteLine();

Console.WriteLine("For implementation details, see:");
Console.WriteLine("  https://learn.microsoft.com/dotnet/ai/evaluation/libraries");
Console.WriteLine("  https://arxiv.org/abs/2303.11366 (Reflexion paper)");

// Cleanup
await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
Console.WriteLine();
Console.WriteLine("Cleanup: Agent deleted.");
