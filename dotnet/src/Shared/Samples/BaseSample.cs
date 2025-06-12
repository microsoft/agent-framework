// Copyright (c) Microsoft. All rights reserved.

using System.Reflection;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Samples;
using OpenAI;

namespace Microsoft.Shared.SampleUtilities;

/// <summary>
/// Provides a base class for test implementations that integrate with xUnit's <see cref="ITestOutputHelper"/>  and
/// logging infrastructure. This class also supports redirecting <see cref="System.Console"/> output  to the test output
/// for improved debugging and test output visibility.
/// </summary>
/// <remarks>
/// This class is designed to simplify the creation of test cases by providing access to logging and
/// configuration utilities, as well as enabling Console-friendly behavior for test samples. Derived classes can use
/// the <see cref="Output"/> property for writing test output and the <see cref="LoggerFactory"/> property for creating
/// loggers.
/// </remarks>
public abstract class BaseSample : TextWriter
{
    /// <summary>
    /// Gets the output helper used for logging test results and diagnostic messages.
    /// </summary>
    protected ITestOutputHelper Output { get; }

    /// <summary>
    /// Gets the <see cref="ILoggerFactory"/> instance used to create loggers for logging operations.
    /// </summary>
    protected ILoggerFactory LoggerFactory { get; }

    /// <summary>
    /// This property makes the samples Console friendly. Allowing them to be copied and pasted into a Console app, with minimal changes.
    /// </summary>
    public BaseSample Console => this;

    /// <inheritdoc />
    public override Encoding Encoding => System.Text.Encoding.UTF8;

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
    protected BaseSample(ITestOutputHelper output, bool redirectSystemConsoleOutput = true)
    {
        this.Output = output;
        this.LoggerFactory = new XunitLogger(output);

        IConfigurationRoot configRoot = new ConfigurationBuilder()
            .AddJsonFile("appsettings.Development.json", true)
            .AddEnvironmentVariables()
            .AddUserSecrets(Assembly.GetExecutingAssembly())
            .Build();

        TestConfiguration.Initialize(configRoot);

        // Redirect System.Console output to the test output if requested
        if (redirectSystemConsoleOutput)
        {
            System.Console.SetOut(this);
        }
    }

    /// <summary>
    /// Sends a chat message from the agent to the user in the chat system.
    /// </summary>
    /// <remarks>This method formats the provided message as a user role chat message and sends it to the chat
    /// system. Ensure the <paramref name="message"/> parameter contains meaningful content, as empty or null values may
    /// result in an error.</remarks>
    /// <param name="message">The text of the message to be sent. Cannot be null or empty.</param>
    protected void WriteAgentChatMessage(string message)
    {
        this.WriteAgentChatMessage(new ChatResponse(new ChatMessage(ChatRole.User, message)));
    }

    /// <summary>
    /// Processes and writes the latest agent chat message to the console, including metadata and content details.
    /// </summary>
    /// <remarks>This method formats and outputs the most recent message from the provided <see
    /// cref="ChatResponse"/> object. It includes the message role, author name (if available), text content, and
    /// additional content such as images, function calls, and function results. Usage statistics, including token
    /// counts, are also displayed.</remarks>
    /// <param name="chatResponse">The <see cref="ChatResponse"/> object containing the chat messages and usage data.</param>
    protected void WriteAgentChatMessage(ChatResponse chatResponse)
    {
        var message = chatResponse.Messages[^1];
        // Include ChatMessage.AuthorName in output, if present.
        string authorExpression = message.Role == ChatRole.User ? string.Empty : FormatAuthor();
        // Include TextContent (via ChatMessage.Text), if present.
        string contentExpression = string.IsNullOrWhiteSpace(chatResponse.Text) ? string.Empty : chatResponse.Text;
        bool isCode = false; //message.AdditionalProperties?.ContainsKey(OpenAIAssistantAgent.CodeInterpreterMetadataKey) ?? false;
        string codeMarker = isCode ? "\n  [CODE]\n" : " ";
        Console.WriteLine($"\n# {message.Role}{authorExpression}:{codeMarker}{contentExpression}");

        // Provide visibility for inner content (that isn't TextContent).
        foreach (AIContent item in message.Contents)
        {
            /*
            if (item is AI annotation)
            {
                if (annotation.Kind == AnnotationKind.UrlCitation)
                {
                    Console.WriteLine($"  [{item.GetType().Name}] {annotation.Label}: {annotation.ReferenceId} - {annotation.Title}");
                }
                else
                {
                    Console.WriteLine($"  [{item.GetType().Name}] {annotation.Label}: File #{annotation.ReferenceId}");
                }
            }
            else if (item is ActionContent action)
            {
                Console.WriteLine($"  [{item.GetType().Name}] {action.Text}");
            }
            else if (item is ReasoningContent reasoning)
            {
                Console.WriteLine($"  [{item.GetType().Name}] {reasoning.Text.DefaultIfEmpty("Thinking...")}");
            }
            else if (item is FileReferenceContent fileReference)
            {
                Console.WriteLine($"  [{item.GetType().Name}] File #{fileReference.FileId}");
            }
            else */

            if (item is DataContent image && image.HasTopLevelMediaType("image"))
            {
                Console.WriteLine($"  [{item.GetType().Name}] {image.Uri?.ToString() ?? image.Uri ?? $"{image.Data.Length} bytes"}");
            }
            else if (item is FunctionCallContent functionCall)
            {
                Console.WriteLine($"  [{item.GetType().Name}] {functionCall.CallId}");
            }
            else if (item is FunctionResultContent functionResult)
            {
                Console.WriteLine($"  [{item.GetType().Name}] {functionResult.CallId} - {AsJson(functionResult.Result) ?? "*"}");
            }
        }

        WriteUsage(chatResponse.Usage?.TotalTokenCount ?? 0, chatResponse.Usage?.InputTokenCount ?? 0, chatResponse.Usage?.OutputTokenCount ?? 0);

        string FormatAuthor() => message.AuthorName is not null ? $" - {message.AuthorName ?? " * "}" : string.Empty;

        void WriteUsage(long totalTokens, long inputTokens, long outputTokens)
        {
            Console.WriteLine($"  [Usage] Tokens: {totalTokens}, Input: {inputTokens}, Output: {outputTokens}");
        }
    }

