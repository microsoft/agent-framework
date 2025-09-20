// Copyright (c) Microsoft. All rights reserved.

using System.Text;
using System.Text.Json;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Samples;
using OpenAIClient = OpenAI.OpenAIClient;

namespace Microsoft.Shared.SampleUtilities;

/// <summary>
/// Provides a base class for orchestration samples that demonstrates agent orchestration scenarios.
/// Inherits from <see cref="BaseSample"/> and provides utility methods for creating agents, chat clients,
/// and writing responses to the console or test output.
/// </summary>
public abstract class OrchestrationSample : BaseSample
{
    /// <summary>
    /// Creates a new <see cref="ChatClientAgent"/> instance using the specified instructions, description, name, and functions.
    /// </summary>
    /// <param name="instructions">The instructions to provide to the agent.</param>
    /// <param name="description">An optional description for the agent.</param>
    /// <param name="name">An optional name for the agent.</param>
    /// <param name="functions">A set of <see cref="AIFunction"/> instances to be used as tools by the agent.</param>
    /// <returns>A new <see cref="ChatClientAgent"/> instance configured with the provided parameters.</returns>
    protected static ChatClientAgent CreateAgent(string instructions, string? description = null, string? name = null, params AIFunction[] functions) =>
        new(CreateChatClient(), new ChatClientAgentOptions()
        {
            Name = name,
            Description = description,
            Instructions = instructions,
            ChatOptions = new() { Tools = functions, ToolMode = ChatToolMode.Auto }
        });

    /// <summary>
    /// Creates and configures a new <see cref="IChatClient"/> instance using the OpenAI client and test configuration.
    /// </summary>
    /// <returns>A configured <see cref="IChatClient"/> instance ready for use with agents.</returns>
    protected static IChatClient CreateChatClient() => new OpenAIClient(TestConfiguration.OpenAI.ApiKey)
        .GetChatClient(TestConfiguration.OpenAI.ChatModelId)
        .AsIChatClient()
        .AsBuilder()
        .UseFunctionInvocation()
        .Build();

    /// <summary>
    /// Display the provided history.
    /// </summary>
    /// <param name="history">The history to display</param>
    protected void DisplayHistory(IEnumerable<ChatMessage> history)
    {
        Console.WriteLine("\n\nORCHESTRATION HISTORY");
        foreach (ChatMessage message in history)
        {
            this.WriteMessageOutput(message);
        }
    }

    /// <summary>
    /// Writes the provided messages to the console or test output, including role and author information.
    /// </summary>
    /// <param name="response">An enumerable of <see cref="ChatMessage"/> objects to write.</param>
    protected static void WriteResponse(IEnumerable<ChatMessage> response)
    {
        foreach (ChatMessage message in response)
        {
            if (!string.IsNullOrEmpty(message.Text))
            {
                System.Console.WriteLine($"\n# RESPONSE {message.Role}{(message.AuthorName is not null ? $" - {message.AuthorName}" : string.Empty)}: {message}");
            }
        }
    }

    /// <summary>
    /// Writes the streamed agent run response updates to the console or test output, including role and author information.
    /// </summary>
    /// <param name="streamedResponses">An enumerable of <see cref="AgentRunResponseUpdate"/> objects representing streamed responses.</param>
    protected static void WriteStreamedResponse(IEnumerable<AgentRunResponseUpdate> streamedResponses)
    {
        string? authorName = null;
        ChatRole? authorRole = null;
        StringBuilder builder = new();
        foreach (AgentRunResponseUpdate response in streamedResponses)
        {
            authorName ??= response.AuthorName;
            authorRole ??= response.Role;

            if (!string.IsNullOrEmpty(response.Text))
            {
                builder.Append($"({JsonSerializer.Serialize(response.Text)})");
            }
        }

        if (builder.Length > 0)
        {
            System.Console.WriteLine($"\n# STREAMED {authorRole ?? ChatRole.Assistant}{(authorName is not null ? $" - {authorName}" : string.Empty)}: {builder}\n");
        }
    }

    /// <summary>
    /// Provides monitoring and callback functionality for orchestration scenarios, including tracking streamed responses and message history.
    /// </summary>
    protected sealed class OrchestrationMonitor
    {
        /// <summary>
        /// Gets the list of streamed response updates received so far.
        /// </summary>
        public List<AgentRunResponseUpdate> StreamedResponses { get; } = [];

        /// <summary>
        /// Gets the list of chat messages representing the conversation history.
        /// </summary>
        public List<ChatMessage> History { get; } = [];

        /// <summary>
        /// Callback to handle a batch of chat messages, adding them to history and writing them to output.
        /// </summary>
        /// <param name="response">The collection of <see cref="ChatMessage"/> objects to process.</param>
        /// <returns>A <see cref="ValueTask"/> representing the asynchronous operation.</returns>
        public ValueTask ResponseCallbackAsync(IEnumerable<ChatMessage> response)
        {
            WriteStreamedResponse(this.StreamedResponses);
            this.StreamedResponses.Clear();

            this.History.AddRange(response);
            WriteResponse(response);
            return default;
        }

        /// <summary>
        /// Callback to handle a streamed agent run response update, adding it to the list and writing output if final.
        /// </summary>
        /// <param name="streamedResponse">The <see cref="AgentRunResponseUpdate"/> to process.</param>
        /// <returns>A <see cref="ValueTask"/> representing the asynchronous operation.</returns>
        public ValueTask StreamingResultCallbackAsync(AgentRunResponseUpdate streamedResponse)
        {
            this.StreamedResponses.Add(streamedResponse);
            return default;
        }
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="BaseSample"/> class, setting up logging, configuration, and
    /// optionally redirecting <see cref="Console"/> output to the test output.
    /// </summary>
    /// <remarks>This constructor initializes logging using an <see cref="XunitLogger"/> and sets up
    /// configuration from multiple sources, including a JSON file, environment variables, and user secrets.
    /// If <paramref name="redirectSystemConsoleOutput"/> is <see langword="true"/>, calls to <see cref="Console"/>
    /// will be redirected to the test output provided by <paramref name="output"/>.
    /// </remarks>
    /// <param name="output">The <see cref="ITestOutputHelper"/> instance used to write test output.</param>
    /// <param name="redirectSystemConsoleOutput">
    /// A value indicating whether <see cref="Console"/> output should be redirected to the test output. <see langword="true"/> to redirect; otherwise, <see langword="false"/>.
    /// </param>
    protected OrchestrationSample(ITestOutputHelper output, bool redirectSystemConsoleOutput = true)
        : base(output, redirectSystemConsoleOutput)
    {
    }
}
