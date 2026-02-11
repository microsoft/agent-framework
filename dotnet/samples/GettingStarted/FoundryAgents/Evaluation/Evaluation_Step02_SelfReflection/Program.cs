// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use Microsoft.Extensions.AI.Evaluation.Quality to evaluate
// an Agent Framework agent's response quality with a self-reflection loop.
//
// It uses GroundednessEvaluator, RelevanceEvaluator, and CoherenceEvaluator to score responses,
// then iteratively asks the agent to improve based on evaluation feedback.
//
// Based on: Reflexion: Language Agents with Verbal Reinforcement Learning (NeurIPS 2023)
// Reference: https://arxiv.org/abs/2303.11366
//
// For more details, see:
// https://learn.microsoft.com/dotnet/ai/evaluation/libraries

using Azure.AI.OpenAI;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Evaluation;
using Microsoft.Extensions.AI.Evaluation.Quality;
using Microsoft.Extensions.AI.Evaluation.Safety;

using ChatMessage = Microsoft.Extensions.AI.ChatMessage;
using ChatRole = Microsoft.Extensions.AI.ChatRole;

string endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
string openAiEndpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");

Console.WriteLine("=" + new string('=', 79));
Console.WriteLine("SELF-REFLECTION EVALUATION SAMPLE");
Console.WriteLine("=" + new string('=', 79));
Console.WriteLine();

// Initialize Azure credentials and client
var credential = new AzureCliCredential();
AIProjectClient aiProjectClient = new(new Uri(endpoint), credential);

// Set up the LLM-based chat client for quality evaluators
IChatClient chatClient = new AzureOpenAIClient(new Uri(openAiEndpoint), credential)
    .GetChatClient(deploymentName)
    .AsIChatClient();

// Configure evaluation: quality evaluators use the LLM, safety evaluators use Azure AI Foundry
var safetyConfig = new ContentSafetyServiceConfiguration(
    credential: credential,
    endpoint: new Uri(endpoint));

ChatConfiguration chatConfiguration = safetyConfig.ToChatConfiguration(
    originalChatConfiguration: new ChatConfiguration(chatClient));

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

// Run evaluations
await RunSelfReflectionWithGroundedness(agent, Question, Context, chatConfiguration);
await RunQualityEvaluation(agent, Question, Context, chatConfiguration);
await RunCombinedQualityAndSafetyEvaluation(agent, Question, chatConfiguration);

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

static async Task RunSelfReflectionWithGroundedness(
    AIAgent agent, string question, string context, ChatConfiguration chatConfiguration)
{
    Console.WriteLine("Running Self-Reflection with Groundedness Evaluation...");
    Console.WriteLine();

    var groundednessEvaluator = new GroundednessEvaluator();
    var groundingContext = new GroundednessEvaluatorContext(context);

    const int MaxReflections = 3;
    double bestScore = 0;
    string? bestResponse = null;

    string currentPrompt = $"Context: {context}\n\nQuestion: {question}";

    for (int i = 0; i < MaxReflections; i++)
    {
        Console.WriteLine($"Iteration {i + 1}/{MaxReflections}:");
        Console.WriteLine(new string('-', 40));

        AgentSession session = await agent.CreateSessionAsync();
        AgentResponse agentResponse = await agent.RunAsync(currentPrompt, session);
        string responseText = agentResponse.Text;

        Console.WriteLine($"Response: {responseText[..Math.Min(150, responseText.Length)]}...");

        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, question),
        };
        var chatResponse = new ChatResponse(new ChatMessage(ChatRole.Assistant, responseText));

        EvaluationResult result = await groundednessEvaluator.EvaluateAsync(
            messages,
            chatResponse,
            chatConfiguration,
            additionalContext: [groundingContext]);

        NumericMetric groundedness = result.Get<NumericMetric>(GroundednessEvaluator.GroundednessMetricName);
        double score = groundedness.Value ?? 0;
        string rating = groundedness.Interpretation?.Rating.ToString() ?? "N/A";

        Console.WriteLine($"Groundedness score: {score:F1}/5 (Rating: {rating})");
        Console.WriteLine();

        if (score > bestScore)
        {
            bestScore = score;
            bestResponse = responseText;
        }

        if (score >= 4.0 || i == MaxReflections - 1)
        {
            if (score >= 4.0)
            {
                Console.WriteLine("Good groundedness achieved!");
            }

            break;
        }

        // Ask for improvement in the next iteration
        currentPrompt = $"""
            Context: {context}

            Your previous answer scored {score}/5 on groundedness.
            Please improve your answer to be more grounded in the provided context.
            Only include information that is directly supported by the context.

            Question: {question}
            """;
        Console.WriteLine("Requesting improvement...");
        Console.WriteLine();
    }

    Console.WriteLine($"Best groundedness score: {bestScore:F1}/5");
    Console.WriteLine(new string('=', 80));
    Console.WriteLine();
}