    private static readonly JsonSerializerOptions s_jsonOptionsCache = new() { WriteIndented = true };

    private static string? AsJson(object? obj)
    {
        if (obj is null) { return null; }
        return JsonSerializer.Serialize(obj, s_jsonOptionsCache);
    }

    /// <inheritdoc/>
    public override void WriteLine(object? value = null)
        => this.Output.WriteLine(value ?? string.Empty);

    /// <inheritdoc/>
    public override void WriteLine(string? format, params object?[] arg)
        => this.Output.WriteLine(format ?? string.Empty, arg);

    /// <inheritdoc/>
    public override void WriteLine(string? value)
        => this.Output.WriteLine(value ?? string.Empty);

    /// <inheritdoc/>
    /// <remarks>
    /// <see cref="ITestOutputHelper"/> only supports output that ends with a newline.
    /// User this method will resolve in a call to <see cref="WriteLine(string?)"/>.
    /// </remarks>
    public override void Write(object? value = null)
        => this.Output.WriteLine(value ?? string.Empty);

    /// <inheritdoc/>
    /// <remarks>
    /// <see cref="ITestOutputHelper"/> only supports output that ends with a newline.
    /// User this method will resolve in a call to <see cref="WriteLine(string?)"/>.
    /// </remarks>
    public override void Write(char[]? buffer)
        => this.Output.WriteLine(new string(buffer));

    /// <summary>
    /// Specifies the type of chat client used for interacting with AI services.
    /// </summary>
    /// <remarks>This enumeration is used to differentiate between various AI service providers, such as
    /// OpenAI and Azure OpenAI. It allows the caller to select the appropriate client type for their
    /// application.</remarks>
    public enum ChatClientType
    {
        /// <summary>Uses OpenAI's services.</summary>
        OpenAI,

        /// <summary>Uses Azure OpenAI services.</summary>
        AzureOpenAI
    }

    /// <summary>
    /// Retrieves an instance of an <see cref="IChatClient"/> based on the specified chat client type.
    /// </summary>
    /// <param name="chatClientType">The type of chat client to retrieve. Must be one of the defined values in <see cref="ChatClientType"/>.</param>
    /// <returns>An instance of <see cref="IChatClient"/> corresponding to the specified <paramref name="chatClientType"/>.</returns>
    /// <exception cref="ArgumentOutOfRangeException">Thrown if the specified <paramref name="chatClientType"/> is not a recognized value.</exception>
    protected IChatClient GetChatClient(ChatClientType chatClientType)
    {
        return chatClientType switch
        {
            ChatClientType.OpenAI => GetOpenAIChatClient(),
            ChatClientType.AzureOpenAI => GetAzureOpenAIChatClient(),
            _ => throw new ArgumentOutOfRangeException(nameof(chatClientType), chatClientType, null)
        };
    }

    private IChatClient GetOpenAIChatClient()
    {
        return new OpenAIClient(TestConfiguration.OpenAI.ApiKey)
            .GetChatClient(TestConfiguration.OpenAI.ChatModelId)
            .AsIChatClient();
    }

    private IChatClient GetAzureOpenAIChatClient()
    {
        throw new NotImplementedException();
    }
}
