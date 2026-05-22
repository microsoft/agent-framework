// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use a CompactionProvider with a compaction pipeline
// as an AIContextProvider for an agent's in-run context management. The pipeline chains multiple
// compaction strategies from gentle to aggressive:
//   1. ToolResultCompactionStrategy - Collapses old tool-call groups into concise summaries
//   2. SummarizationCompactionStrategy - LLM-compresses older conversation spans
//   3. SlidingWindowCompactionStrategy - Keeps only the most recent N user turns
//   4. TruncationCompactionStrategy - Emergency token-budget backstop

using System.ComponentModel;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-5.4-mini";

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AzureOpenAIClient openAIClient = new(new Uri(endpoint), new DefaultAzureCredential());

// Create a chat client for the agent and a separate one for the summarization strategy.
// Using the same model for simplicity; in production, use a smaller/cheaper model for summarization.
IChatClient agentChatClient = openAIClient.GetChatClient(deploymentName).AsIChatClient();
IChatClient summarizerChatClient = openAIClient.GetChatClient(deploymentName).AsIChatClient();

// Define a tool the agent can use, so we can see tool-result compaction in action.
[Description("Look up the current price of a product by name.")]
static string LookupPrice([Description("The product name to look up.")] string productName) =>
    productName.ToUpperInvariant() switch
    {
        "LAPTOP" => "The laptop costs $999.99.",
        "KEYBOARD" => "The keyboard costs $79.99.",
        "MOUSE" => "The mouse costs $29.99.",
        _ => $"Sorry, I don't have pricing for '{productName}'."
    };

// Configure the compaction pipeline with one of each strategy, ordered least to most aggressive.
PipelineCompactionStrategy compactionPipeline =
    new(// 1. Gentle: collapse old tool-call groups into short summaries
        new ToolResultCompactionStrategy(CompactionTriggers.MessagesExceed(7)),

        // 2. Moderate: use an LLM to summarize older conversation spans into a concise message
        new SummarizationCompactionStrategy(summarizerChatClient, CompactionTriggers.TokensExceed(0x500)),

        // 3. Aggressive: keep only the last N user turns and their responses
        new SlidingWindowCompactionStrategy(CompactionTriggers.TurnsExceed(4)),

        // 4. Emergency: drop oldest groups until under the token budget
        new TruncationCompactionStrategy(CompactionTriggers.TokensExceed(0x8000)));

// Create the agent with a CompactionProvider that uses the compaction pipeline.
AIAgent agent =
    agentChatClient
        .AsBuilder()
        // Note: Adding the CompactionProvider at the builder level means it will be applied to all agents
        // built from this builder and will manage context for both agent messages and tool calls.
        .UseAIContextProviders(new CompactionProvider(compactionPipeline))
        .BuildAIAgent(
            new ChatClientAgentOptions
            {
                Name = "ShoppingAssistant",
                ChatOptions = new()
                {
                    Instructions =
                        """
                        You are a helpful, but long winded, shopping assistant.
                        Help the user look up prices and compare products.
                        When responding, Be sure to be extra descriptive and use as
                        many words as possible without sounding ridiculous.
                        """,
                    Tools = [AIFunctionFactory.Create(LookupPrice)]
                },
                // Note: AIContextProviders may be specified here instead of ChatClientBuilder.UseAIContextProviders.
                // Specifying compaction at the agent level skips compaction in the function calling loop.
                //AIContextProviders = [new CompactionProvider(compactionPipeline)]
            });

AgentSession session = await agent.CreateSessionAsync();

// Helper to print chat history size
void PrintChatHistory()
{
    if (session.TryGetInMemoryChatHistory(out var history))
    {
        Console.ForegroundColor = ConsoleColor.Cyan;
        Console.WriteLine($"\n[Messages: #{history.Count}]\n");
        Console.ResetColor();
    }
}

// Run a multi-turn conversation with tool calls to exercise the pipeline.
string[] prompts =
[
    "What's the price of a laptop?",
    "How about a keyboard?",
    "And a mouse?",
    "Which product is the cheapest?",
    "Can you compare the laptop and the keyboard for me?",
    "What was the first product I asked about?",
    "Thank you!",
];

foreach (string prompt in prompts)
{
    Console.ForegroundColor = ConsoleColor.Cyan;
    Console.Write("\n[User] ");
    Console.ResetColor();
    Console.WriteLine(prompt);
    Console.ForegroundColor = ConsoleColor.Cyan;
    Console.Write("\n[Agent] ");
    Console.ResetColor();
    Console.WriteLine(await agent.RunAsync(prompt, session));

    PrintChatHistory();
}
