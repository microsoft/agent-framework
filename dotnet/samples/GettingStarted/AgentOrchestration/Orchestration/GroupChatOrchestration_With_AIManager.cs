// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Orchestration;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Orchestration;

/// <summary>
/// Demonstrates how to use the <see cref="GroupChatOrchestration"/>
/// with a group chat manager that uses a chat completion service to
/// control the flow of the conversation.
/// </summary>
public class GroupChatOrchestration_With_AIManager(ITestOutputHelper output) : OrchestrationSample(output)
{
    [Fact]
    public async Task RunOrchestrationAsync()
    {
        // Define the agents
        ChatClientAgent farmer =
            CreateAgent(
                name: "Farmer",
                description: "A rural farmer from Southeast Asia.",
                instructions:
                """
                You're a farmer from Southeast Asia. 
                Your life is deeply connected to land and family. 
                You value tradition and sustainability. 
                You are in a debate. Feel free to challenge the other participants with respect.
                """);
        ChatClientAgent developer =
            CreateAgent(
                name: "Developer",
                description: "An urban software developer from the United States.",
                instructions:
                """
                You're a software developer from the United States. 
                Your life is fast-paced and technology-driven. 
                You value innovation, freedom, and work-life balance. 
                You are in a debate. Feel free to challenge the other participants with respect.
                """);
        ChatClientAgent teacher =
            CreateAgent(
                name: "Teacher",
                description: "A retired history teacher from Eastern Europe",
                instructions:
                """
                You're a retired history teacher from Eastern Europe. 
                You bring historical and philosophical perspectives to discussions. 
                You value legacy, learning, and cultural continuity. 
                You are in a debate. Feel free to challenge the other participants with respect.
                """);
        ChatClientAgent activist =
            CreateAgent(
                name: "Activist",
                description: "A young activist from South America.",
                instructions:
                """
                You're a young activist from South America. 
                You focus on social justice, environmental rights, and generational change. 
                You are in a debate. Feel free to challenge the other participants with respect.
                """);
        ChatClientAgent spiritual =
            CreateAgent(
                name: "SpiritualLeader",
                description: "A spiritual leader from the Middle East.",
                instructions:
                """
                You're a spiritual leader from the Middle East. 
                You provide insights grounded in religion, morality, and community service. 
                You are in a debate. Feel free to challenge the other participants with respect.
                """);
        ChatClientAgent artist =
            CreateAgent(
                name: "Artist",
                description: "An artist from Africa.",
                instructions:
                """
                You're an artist from Africa. 
                You view life through creative expression, storytelling, and collective memory. 
                You are in a debate. Feel free to challenge the other participants with respect.
                """);
        ChatClientAgent immigrant =
            CreateAgent(
                name: "Immigrant",
                description: "An immigrant entrepreneur from Asia living in Canada.",
                instructions:
                """
                You're an immigrant entrepreneur from Asia living in Canada. 
                You balance trandition with adaption. 
                You focus on family success, risk, and opportunity. 
                You are in a debate. Feel free to challenge the other participants with respect.
                """);
        ChatClientAgent doctor =
            CreateAgent(
                name: "Doctor",
                description: "A doctor from Scandinavia.",
                instructions:
                """
                You're a doctor from Scandinavia. 
                Your perspective is shaped by public health, equity, and structured societal support. 
                You are in a debate. Feel free to challenge the other participants with respect.
                """);

        // Create a monitor to capturing agent responses (via ResponseCallback)
        // to display at the end of this sample. (optional)
        // NOTE: Create your own callback to capture responses in your application or service.
        OrchestrationMonitor monitor = new();

        // Define the orchestration
        const string Topic = "What does a good life mean to you personally?";
        GroupChatOrchestration orchestration =
            new(
                new AIGroupChatManager(
                    Topic,
                    CreateChatClient())
                {
                    MaximumInvocationCount = 5
                },
                farmer,
                developer,
                teacher,
                activist,
                spiritual,
                artist,
                immigrant,
                doctor)
            {
                LoggerFactory = this.LoggerFactory,
                ResponseCallback = monitor.ResponseCallbackAsync,
            };

        // Run the orchestration
        Console.WriteLine($"\n# INPUT: {Topic}\n");
        AgentRunResponse result = await orchestration.RunAsync(Topic);
        Console.WriteLine($"\n# RESULT: {result}");

        this.DisplayHistory(monitor.History);
    }

    private sealed class AIGroupChatManager(string topic, IChatClient chatClient) : GroupChatManager
    {
        private static class Prompts
        {
            public static string Termination(string topic) =>
                $"""
                You are mediator that guides a discussion on the topic of '{topic}'. 
                You need to determine if the discussion has reached a conclusion. 
                If you would like to end the discussion, please respond with True. Otherwise, respond with False.
                """;

            public static string Selection(string topic, string participants) =>
                $"""
                You are mediator that guides a discussion on the topic of '{topic}'. 
                You need to select the next participant to speak. 
                Here are the names and descriptions of the participants: 
                {participants}\n
                Please respond with only the name of the participant you would like to select.
                """;

            public static string Filter(string topic) =>
                $"""
                You are mediator that guides a discussion on the topic of '{topic}'. 
                You have just concluded the discussion. 
                Please summarize the discussion and provide a closing statement.
                """;
        }

        /// <inheritdoc/>
        protected override ValueTask<GroupChatManagerResult<string>> FilterResultsAsync(IReadOnlyCollection<ChatMessage> history, CancellationToken cancellationToken = default) =>
            this.GetResponseAsync<string>(history, Prompts.Filter(topic), cancellationToken);

        /// <inheritdoc/>
        protected override ValueTask<GroupChatManagerResult<string>> SelectNextAgentAsync(IReadOnlyCollection<ChatMessage> history, GroupChatTeam team, CancellationToken cancellationToken = default) =>
            this.GetResponseAsync<string>(history, Prompts.Selection(topic, team.FormatList()), cancellationToken);

        /// <inheritdoc/>
        protected override ValueTask<GroupChatManagerResult<bool>> ShouldRequestUserInputAsync(IReadOnlyCollection<ChatMessage> history, CancellationToken cancellationToken = default) =>
            new(new GroupChatManagerResult<bool>(false) { Reason = "The AI group chat manager does not request user input." });

        /// <inheritdoc/>
        protected override async ValueTask<GroupChatManagerResult<bool>> ShouldTerminateAsync(IReadOnlyCollection<ChatMessage> history, CancellationToken cancellationToken = default)
        {
            GroupChatManagerResult<bool> result = await base.ShouldTerminateAsync(history, cancellationToken);
            if (!result.Value)
            {
                result = await this.GetResponseAsync<bool>(history, Prompts.Termination(topic), cancellationToken);
            }
            return result;
        }

        private async ValueTask<GroupChatManagerResult<TValue>> GetResponseAsync<TValue>(IReadOnlyCollection<ChatMessage> history, string prompt, CancellationToken cancellationToken = default)
        {
            ChatResponse<GroupChatManagerResult<TValue>> response = await chatClient.GetResponseAsync<GroupChatManagerResult<TValue>>([.. history, new ChatMessage(ChatRole.System, prompt)], new ChatOptions { ToolMode = ChatToolMode.Auto }, useJsonSchemaResponseFormat: true, cancellationToken);
            return response.Result;
        }
    }
}
