// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use a ChatClientAgent with function tools that require a human in the loop for approvals.
// It shows both non-streaming and streaming agent interactions using menu-related tools.
// If the agent is hosted in a service, with a remote user, combine this sample with the Persisted Conversations sample to persist the chat history
// while the agent is waiting for user input.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Linq;
using System.Threading.Tasks;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using OpenAI;
using SampleApp;

var azureOpenAIEndpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var azureOpenAIDeploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Define the menu tools to be used by the agent.
var menuTools = new MenuTools();

// Define the options for the chat client agent.
// We mark GetMenu and GetSpecial as requiring approval before they can be invoked, while GetItemPrice can be invoked without user approval.
// IMPORTANT: A limitation of the approvals flow when using ChatClientAgent is that if more than one function needs to be executed in one run,
// and any one of them requires approval, approval will be sought for all function calls produced during that run.
var agentOptions = new ChatClientAgentOptions(
    name: "Host",
    instructions: "Answer questions about the menu",
    tools: [
        new ApprovalRequiredAIFunction(AIFunctionFactory.Create(menuTools.GetMenu)),
        new ApprovalRequiredAIFunction(AIFunctionFactory.Create(menuTools.GetSpecials)),
        AIFunctionFactory.Create(menuTools.GetItemPrice)
    ]);

// Create the chat client and agent.
AIAgent agent = new AzureOpenAIClient(
    new Uri(azureOpenAIEndpoint),
    new AzureCliCredential())
     .GetChatClient(azureOpenAIDeploymentName)
     .CreateAIAgent(agentOptions);

// Non-streaming agent interaction with function tools.
Console.WriteLine("\n--- Run with approval requiring function tools ---\n");

AgentThread thread = agent.GetNewThread();

// Respond to user input, invoking functions where appropriate.
await RunAgentAsync("What is the special soup and its price?");
await RunAgentAsync("What is the special drink?");

async Task RunAgentAsync(string input)
{
    Console.WriteLine($"\nUser: {input}");
    var response = await agent.RunAsync(input, thread);

    // Loop until all user input requests are handled.
    var userInputRequests = response.UserInputRequests.ToList();
    while (userInputRequests.Count > 0)
    {
        // Approve GetSpecials function calls, reject all others.
        List<ChatMessage> nextIterationMessages = userInputRequests?.Select((request) => request switch
        {
            FunctionApprovalRequestContent functionApprovalRequest when functionApprovalRequest.FunctionCall.Name == "GetSpecials" =>
                new ChatMessage(ChatRole.User, [functionApprovalRequest.CreateResponse(approved: true)]),

            FunctionApprovalRequestContent functionApprovalRequest =>
                new ChatMessage(ChatRole.User, [functionApprovalRequest.CreateResponse(approved: false)]),

            _ => throw new NotSupportedException($"Unsupported user input request type: {request.GetType().Name}")
        })?.ToList() ?? [];

        // Write out what the decision was for each function approval request.
        nextIterationMessages.ForEach(x => Console.WriteLine($"Approval for the {(x.Contents[0] as FunctionApprovalResponseContent)?.FunctionCall.Name} function call is set to {(x.Contents[0] as FunctionApprovalResponseContent)?.Approved}."));

        // Pass the user input responses back to the agent for further processing.
        response = await agent.RunAsync(nextIterationMessages, thread);

        userInputRequests = response.UserInputRequests.ToList();
    }

    Console.WriteLine($"\nAgent: {response}");
}

// Streaming agent interaction with function tools.
Console.WriteLine("\n--- Run with approval requiring function tools and streaming ---\n");
// Create the chat history thread to capture the agent interaction.
thread = agent.GetNewThread();

// Respond to user input, invoking functions where appropriate.
await RunAgentStreamingAsync("What is the special soup and its price?");
await RunAgentStreamingAsync("What is the special drink?");

async Task RunAgentStreamingAsync(string input)
{
    Console.WriteLine($"\nUser: {input}");
    var updates = await agent.RunStreamingAsync(input, thread).ToListAsync();

    // Loop until all user input requests are handled.
    var userInputRequests = updates.SelectMany(x => x.UserInputRequests).ToList();
    while (userInputRequests.Count > 0)
    {
        // Approve GetSpecials function calls, reject all others.
        List<ChatMessage> nextIterationMessages = userInputRequests?.Select((request) => request switch
        {
            FunctionApprovalRequestContent functionApprovalRequest when functionApprovalRequest.FunctionCall.Name == "GetSpecials" =>
                new ChatMessage(ChatRole.User, [functionApprovalRequest.CreateResponse(approved: true)]),

            FunctionApprovalRequestContent functionApprovalRequest =>
                new ChatMessage(ChatRole.User, [functionApprovalRequest.CreateResponse(approved: false)]),

            _ => throw new NotSupportedException($"Unsupported request type: {request.GetType().Name}")
        })?.ToList() ?? [];

        // Write out what the decision was for each function approval request.
        nextIterationMessages.ForEach(x => Console.WriteLine($"Approval for the {(x.Contents[0] as FunctionApprovalResponseContent)?.FunctionCall.Name} function call is set to {(x.Contents[0] as FunctionApprovalResponseContent)?.Approved}."));

        // Pass the user input responses back to the agent for further processing.
        updates = await agent.RunStreamingAsync(nextIterationMessages, thread).ToListAsync();

        userInputRequests = updates.SelectMany(x => x.UserInputRequests).ToList();
    }

    Console.WriteLine($"\nAgent: {updates.ToAgentRunResponse()}");
}

namespace SampleApp
{
    /// <summary>
    /// MenuTools class as used in the agent's function tools.
    /// </summary>
    internal sealed class MenuTools
    {
        private static readonly MenuItem[] s_menuItems = [
            new() { Category = "Soup", Name = "Clam Chowder", Price = 4.95f, IsSpecial = true },
            new() { Category = "Soup", Name = "Tomato Soup", Price = 4.95f, IsSpecial = false },
            new() { Category = "Salad", Name = "Cobb Salad", Price = 9.99f },
            new() { Category = "Salad", Name = "House Salad", Price = 4.95f },
            new() { Category = "Drink", Name = "Chai Tea", Price = 2.95f, IsSpecial = true },
            new() { Category = "Drink", Name = "Soda", Price = 1.95f },
        ];

        [Description("Get the full menu items.")]
        public MenuItem[] GetMenu()
        {
            return s_menuItems;
        }

        [Description("Get the specials from the menu.")]
        public IEnumerable<MenuItem> GetSpecials()
        {
            return s_menuItems.Where(i => i.IsSpecial);
        }

        [Description("Get the price of a menu item.")]
        public float? GetItemPrice([Description("The name of the menu item.")] string menuItem)
        {
            return s_menuItems.FirstOrDefault(i => i.Name.Equals(menuItem, StringComparison.OrdinalIgnoreCase))?.Price;
        }

        public sealed class MenuItem
        {
            public string Category { get; set; } = string.Empty;
            public string Name { get; set; } = string.Empty;
            public float Price { get; set; }
            public bool IsSpecial { get; set; }
        }
    }
}
