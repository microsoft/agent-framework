// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
#if NETFRAMEWORK
using System.Net.Http;
#endif
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.ModelContextProtocol;
using Microsoft.Extensions.DependencyInjection;

namespace Steps;

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
        var agentOptions = new ChatClientAgentOptions(
            name: "Host",
            instructions: "Answer questions about the menu",
            tools: [
                AIFunctionFactory.Create(menuTools.GetMenu),
                new ApprovalRequiredAIFunction(AIFunctionFactory.Create(menuTools.GetSpecials)),
                AIFunctionFactory.Create(menuTools.GetItemPrice),
                new HostedMcpServerTool("Tiktoken Documentation", new Uri("https://gitmcp.io/openai/tiktoken"))
                {
                    AllowedTools = ["search_tiktoken_documentation", "fetch_tiktoken_documentation"],
                    ApprovalMode = HostedMcpServerToolApprovalMode.AlwaysRequire,
                }
            ]);

        // Create the server-side agent Id when applicable (depending on the provider).
        agentOptions.Id = await base.AgentCreateAsync(provider, agentOptions);

        // Get the chat client to use for the agent.
        using var chatClient = base.GetChatClient(provider, agentOptions);

        // Modify the chat client to include MCP and built-in approvals if not already present.
        var chatBuilder = chatClient.AsBuilder();
        if (chatClient.GetService<HostedMCPChatClient>() is null)
        {
            chatBuilder.Use((IChatClient innerClient, IServiceProvider services) =>
            {
                return new HostedMCPChatClient(innerClient, new HttpClient());
            });
        }
        if (chatClient.GetService<NewFunctionInvokingChatClient>() is null)
        {
            chatBuilder.Use((IChatClient innerClient, IServiceProvider services) =>
            {
                return new NewFunctionInvokingChatClient(innerClient, null, services);
            });
        }
        using var chatClientWithMCPAndApprovals = chatBuilder.Build();

        // Define the agent
        var agent = new ChatClientAgent(chatClientWithMCPAndApprovals, agentOptions);

        // Create the chat history thread to capture the agent interaction.
        var thread = agent.GetNewThread();

        // Respond to user input, invoking functions where appropriate.
        await RunAgentAsync("What is the special soup and its price?");
        await RunAgentAsync("What is the special drink?");
        await RunAgentAsync("how does tiktoken work?");

        async Task RunAgentAsync(string input)
        {
            this.WriteUserMessage(input);
            var response = await agent.RunAsync(input, thread);
            this.WriteResponseOutput(response);

            var userInputRequests = response.UserInputRequests.ToList();

            // Loop until all user input requests are handled.
            while (userInputRequests.Count > 0)
            {
                List<ChatMessage> nextIterationMessages = userInputRequests?.Select((request) => request switch
                {
                    FunctionApprovalRequestContent functionApprovalRequest when functionApprovalRequest.FunctionCall.Name == "GetSpecials" || functionApprovalRequest.FunctionCall.Name == "add" || functionApprovalRequest.FunctionCall.Name == "search_tiktoken_documentation" =>
                        new ChatMessage(ChatRole.User, [functionApprovalRequest.CreateApproval()]),
                    FunctionApprovalRequestContent functionApprovalRequest =>
                        new ChatMessage(ChatRole.User, [functionApprovalRequest.CreateRejection()]),
                    _ => throw new NotSupportedException($"Unsupported request type: {request.GetType().Name}")
                })?.ToList() ?? [];

                nextIterationMessages.ForEach(x => Console.WriteLine($"Approval for the {(x.Contents[0] as FunctionApprovalResponseContent)?.FunctionCall.Name} function call is set to {(x.Contents[0] as FunctionApprovalResponseContent)?.Approved}."));

                response = await agent.RunAsync(nextIterationMessages, thread);
                this.WriteResponseOutput(response);
                userInputRequests = response.UserInputRequests.ToList();
            }
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

        // Define the options for the chat client agent.
        var agentOptions = new ChatClientAgentOptions(
            name: "Host",
            instructions: "Answer questions about the menu",
            tools: [
                AIFunctionFactory.Create(menuTools.GetMenu),
                new ApprovalRequiredAIFunction(AIFunctionFactory.Create(menuTools.GetSpecials)),
                AIFunctionFactory.Create(menuTools.GetItemPrice),
                new HostedMcpServerTool("Tiktoken Documentation", new Uri("https://gitmcp.io/openai/tiktoken"))
                {
                    AllowedTools = ["search_tiktoken_documentation", "fetch_tiktoken_documentation"],
                    ApprovalMode = HostedMcpServerToolApprovalMode.AlwaysRequire,
                }
            ]);

        // Create the server-side agent Id when applicable (depending on the provider).
        agentOptions.Id = await base.AgentCreateAsync(provider, agentOptions);

        // Get the chat client to use for the agent.
        using var chatClient = base.GetChatClient(provider, agentOptions);

        // Modify the chat client to include MCP and built-in approvals if not already present.
        var chatBuilder = chatClient.AsBuilder();
        if (chatClient.GetService<HostedMCPChatClient>() is null)
        {
            chatBuilder.Use((IChatClient innerClient, IServiceProvider services) =>
            {
                return new HostedMCPChatClient(innerClient, new HttpClient());
            });
        }
        if (chatClient.GetService<NewFunctionInvokingChatClient>() is null)
        {
            chatBuilder.Use((IChatClient innerClient, IServiceProvider services) =>
            {
                return new NewFunctionInvokingChatClient(innerClient, null, services);
            });
        }
        using var chatClientWithMCPAndApprovals = chatBuilder.Build();

        // Define the agent
        var agent = new ChatClientAgent(chatClientWithMCPAndApprovals, agentOptions);

        // Create the chat history thread to capture the agent interaction.
        var thread = agent.GetNewThread();

        // Respond to user input, invoking functions where appropriate.
        await RunAgentAsync("What is the special soup and its price?");
        await RunAgentAsync("What is the special drink?");
        await RunAgentAsync("how does tiktoken work?");

        async Task RunAgentAsync(string input)
        {
            this.WriteUserMessage(input);
            var updates = await agent.RunStreamingAsync(input, thread).ToListAsync();
            this.WriteResponseOutput(updates.ToAgentRunResponse());
            var userInputRequests = updates.SelectMany(x => x.UserInputRequests).ToList();

            // Loop until all user input requests are handled.
            while (userInputRequests.Count > 0)
            {
                List<ChatMessage> nextIterationMessages = userInputRequests?.Select((request) => request switch
                {
                    FunctionApprovalRequestContent functionApprovalRequest when functionApprovalRequest.FunctionCall.Name == "GetSpecials" || functionApprovalRequest.FunctionCall.Name == "add" || functionApprovalRequest.FunctionCall.Name == "search_tiktoken_documentation" =>
                        new ChatMessage(ChatRole.User, [functionApprovalRequest.CreateApproval()]),
                    FunctionApprovalRequestContent functionApprovalRequest =>
                        new ChatMessage(ChatRole.User, [functionApprovalRequest.CreateRejection()]),
                    _ => throw new NotSupportedException($"Unsupported request type: {request.GetType().Name}")
                })?.ToList() ?? [];

                nextIterationMessages.ForEach(x => Console.WriteLine($"Approval for the {(x.Contents[0] as FunctionApprovalResponseContent)?.FunctionCall.Name} function call is set to {(x.Contents[0] as FunctionApprovalResponseContent)?.Approved}."));

                updates = await agent.RunStreamingAsync(nextIterationMessages, thread).ToListAsync();
                this.WriteResponseOutput(updates.ToAgentRunResponse());
                userInputRequests = updates.SelectMany(x => x.UserInputRequests).ToList();
            }
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
