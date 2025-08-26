// Copyright (c) Microsoft. All rights reserved.

using System.Text;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.Agents;
using Microsoft.SemanticKernel.Agents.AzureAI;

#pragma warning disable SKEXP0110 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
#pragma warning disable CS8321 // Local function is declared but never used

Console.ForegroundColor = ConsoleColor.Gray;

var azureEndpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var modelId = "gpt-4o";
var userInput = "Create a python code file using the code interpreter tool with a code ready to determine the values in the Fibonacci sequence that are less then the value of 101";

Console.WriteLine($"User Input: {userInput}");

await AFAgent();
await SKAgent();

Console.ForegroundColor = ConsoleColor.Gray;

async Task SKAgent()
{
    Console.ForegroundColor = ConsoleColor.Yellow;
    Console.WriteLine("\n=== SK Agent ===\n");

    var azureAgentClient = AzureAIAgent.CreateAgentsClient(azureEndpoint, new AzureCliCredential());

    Console.Write("Creating agent in the cloud...");
    PersistentAgent definition = await azureAgentClient.Administration.CreateAgentAsync(modelId, tools: [new CodeInterpreterToolDefinition()]);
    Console.Write("Done\n");

    AzureAIAgent agent = new(definition, azureAgentClient);
    var thread = new AzureAIAgentThread(azureAgentClient);

    // Respond to user input
    Console.WriteLine("\nResponse:");
    await foreach (var content in agent.InvokeAsync(userInput, thread))
    {
        string contentExpression = string.IsNullOrWhiteSpace(content.Message.Content) ? string.Empty : content.Message.Content;
        bool isCode = content.Message.Metadata?.ContainsKey(AzureAIAgent.CodeInterpreterMetadataKey) ?? false;
        string codeMarker = isCode ? "\n  [CODE]\n" : " ";
        Console.WriteLine($"\n# {content.Message.Role}:{codeMarker}{contentExpression}");

        foreach (var item in content.Message.Items)
        {
            // Process each item in the message
#pragma warning disable SKEXP0110 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
            if (item is AnnotationContent annotation)
            {
                if (annotation.Kind != AnnotationKind.UrlCitation)
                {
                    Console.WriteLine($"  [{item.GetType().Name}] {annotation.Label}: File #{annotation.ReferenceId}");
                }
            }
            else if (item is FileReferenceContent fileReference)
            {
                Console.WriteLine($"  [{item.GetType().Name}] File #{fileReference.FileId}");
            }
        }
    }
#pragma warning restore SKEXP0110 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

    // Clean up
    await thread.DeleteAsync();
    await azureAgentClient.Administration.DeleteAgentAsync(agent.Id);
}

async Task AFAgent()
{
    Console.ForegroundColor = ConsoleColor.Green;
    Console.WriteLine("\n=== AF Agent ===\n");

    var azureAgentClient = new PersistentAgentsClient(azureEndpoint, new AzureCliCredential());

    Console.Write("Creating agent in the cloud...");
    var agent = await azureAgentClient.CreateAIAgentAsync(modelId, tools: [new CodeInterpreterToolDefinition()]);
    Console.Write("Done\n");

    var thread = agent.GetNewThread();

    Console.WriteLine("Response:");
    var result = await agent.RunAsync(userInput, thread);
    Console.WriteLine(result);

    var codeContent = GetCodeInterpreterContent(result);
    bool isCode = !string.IsNullOrEmpty(codeContent);
    string codeMarker = isCode ? "\n  [CODE]\n" : " ";
    if (!string.IsNullOrEmpty(codeContent))
    {
        Console.WriteLine($"\n# {result.Messages[0].Role}:{codeMarker}{codeContent}");
    }
    foreach (var textContent in result.Messages[0].Contents.OfType<Microsoft.Extensions.AI.TextContent>())
    {
        foreach (var annotation in textContent.Annotations ?? [])
        {
            if (annotation is CitationAnnotation citation)
            {
                if (citation.Url is null)
                {
                    Console.WriteLine($"  [{citation.GetType().Name}] {citation.Snippet}: File #{citation.FileId}");
                }

                foreach (var region in citation.AnnotatedRegions ?? [])
                {
                    if (region is TextSpanAnnotatedRegion textSpanRegion)
                    {
                        Console.WriteLine($"\n[TextSpan Region] {textSpanRegion.StartIndex}-{textSpanRegion.EndIndex}");
                    }
                }
            }
        }
    }

    // Extracts via breaking glass the code generated by code interpreter tool 
    string GetCodeInterpreterContent(AgentRunResponse agentResponse)
    {
        var chatResponse = agentResponse.RawRepresentation as ChatResponse;
        StringBuilder generatedCode = new();

        foreach (object? updateRawRepresentation in chatResponse?.RawRepresentation as IEnumerable<object?> ?? [])
        {
            if (updateRawRepresentation is RunStepDetailsUpdate update && update.CodeInterpreterInput is not null)
            {
                generatedCode.Append(update.CodeInterpreterInput);
            }
        }

        return generatedCode.ToString();
    }

    // Clean up
    await azureAgentClient.Threads.DeleteThreadAsync(thread.ConversationId);
    await azureAgentClient.Administration.DeleteAgentAsync(agent.Id);
}
