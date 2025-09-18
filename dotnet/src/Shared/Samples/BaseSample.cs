// Copyright (c) Microsoft. All rights reserved.

using System.Reflection;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Samples;

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
    public override Encoding Encoding => Encoding.UTF8;

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
    /// Writes a user message to the console.
    /// </summary>
    /// <param name="message">The text of the message to be sent. Cannot be null or empty.</param>
    protected void WriteUserMessage(string message) =>
        this.WriteMessageOutput(new ChatMessage(ChatRole.User, message));

    /// <summary>
    /// Processes and writes the latest agent chat response to the console, including metadata and content details.
    /// </summary>
    /// <remarks>This method formats and outputs the most recent message from the provided <see
    /// cref="AgentRunResponse"/> object. It includes the message role, author name (if available), text content, and
    /// additional content such as images, function calls, and function results. Usage statistics, including token
    /// counts, are also displayed.</remarks>
    /// <param name="response">The <see cref="AgentRunResponse"/> object containing the chat messages and usage data.</param>
    /// <param name="printUsage">The flag to indicate whether to print usage information. Defaults to <see langword="true"/>.</param>
    protected void WriteResponseOutput(AgentRunResponse response, bool? printUsage = true)
    {
        if (response.Messages.Count == 0)
        {
            // If there are no messages, we can skip writing the message.
            return;
        }

        var message = response.Messages.Last();
        this.WriteMessageOutput(message);

        WriteUsage();

        void WriteUsage()
        {
            if (!(printUsage ?? true) || response.Usage is null) { return; }

            UsageDetails usageDetails = response.Usage;

            Console.WriteLine($"  [Usage] Tokens: {usageDetails.TotalTokenCount}, Input: {usageDetails.InputTokenCount}, Output: {usageDetails.OutputTokenCount}");
        }
    }

    /// <summary>
    /// Writes the given chat message to the console.
    /// </summary>
    /// <param name="message">The specified message</param>
    protected void WriteMessageOutput(ChatMessage message)
    {
        string authorExpression = message.Role == ChatRole.User ? string.Empty : FormatAuthor();
        string contentExpression = message.Text.Trim();
        const bool IsCode = false; //message.AdditionalProperties?.ContainsKey(OpenAIAssistantAgent.CodeInterpreterMetadataKey) ?? false;
        const string CodeMarker = IsCode ? "\n  [CODE]\n" : " ";
        Console.WriteLine($"\n# {message.Role}{authorExpression}:{CodeMarker}{contentExpression}");

        // Provide visibility for inner content (that isn't TextContent).
        foreach (AIContent item in message.Contents)
        {
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

        string FormatAuthor() => message.AuthorName is not null ? $" - {message.AuthorName ?? " * "}" : string.Empty;
    }

    /// <summary>
    /// Writes the streaming agent response updates to the console.
    /// </summary>
    /// <remarks>This method formats and outputs the most recent message from the provided <see
    /// cref="AgentRunResponseUpdate"/> object. It includes the message role, author name (if available), text content, and
    /// additional content such as images, function calls, and function results. Usage statistics, including token
    /// counts, are also displayed.</remarks>
    /// <param name="update">The <see cref="AgentRunResponseUpdate"/> object containing the chat messages and usage data.</param>
    protected void WriteAgentOutput(AgentRunResponseUpdate update)
    {
        if (update.Contents.Count == 0)
        {
            // If there are no contents, we can skip writing the message.
            return;
        }

        string authorExpression = update.Role == ChatRole.User ? string.Empty : FormatAuthor();
        string contentExpression = string.IsNullOrWhiteSpace(update.Text) ? string.Empty : update.Text;
        const bool IsCode = false; //message.AdditionalProperties?.ContainsKey(OpenAIAssistantAgent.CodeInterpreterMetadataKey) ?? false;
        const string CodeMarker = IsCode ? "\n  [CODE]\n" : " ";
        Console.WriteLine($"\n# {update.Role}{authorExpression}:{CodeMarker}{contentExpression}");

        // Provide visibility for inner content (that isn't TextContent).
        foreach (AIContent item in update.Contents)
        {
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
            else if (item is UsageContent usage)
            {
                Console.WriteLine("  [Usage] Tokens: {0}, Input: {1}, Output: {2}",
                usage?.Details?.TotalTokenCount ?? 0,
                usage?.Details?.InputTokenCount ?? 0,
                usage?.Details?.OutputTokenCount ?? 0);
            }
        }

        string FormatAuthor() => update.AuthorName is not null ? $" - {update.AuthorName ?? " * "}" : string.Empty;
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
    public override void Write(object? value = null)
        => this.Output.WriteLine(value ?? string.Empty);

    /// <inheritdoc/>
    public override void Write(char[]? buffer)
        => this.Output.WriteLine(new string(buffer));
}
