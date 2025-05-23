// Copyright (c) Microsoft. All rights reserved.
using Microsoft.Agents;
using Microsoft.Extensions.AI;
using Xunit;
using Xunit.Abstractions;

namespace GettingStarted;

/// <summary>
/// Demonstrate creation of <see cref="ChatClientAgent"/> with function calling.
/// </summary>
public class Step02_FunctionCalling(ITestOutputHelper output) : BaseAgentsTest(output)
{
    /// <summary>
    /// Demonstrate the usage of <see cref="ChatClientAgent"/> with function calling.
    /// </summary>
    [Fact]
    public async Task UseSingleChatClientAgent()
    {
        var chatClient = this.CreateChatClient();

        // Define the agent
        ChatClientAgent agent =
            new(chatClient)
            {
                Name = "Host",
                Instructions = "Answer questions about the menu.",
                // Functions = [AIFunctionFactory.Create(...)],
                // Functions = KernelAIFunctionFactory.CreateFromType<MenuPlugin>(),
            };

        // Respond to user input
        await InvokeAgentAsync("What is the special soup and its price?");
        await InvokeAgentAsync("What is the special drink and its price?");

        chatClient?.Dispose();

        // Local function to invoke agent and display the conversation messages.
        async Task InvokeAgentAsync(string input)
        {
            ChatMessage message = new(ChatRole.User, input);
            this.WriteAgentChatMessage(message);

            await foreach (AgentResponseItem<ChatMessage> response in agent.InvokeAsync(message))
            {
                this.WriteAgentChatMessage(response);
            }
        }
    }
}
