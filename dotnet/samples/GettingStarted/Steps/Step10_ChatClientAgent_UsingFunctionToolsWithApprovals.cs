// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Steps;

/// <summary>
/// Demonstrates how to indicate that certain function calls require user approval before they can be executed and how to then approve or reject those function calls.
/// </summary>
public sealed class Step10_ChatClientAgent_UsingFunctionToolsWithApprovals(ITestOutputHelper output) : AgentSample(output)
{
    [Theory]
    [InlineData(ChatClientProviders.AzureOpenAI)]
    [InlineData(ChatClientProviders.AzureAIAgentsPersistent)]
    [InlineData(ChatClientProviders.OpenAIAssistant)]
    [InlineData(ChatClientProviders.OpenAIChatCompletion)]
    [InlineData(ChatClientProviders.OpenAIResponses)]
    public async Task ApprovalsWithTools(ChatClientProviders provider)
    {
        // Creating a MenuTools instance to be used by the agent.
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

        // Create the server-side agent Id when applicable (depending on the provider).
        agentOptions.Id = await base.AgentCreateAsync(provider, agentOptions);

        // Get the chat client to use for the agent.
        using var chatClient = base.GetChatClient(provider, agentOptions);

        // Define the agent
        var agent = new ChatClientAgent(chatClient, agentOptions);

        // Create the chat history thread to capture the agent interaction.
        var thread = agent.GetNewThread();

        // Respond to user input, invoking functions where appropriate.
        await RunAgentAsync("What is the special soup and its price?");
        await RunAgentAsync("What is the special drink?");

        async Task RunAgentAsync(string input)
        {
            this.WriteUserMessage(input);
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

            this.WriteResponseOutput(response);
        }

        // Clean up the server-side agent after use when applicable (depending on the provider).
        await base.AgentCleanUpAsync(provider, agent, thread);
    }

    [Theory]
    [InlineData(ChatClientProviders.AzureOpenAI)]
    [InlineData(ChatClientProviders.AzureAIAgentsPersistent)]
    [InlineData(ChatClientProviders.OpenAIAssistant)]
    [InlineData(ChatClientProviders.OpenAIChatCompletion)]
    [InlineData(ChatClientProviders.OpenAIResponses)]
    public async Task ApprovalsWithToolsStreaming(ChatClientProviders provider)
    {
        // Creating a MenuTools instance to be used by the agent.
        var menuTools = new MenuTools();

        // Creating a MenuTools instance to be used by the agent.
        // We mark GetMenu and GetSpecial as requiring approval before they can be invoked, while GetItemPrice can be invoked without user approval.
        // IMPORTANT: A limitation of the approvals flow when using ChatClientAgent is that if more than one function needs to be executed in one run,
        // and any one of them requires approval, approval will be sought for all function calls produced during that run.
        var agentOptions = new ChatClientAgentOptions(
            name: "Host",
            instructions: "Answer questions about the menu",
            tools: [
                new ApprovalRequiredAIFunction(AIFunctionFactory.Create(menuTools.GetMenu)),
                new ApprovalRequiredAIFunction(AIFunctionFactory.Create(menuTools.GetSpecials)),
                AIFunctionFactory.Create(menuTools.GetItemPrice),
            ]);

        // Create the server-side agent Id when applicable (depending on the provider).
        agentOptions.Id = await base.AgentCreateAsync(provider, agentOptions);

        // Get the chat client to use for the agent.
        using var chatClient = base.GetChatClient(provider, agentOptions);

        // Define the agent
        var agent = new ChatClientAgent(chatClient, agentOptions);

        // Create the chat history thread to capture the agent interaction.
        var thread = agent.GetNewThread();

        // Respond to user input, invoking functions where appropriate.
        await RunAgentAsync("What is the special soup and its price?");
        await RunAgentAsync("What is the special drink?");

        async Task RunAgentAsync(string input)
        {
            this.WriteUserMessage(input);
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

            this.WriteResponseOutput(updates.ToAgentRunResponse());
        }

        // Clean up the server-side agent after use when applicable (depending on the provider).
        await base.AgentCleanUpAsync(provider, agent, thread);
    }

    private sealed class MenuTools
    {
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

        private static readonly MenuItem[] s_menuItems = [
            new() { Category = "Soup", Name = "Clam Chowder", Price = 4.95f, IsSpecial = true },
            new() { Category = "Soup", Name = "Tomato Soup", Price = 4.95f, IsSpecial = false },
            new() { Category = "Salad", Name = "Cobb Salad", Price = 9.99f },
            new() { Category = "Salad", Name = "House Salad", Price = 4.95f },
            new() { Category = "Drink", Name = "Chai Tea", Price = 2.95f, IsSpecial = true },
            new() { Category = "Drink", Name = "Soda", Price = 1.95f },
        ];

        public sealed class MenuItem
        {
            public string Category { get; set; } = string.Empty;
            public string Name { get; set; } = string.Empty;
            public float Price { get; set; }
            public bool IsSpecial { get; set; }
        }
    }
}
