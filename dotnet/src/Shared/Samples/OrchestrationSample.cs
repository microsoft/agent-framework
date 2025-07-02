// Copyright (c) Microsoft. All rights reserved.

using System.Text;
using System.Text.Json;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using GenerativeAI.Microsoft;
using Microsoft.Agents;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Samples;
using OpenAI.Responses;
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
    /// This constant defines the timeout duration for result retrieval, measured in seconds.
    /// </summary>
    protected const int ResultTimeoutInSeconds = 120;

    /// <summary>
    /// This static readonly property defines the timeout duration for result retrieval.
    /// </summary>
    protected static readonly TimeSpan ResultTimeout = TimeSpan.FromSeconds(ResultTimeoutInSeconds);

    /// <summary>
    /// Creates a new <see cref="ChatClientAgent"/> instance using the specified instructions, description, name, and functions.
    /// </summary>
    /// <param name="instructions">The instructions to provide to the agent.</param>
    /// <param name="description">An optional description for the agent.</param>
    /// <param name="name">An optional name for the agent.</param>
    /// <param name="functions">A set of <see cref="AIFunction"/> instances to be used as tools by the agent.</param>
    /// <returns>A new <see cref="ChatClientAgent"/> instance configured with the provided parameters.</returns>
    protected ChatClientAgent CreateAgent(string instructions, string? description = null, string? name = null, params AIFunction[] functions)
    {
        // Get the chat client to use for the agent.
        using IChatClient chatClient = CreateChatClient();

        ChatClientAgentOptions options =
            new()
            {
                Name = name,
                Description = description,
                Instructions = instructions,
                ChatOptions = new() { Tools = functions, ToolMode = ChatToolMode.Auto }
            };

        return new ChatClientAgent(chatClient, options);
    }

    /// <summary>
    /// Creates a new Gemini based <see cref="ChatClientAgent"/> instance using the specified instructions, description, name, and functions.
    /// </summary>
    /// <param name="instructions">The instructions to provide to the agent.</param>
    /// <param name="description">An optional description for the agent.</param>
    /// <param name="name">An optional name for the agent.</param>
    /// <param name="functions">A set of <see cref="AIFunction"/> instances to be used as tools by the agent.</param>
    /// <returns>A new <see cref="ChatClientAgent"/> instance configured with the provided parameters.</returns>
    protected ChatClientAgent CreateGeminiAgent(string instructions, string? description = null, string? name = null, params AIFunction[] functions)
    {
        // Get a chat client.
#pragma warning disable CA2000 // Dispose objects before losing scope
        GenerativeAIChatClient chatClient = new(TestConfiguration.GoogleAI.ApiKey, TestConfiguration.GoogleAI.Gemini.ModelId);
#pragma warning restore CA2000 // Dispose objects before losing scope

        // Create the agent.
        return new ChatClientAgent(chatClient, new() { Name = name, Description = description, Instructions = instructions, ChatOptions = new() { Tools = functions, ToolMode = ChatToolMode.Auto } });
    }

    /// <summary>
    /// Creates a new Gemini based <see cref="ChatClientAgent"/> instance using the specified instructions, description, name, and functions.
    /// </summary>
    /// <param name="instructions">The instructions to provide to the agent.</param>
    /// <param name="description">An optional description for the agent.</param>
    /// <param name="name">An optional name for the agent.</param>
    /// <param name="stored">A value indicating whether the conversation thread should be stored in the service.</param>
    /// <param name="functions">A set of <see cref="AIFunction"/> instances to be used as tools by the agent.</param>
    /// <returns>A new <see cref="ChatClientAgent"/> instance configured with the provided parameters.</returns>
    protected ChatClientAgent CreateResponsesAgent(string instructions, string? description = null, string? name = null, bool? stored = false, params AIFunction[] functions)
    {
        // Get the chat client to use for the agent.
        using var chatClient = new OpenAIClient(TestConfiguration.OpenAI.ApiKey)
            .GetOpenAIResponseClient(TestConfiguration.OpenAI.ChatModelId)
            .AsIChatClient();

        // Define the agent
        return new(chatClient, new()
        {
            Name = name,
            Description = description,
            Instructions = instructions,
            ChatOptions = new ChatOptions
            {
                RawRepresentationFactory = (_) => new ResponseCreationOptions() { StoredOutputEnabled = stored }
            }
        });
    }

    /// <summary>
    /// Creates a new Foundry based <see cref="ChatClientAgent"/> instance using the specified instructions, description, name, and functions.
    /// </summary>
    /// <param name="instructions">The instructions to provide to the agent.</param>
    /// <param name="description">An optional description for the agent.</param>
    /// <param name="name">An optional name for the agent.</param>
    /// <param name="functions">A set of <see cref="AIFunction"/> instances to be used as tools by the agent.</param>
    /// <returns>A new <see cref="ChatClientAgent"/> instance configured with the provided parameters.</returns>
    protected async Task<ChatClientAgent> CreateFoundryAgent(string instructions, string? description = null, string? name = null, params AIFunction[] functions)
    {
        // Get a client for creating server side agents.
        PersistentAgentsClient persistentAgentsClient = new(TestConfiguration.AzureAI.Endpoint, new AzureCliCredential());

        // Create a server side agent.
        var persistentAgentResponse = await persistentAgentsClient.Administration.CreateAgentAsync(
            model: TestConfiguration.AzureAI.DeploymentName,
            name: name,
            description: description,
            instructions: instructions).ConfigureAwait(false);

        // Create a ChatClientAgent from the service call result.
        return persistentAgentsClient.GetChatClientAgent(persistentAgentResponse.Value.Id, new() { Tools = functions, ToolMode = ChatToolMode.Auto }, name, description, instructions);
    }

    /// <summary>
    /// Deletes a foundry agent with the specified identifier.
    /// </summary>
    /// <param name="agentId">The unique identifier of the agent to delete. This value cannot be null or empty.</param>
    /// <returns>A task that completes when the agent is deleted.</returns>
    protected async Task DeleteFoundryAgent(string agentId)
    {
        // Get a client for creating server side agents.
        PersistentAgentsClient persistentAgentsClient = new(TestConfiguration.AzureAI.Endpoint, new AzureCliCredential());

        // Delete the agent.
        await persistentAgentsClient.Administration.DeleteAgentAsync(agentId).ConfigureAwait(false);
    }

    /// <summary>
    /// Creates and configures a new <see cref="IChatClient"/> instance using the OpenAI client and test configuration.
    /// </summary>
    /// <returns>A configured <see cref="IChatClient"/> instance ready for use with agents.</returns>
    protected IChatClient CreateChatClient()
    {
        return new OpenAIClient(TestConfiguration.OpenAI.ApiKey)
            .GetChatClient(TestConfiguration.OpenAI.ChatModelId)
            .AsIChatClient()
            .AsBuilder()
            .UseFunctionInvocation()
            .Build();
    }

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
    /// Writes the provided chat response messages to the console or test output, including role and author information.
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
    /// Writes the streamed chat response updates to the console or test output, including role and author information.
    /// </summary>
    /// <param name="streamedResponses">An enumerable of <see cref="ChatResponseUpdate"/> objects representing streamed responses.</param>
    protected static void WriteStreamedResponse(IEnumerable<ChatResponseUpdate> streamedResponses)
    {
        string? authorName = null;
        ChatRole? authorRole = null;
        StringBuilder builder = new();
        foreach (ChatResponseUpdate response in streamedResponses)
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
        public List<ChatResponseUpdate> StreamedResponses { get; } = [];

        /// <summary>
        /// Gets the list of chat messages representing the conversation history.
        /// </summary>
        public List<ChatMessage> History { get; } = [];

        /// <summary>
        /// Callback to handle a batch of chat messages, adding them to history and writing them to output.
        /// </summary>
        /// <param name="response">The collection of <see cref="ChatMessage"/> objects to process.</param>
        /// <returns>A <see cref="ValueTask"/> representing the asynchronous operation.</returns>
        public ValueTask ResponseCallback(IEnumerable<ChatMessage> response)
        {
            this.History.AddRange(response);
            WriteResponse(response);
            return new ValueTask();
        }

        /// <summary>
        /// Callback to handle a streamed chat response update, adding it to the list and writing output if final.
        /// </summary>
        /// <param name="streamedResponse">The <see cref="ChatResponseUpdate"/> to process.</param>
        /// <param name="isFinal">Indicates whether this is the final update in the stream.</param>
        /// <returns>A <see cref="ValueTask"/> representing the asynchronous operation.</returns>
        public ValueTask StreamingResultCallback(ChatResponseUpdate streamedResponse, bool isFinal)
        {
            this.StreamedResponses.Add(streamedResponse);

            if (isFinal)
            {
                WriteStreamedResponse(this.StreamedResponses);
                this.StreamedResponses.Clear();
            }

            return new ValueTask();
        }
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="BaseSample"/> class, setting up logging, configuration, and
    /// optionally redirecting <see cref="System.Console"/> output to the test output.
    /// </summary>
    /// <remarks>This constructor initializes logging using an <see cref="XunitLogger"/> and sets up
    /// configuration from multiple sources, including a JSON file, environment variables, and user secrets.
    /// If <paramref name="redirectSystemConsoleOutput"/> is <see langword="true"/>, calls to <see cref="System.Console"/>
    /// will be redirected to the test output provided by <paramref name="output"/>.
    /// </remarks>
    /// <param name="output">The <see cref="ITestOutputHelper"/> instance used to write test output.</param>
    /// <param name="redirectSystemConsoleOutput">
    /// A value indicating whether <see cref="System.Console"/> output should be redirected to the test output. <see langword="true"/> to redirect; otherwise, <see langword="false"/>.
    /// </param>
    protected OrchestrationSample(ITestOutputHelper output, bool redirectSystemConsoleOutput = true)
        : base(output, redirectSystemConsoleOutput)
    {
    }
}
