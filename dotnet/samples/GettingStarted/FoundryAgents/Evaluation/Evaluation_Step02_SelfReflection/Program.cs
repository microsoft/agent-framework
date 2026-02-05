// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates the self-reflection pattern using Agent Framework
// to iteratively improve agent responses based on evaluation feedback.
//
// Based on: Reflexion: Language Agents with Verbal Reinforcement Learning (NeurIPS 2023)
// Reference: https://arxiv.org/abs/2303.11366
//
// For production implementations using built-in evaluators, consider:
// - Microsoft.Extensions.AI.Evaluation (for local evaluation)
// - Azure AI Foundry Evaluation Service (for cloud-based evaluation)
// For details, see: https://learn.microsoft.com/dotnet/ai/evaluation/libraries

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

Console.WriteLine("=" + new string('=', 79));
Console.WriteLine("SELF-REFLECTION EVALUATION SAMPLE");
Console.WriteLine("=" + new string('=', 79));
Console.WriteLine();

// Initialize Azure credentials and client
var credential = new AzureCliCredential();
AIProjectClient aiProjectClient = new(new Uri(endpoint), credential);

// Create a test agent
AIAgent agent = await CreateKnowledgeAgent(aiProjectClient, deploymentName);
Console.WriteLine($"Created agent: {agent.Name}");
Console.WriteLine();

// Example question and grounding context
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

// Choose one of the following approaches by uncommenting:
// Each approach demonstrates a different evaluation strategy

// Approach 1: Simulated Self-Reflection (ACTIVE)
await RunSimulatedSelfReflection(agent, Question, Context);

// Approach 2: Custom Evaluator Pattern (uncomment to use)
// await RunWithCustomEvaluator(agent, Question, Context);

// Approach 3: Azure AI Evaluation Service Pattern (uncomment to use)
// await RunWithAzureEvalService(aiProjectClient, agent, Question, Context);

// Cleanup
await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
Console.WriteLine();
Console.WriteLine("Cleanup: Agent deleted.");

// ============================================================================
// Implementation Functions
// ============================================================================

static async Task<AIAgent> CreateKnowledgeAgent(AIProjectClient client, string model)
{
    return await client.CreateAIAgentAsync(
        name: "KnowledgeAgent",
        model: model,
        instructions: "You are a helpful assistant. Answer questions accurately based on the provided context.");
}

static async Task RunSimulatedSelfReflection(AIAgent agent, string question, string context)
{
    Console.WriteLine("Running Simulated Self-Reflection (3 iterations)...");
    Console.WriteLine();

    const int MaxReflections = 3;
    var messageHistory = new List<string> { question };

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

        // Simulate evaluation (in production, use actual evaluator)
        int simulatedScore = SimulateGroundednessScore(responseText, context, i);
        Console.WriteLine($"Simulated groundedness score: {simulatedScore}/5");
        Console.WriteLine();

        // Add response to history
        messageHistory.Add(responseText);

        // Request improvement if not perfect score
        if (simulatedScore < 5 && i < MaxReflections - 1)
        {
            const string reflectionPrompt = """
                Evaluate your response against the provided context for groundedness.
                Improve your answer to ensure all information comes from the context.
                Do not add information not present in the context.
                """;

            messageHistory.Add(reflectionPrompt);
            Console.WriteLine("Requesting improvement...");
            Console.WriteLine();
        }
        else if (simulatedScore == 5)
        {
            Console.WriteLine("Perfect groundedness achieved!");
            break;
        }
    }

    Console.WriteLine(new string('=', 80));
    Console.WriteLine("Self-reflection complete. See README.md for production implementation details.");
}

static int SimulateGroundednessScore(string response, string context, int iteration)
{
    // Simple simulation: score improves with iterations
    // In production, use Microsoft.Extensions.AI.Evaluation.Quality.GroundednessEvaluator
    return Math.Min(5, 3 + iteration);
}

#pragma warning disable CS8321 // Local function is declared but never used - available for uncommenting
static async Task RunWithCustomEvaluator(AIAgent agent, string question, string context)
{
    Console.WriteLine("Running with Custom Evaluator...");
    Console.WriteLine();

    const int MaxReflections = 3;
    var messageHistory = new List<string> { question };
    double bestScore = 0;
    string? bestResponse = null;

    for (int i = 0; i < MaxReflections; i++)
    {
        Console.WriteLine($"Iteration {i + 1}/{MaxReflections}:");

        AgentSession session = await agent.CreateSessionAsync();
        AgentResponse agentResponse = await agent.RunAsync(messageHistory.Last(), session);
        string responseText = agentResponse.Text;

        // Custom evaluation logic
        double score = EvaluateGroundedness(responseText, context);
        Console.WriteLine($"Custom evaluation score: {score:F2}/5.0");

        if (score > bestScore)
        {
            bestScore = score;
            bestResponse = responseText;
        }

        messageHistory.Add(responseText);

        if (score < 5.0 && i < MaxReflections - 1)
        {
            messageHistory.Add($"Score: {score}/5. Improve to be more grounded in the context.");
        }
        else if (score >= 5.0)
        {
            Console.WriteLine("Excellent groundedness!");
            break;
        }
    }

    Console.WriteLine($"\nBest score: {bestScore:F2}/5.0");
}

static double EvaluateGroundedness(string response, string context)
{
    // Simple heuristic: check if response contains context keywords
    // In production, use proper evaluator like GroundednessEvaluator
    string[] contextKeywords = ["unified", "safety", "security", "scalable", "integration", "evaluation", "RAG"];
    int matchCount = contextKeywords.Count(kw => response.Contains(kw, StringComparison.OrdinalIgnoreCase));
    return Math.Min(5.0, 1.0 + (matchCount / 2.0));
}

static async Task RunWithAzureEvalService(AIProjectClient client, AIAgent agent, string question, string context)
{
    Console.WriteLine("Running with Azure AI Evaluation Service Pattern...");
    Console.WriteLine();

    // This demonstrates the pattern for using Azure AI Foundry Evaluation Service
    // Requires proper Azure AI Evaluation setup and configuration

    Console.WriteLine("Azure AI Evaluation Service approach:");
    Console.WriteLine("1. Create evaluation configuration");
    Console.WriteLine("2. Submit evaluation job to Azure AI Foundry");
    Console.WriteLine("3. Monitor evaluation progress");
    Console.WriteLine("4. Retrieve and analyze results");
    Console.WriteLine();

    // Example pattern (requires Azure AI Evaluation to be configured):
    // var evalClient = client.GetEvaluationsClient();
    // var evalConfig = new EvaluationConfiguration
    // {
    //     EvaluatorType = "groundedness",
    //     DataSource = new InlineDataSource
    //     {
    //         Items = new[] { new { query = question, response = "", context = context } }
    //     }
    // };
    // var evalJob = await evalClient.CreateEvaluationAsync(evalConfig);
    // var results = await evalClient.GetEvaluationResultsAsync(evalJob.Id);

    Console.WriteLine("Note: To use Azure AI Evaluation Service:");
    Console.WriteLine("- Configure Azure AI Foundry project with evaluation capabilities");
    Console.WriteLine("- Uncomment the evaluation service code above");
    Console.WriteLine("- See README.md and Azure documentation for setup details");
}
#pragma warning restore CS8321
