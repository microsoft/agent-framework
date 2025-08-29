// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.Agents;
using Microsoft.SemanticKernel.Agents.OpenAI;
using Microsoft.SemanticKernel.ChatCompletion;
using Microsoft.SemanticKernel.Connectors.OpenAI;
using OpenAI;

#pragma warning disable SKEXP0110 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
#pragma warning disable OPENAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

var apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY") ?? throw new InvalidOperationException("OPENAI_API_KEY is not set.");
var modelId = System.Environment.GetEnvironmentVariable("OPENAI_MODELID") ?? "o4-mini";
var userInput =
    """
    Instructions:
    - Given the React component below, change it so that nonfiction books have red
        text. 
    - Return only the code in your reply
    - Do not include any additional formatting, such as markdown code blocks
    - For formatting, use four space tabs, and do not allow any lines of code to 
        exceed 80 columns
    const books = [
        { title: 'Dune', category: 'fiction', id: 1 },
        { title: 'Frankenstein', category: 'fiction', id: 2 },
        { title: 'Moneyball', category: 'nonfiction', id: 3 },
    ];
    export default function BookList() {
        const listItems = books.map(book =>
        <li>
            {book.title}
        </li>
        );
        return (
        <ul>{listItems}</ul>
        );
    }
    """;

Console.WriteLine($"User Input: {userInput}");

await SKAgent();
await AFAgent();

async Task SKAgent()
{
    Console.WriteLine("\n=== SK Agent ===\n");

    OpenAIResponseAgent agent = new(new OpenAIClient(apiKey).GetOpenAIResponseClient(modelId))
    {
        Name = "Joker",
        Instructions = "You are good at telling jokes.",
    };

    var settings = new OpenAIPromptExecutionSettings() { MaxTokens = 1000, ReasoningEffort = OpenAI.Chat.ChatReasoningEffortLevel.Low };
    var agentOptions = new AgentInvokeOptions() { KernelArguments = new(settings) };

    Microsoft.SemanticKernel.Agents.AgentThread? thread = null;
    await foreach (var item in agent.InvokeAsync(userInput, thread, agentOptions))
    {
        foreach (var content in item.Message.Items)
        {
            if (content is ReasoningContent thinking)
            {
                Console.Write($"Thinking: \n{thinking}\n---\n");
            }
            else if (content is Microsoft.SemanticKernel.TextContent text)
            {
                Console.Write($"Assistant: {text}");
            }
        }
        Console.WriteLine(item.Message);
    }

    Console.WriteLine("---");
    var userMessage = new ChatMessageContent(AuthorRole.User, userInput);
    await foreach (var item in agent.InvokeStreamingAsync(userMessage, thread, agentOptions))
    {
        thread = item.Thread;
        foreach (var content in item.Message.Items)
        {
            if (content is StreamingReasoningContent thinking)
            {
                Console.WriteLine($"Thinking: [{thinking}]");
                continue;
            }

            if (content is StreamingTextContent text)
            {
                Console.WriteLine($"Response: [{text}]");
            }
        }
    }
}

async Task AFAgent()
{
    Console.WriteLine("\n=== AF Agent ===\n");

    var agent = new OpenAIClient(apiKey).GetOpenAIResponseClient(modelId)
        .CreateAIAgent(name: "Joker", instructions: "You are good at telling jokes.");

    var thread = agent.GetNewThread();
    var agentOptions = new ChatClientAgentRunOptions(new()
    {
        MaxOutputTokens = 1000,
        // Microsoft.Extensions.AI currently does not have an abstraction for reasoning-effort,
        // we need to break glass using the RawRepresentationFactory.
        RawRepresentationFactory = (_) => new OpenAI.Responses.ResponseCreationOptions()
        {
            ReasoningOptions = new() { ReasoningEffortLevel = OpenAI.Responses.ResponseReasoningEffortLevel.Low }
        }
    });

    var result = await agent.RunAsync(userInput, thread, agentOptions);

    string assistantThinking = string.Join("\n", result.Messages
        .SelectMany(m => m.Contents)
        .OfType<TextReasoningContent>()
        .Select(trc => trc.Text));

    var assistantText = result.Text;
    Console.WriteLine($"Thinking: \n{assistantThinking}\n---\n");
    Console.WriteLine($"Assistant: \n{assistantText}\n---\n");

    Console.WriteLine("---");
    await foreach (var update in agent.RunStreamingAsync(userInput, thread, agentOptions))
    {
        var thinkingContents = update.Contents
            .OfType<TextReasoningContent>()
            .Select(trc => trc.Text)
            .ToList();

        if (thinkingContents.Count != 0)
        {
            Console.WriteLine($"Thinking: [{string.Join("\n", thinkingContents)}]");
            continue;
        }

        Console.WriteLine($"Response: [{update.Text}]");
    }
}