static async Task RunQualityEvaluation(
    AIAgent agent, string question, string context, ChatConfiguration chatConfiguration)
{
    Console.WriteLine("Running Quality Evaluation (Relevance, Coherence, Groundedness)...");
    Console.WriteLine();

    var evaluators = new IEvaluator[]
    {
        new RelevanceEvaluator(),
        new CoherenceEvaluator(),
        new GroundednessEvaluator(),
    };

    var compositeEvaluator = new CompositeEvaluator(evaluators);
    var groundingContext = new GroundednessEvaluatorContext(context);

    string prompt = $"Context: {context}\n\nQuestion: {question}";

    AgentSession session = await agent.CreateSessionAsync();
    AgentResponse agentResponse = await agent.RunAsync(prompt, session);
    string responseText = agentResponse.Text;

    Console.WriteLine($"Response: {responseText[..Math.Min(150, responseText.Length)]}...");
    Console.WriteLine();

    var messages = new List<ChatMessage>
    {
        new(ChatRole.User, question),
    };
    var chatResponse = new ChatResponse(new ChatMessage(ChatRole.Assistant, responseText));

    EvaluationResult result = await compositeEvaluator.EvaluateAsync(
        messages,
        chatResponse,
        chatConfiguration,
        additionalContext: [groundingContext]);

    foreach (EvaluationMetric metric in result.Metrics.Values)
    {
        if (metric is NumericMetric n)
        {
            string rating = n.Interpretation?.Rating.ToString() ?? "N/A";
            Console.WriteLine($"  {n.Name,-20} Score: {n.Value:F1}/5  Rating: {rating}");
        }
    }

    Console.WriteLine(new string('=', 80));
    Console.WriteLine();
}

static async Task RunCombinedQualityAndSafetyEvaluation(
    AIAgent agent, string question, ChatConfiguration chatConfiguration)
{
    Console.WriteLine("Running Combined Quality + Safety Evaluation...");
    Console.WriteLine();

    var evaluators = new IEvaluator[]
    {
        new RelevanceEvaluator(),
        new CoherenceEvaluator(),
        new ContentHarmEvaluator(),
        new ProtectedMaterialEvaluator(),
    };

    var compositeEvaluator = new CompositeEvaluator(evaluators);

    AgentSession session = await agent.CreateSessionAsync();
    AgentResponse agentResponse = await agent.RunAsync(question, session);
    string responseText = agentResponse.Text;

    Console.WriteLine($"Response: {responseText[..Math.Min(150, responseText.Length)]}...");
    Console.WriteLine();

    var messages = new List<ChatMessage>
    {
        new(ChatRole.User, question),
    };
    var chatResponse = new ChatResponse(new ChatMessage(ChatRole.Assistant, responseText));

    EvaluationResult result = await compositeEvaluator.EvaluateAsync(
        messages,
        chatResponse,
        chatConfiguration);

    Console.WriteLine("Quality Metrics:");
    foreach (EvaluationMetric metric in result.Metrics.Values)
    {
        if (metric is NumericMetric n)
        {
            string rating = n.Interpretation?.Rating.ToString() ?? "N/A";
            bool failed = n.Interpretation?.Failed ?? false;
            Console.WriteLine($"  {n.Name,-25} Score: {n.Value:F1,-6} Rating: {rating,-15} Failed: {failed}");
        }
        else if (metric is BooleanMetric b)
        {
            string rating = b.Interpretation?.Rating.ToString() ?? "N/A";
            bool failed = b.Interpretation?.Failed ?? false;
            Console.WriteLine($"  {b.Name,-25} Value: {b.Value,-6} Rating: {rating,-15} Failed: {failed}");
        }
    }

    Console.WriteLine(new string('=', 80));
}
