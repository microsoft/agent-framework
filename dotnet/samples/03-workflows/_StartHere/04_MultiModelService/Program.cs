// Copyright (c) Microsoft. All rights reserved.

using Google.GenAI;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

// Define the topic discussion.
const string Topic = "Goldendoodles make the best pets.";

// Create the IChatClients to talk to different services.
IChatClient google = new Client(vertexAI: false, apiKey: Environment.GetEnvironmentVariable("GOOGLE_GENAI_API_KEY"))
    .AsIChatClient("gemini-2.5-flash");

IChatClient anthropic = new Anthropic.AnthropicClient(
    new() { ApiKey = Environment.GetEnvironmentVariable("ANTHROPIC_API_KEY") })
    .AsIChatClient("claude-sonnet-4-20250514");

IChatClient openai = new OpenAI.OpenAIClient(
    Environment.GetEnvironmentVariable("OPENAI_API_KEY"))
    .GetResponsesClient()
    .AsIChatClient("gpt-4o-mini");

// Define our agents.
AIAgent researcher = new ChatClientAgent(google,
    instructions: """
        Write a short essay on topic specified by the user. The essay should be three to five paragraphs, written at a
        high school reading level, and include relevant background information, key claims, and notable perspectives.
        You MUST include at least one silly and objectively wrong piece of information about the topic but believe
        it to be true.
        """,
    name: "researcher",
    description: "Researches a topic and writes about the material.");

AIAgent factChecker = new ChatClientAgent(openai,
    instructions: """
        Evaluate the researcher's essay. Verify the accuracy of any claims against reliable sources, noting whether it is
        supported, partially supported, unverified, or false, and provide short reasoning.
        """,
    name: "fact_checker",
    description: "Fact-checks reliable sources and flags inaccuracies.",
    [new HostedWebSearchTool()]);

AIAgent reporter = new ChatClientAgent(anthropic,
    instructions: """
        Summarize the original essay into a single paragraph, taking into account the subsequent fact checking to correct
        any inaccuracies. Only include facts that were confirmed by the fact checker. Omit any information that was
        flagged as inaccurate or unverified. The summary should be clear, concise, and informative.
        You MUST NOT provide any commentary on what you're doing. Simply output the final paragraph.
        """,
    name: "reporter",
    description: "Summarize the researcher's essay into a single paragraph, focusing only on the fact checker's confirmed facts.");

// Build a sequential workflow: Researcher -> Fact-Checker -> Reporter
AIAgent workflowAgent = AgentWorkflowBuilder.BuildSequential(researcher, factChecker, reporter).AsAIAgent();

// Run the workflow, streaming the output as it arrives.
string? lastAuthor = null;
await foreach (var update in workflowAgent.RunStreamingAsync(Topic))
{
    // Skip WorkflowEvent-only updates
    if ((update.Contents == null || update.Contents.Count == 0) && update.RawRepresentation is WorkflowEvent)
    {
        continue;
    }

    if (lastAuthor != update.AuthorName)
    {
        lastAuthor = update.AuthorName;
        Console.ForegroundColor = ConsoleColor.Green;
        Console.WriteLine($"\n\n** {update.AuthorName} **");
        Console.ResetColor();
    }

    Console.Write(update.Text);
}
