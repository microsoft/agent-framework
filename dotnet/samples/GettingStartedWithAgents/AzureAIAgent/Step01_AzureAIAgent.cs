// Copyright (c) Microsoft. All rights reserved.
using Azure.AI.Agents.Persistent;
using Microsoft.Agents;
using Microsoft.Agents.AzureAI;
using Microsoft.Extensions.AI;
using Xunit;
using Xunit.Abstractions;

namespace GettingStarted.AzureAgents;

/// <summary>
/// This example demonstrates similarity between using <see cref="AzureAIAgent"/>
/// and other agent types.
/// </summary>
public class Step01_AzureAIAgent(ITestOutputHelper output) : BaseAzureAgentTest(output)
{
    [Fact]
    public async Task UseAzureAgent()
    {
        // Define the agent
        // Instructions, Name and Description properties defined via the PromptTemplateConfig.
        PersistentAgent definition = await this.Client.Administration.CreateAgentAsync(TestConfiguration.AzureAI.ChatModelId, "MyAgent");
        AzureAIAgent agent = new(definition, this.Client);

        // Create a thread for the agent conversation.
        AgentThread thread = new AzureAIAgentThread(this.Client);

        try
        {
            await InvokeAgentAsync("Fortune favors the bold.");
        }
        finally
        {
            await thread.DeleteAsync();
            await this.Client.Administration.DeleteAgentAsync(agent.Id);
        }

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
