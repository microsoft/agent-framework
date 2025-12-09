// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A text search context provider that performs a search over external knowledge
/// and injects the formatted results into the AI invocation context, or exposes a search tool for on-demand use.
/// This provider can be used to enable Retrieval Augmented Generation (RAG) on an agent.
/// </summary>
/// <remarks>
/// <para>
/// The provider supports two behaviors controlled via <see cref="TextSearchProviderOptions.SearchTime"/>:
/// <list type="bullet">
/// <item><description><see cref="TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke"/> – Automatically performs a search prior to every AI invocation and injects results as additional messages.</description></item>
/// <item><description><see cref="TextSearchProviderOptions.TextSearchBehavior.OnDemandFunctionCalling"/> – Exposes a function tool that the model may invoke to retrieve contextual information when needed.</description></item>
/// </list>
/// </para>
/// <para>
/// When <see cref="TextSearchProviderOptions.RecentMessageMemoryLimit"/> is greater than zero the provider will retain the most recent
/// user and assistant messages (up to the configured limit) across invocations and prepend them (in chronological order)
/// to the current request messages when forming the search input. This can improve search relevance by providing
/// multi-turn context to the retrieval layer without permanently altering the conversation history.
/// </para>
/// </remarks>
public sealed class TextSearchProvider : AIContextProvider
{
    private const string DefaultPluginSearchFunctionName = "Search";
    private const string DefaultPluginSearchFunctionDescription = "Allows searching for additional information to help answer the user question.";
    private const string DefaultContextPrompt = "## Additional Context\nConsider the following information from source documents when responding to the user:";
    private const string DefaultCitationsPrompt = "Include citations to the source document with document name and link if document name and link is available.";

    private readonly Func<string, CancellationToken, Task<IEnumerable<TextSearchResult>>> _searchAsync;
    private readonly ILogger<TextSearchProvider>? _logger;
    private readonly AITool[] _tools;
    private readonly Queue<string> _recentMessagesText;
    private readonly List<ChatRole> _recentMessageRolesIncluded;
    private readonly int _recentMessageMemoryLimit;
    private readonly TextSearchProviderOptions.TextSearchBehavior _searchTime;
    private readonly string _contextPrompt;
    private readonly string _citationsPrompt;
    private readonly Func<IList<TextSearchResult>, string>? _contextFormatter;

    /// <summary>
    /// Initializes a new instance of the <see cref="TextSearchProvider"/> class.
    /// </summary>
    /// <param name="searchAsync">Delegate that executes the search logic. Must not be <see langword="null"/>.</param>
    /// <param name="serializedState">A <see cref="JsonElement"/> representing the serialized provider state.</param>
    /// <param name="jsonSerializerOptions">Optional serializer options (unused - source generated context is used).</param>
    /// <param name="options">Optional configuration options.</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="searchAsync"/> is <see langword="null"/>.</exception>
    public TextSearchProvider(
        Func<string, CancellationToken, Task<IEnumerable<TextSearchResult>>> searchAsync,
        JsonElement serializedState,
        JsonSerializerOptions? jsonSerializerOptions = null,
        TextSearchProviderOptions? options = null,
        ILoggerFactory? loggerFactory = null)
    {
        // Validate and assign parameters
        this._searchAsync = Throw.IfNull(searchAsync);
        this._logger = loggerFactory?.CreateLogger<TextSearchProvider>();
        this._recentMessageMemoryLimit = Throw.IfLessThan(options?.RecentMessageMemoryLimit ?? 0, 0);
        this._recentMessageRolesIncluded = options?.RecentMessageRolesIncluded ?? [ChatRole.User];
        this._searchTime = options?.SearchTime ?? TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke;
        this._contextPrompt = options?.ContextPrompt ?? DefaultContextPrompt;
        this._citationsPrompt = options?.CitationsPrompt ?? DefaultCitationsPrompt;
        this._contextFormatter = options?.ContextFormatter;

        // Restore recent messages from serialized state if provided
        List<string>? restoredMessages = null;
        if (serializedState.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined)
        {
            this._recentMessagesText = new();
        }
        else
        {
            var jso = jsonSerializerOptions ?? AgentJsonUtilities.DefaultOptions;
            var state = serializedState.Deserialize(jso.GetTypeInfo(typeof(TextSearchProviderState))) as TextSearchProviderState;
            if (state?.RecentMessagesText is { Count: > 0 })
            {
                restoredMessages = state.RecentMessagesText;
            }

            // Restore recent messages respecting the limit (may truncate if limit changed afterwards).
            this._recentMessagesText = restoredMessages is null ? new() : new(restoredMessages.Take(this._recentMessageMemoryLimit));
        }

        // Create the on-demand search tool (only used if behavior is OnDemandFunctionCalling)
        this._tools =
        [
            AIFunctionFactory.Create(
                this.SearchAsync,
                name: options?.FunctionToolName ?? DefaultPluginSearchFunctionName,
                description: options?.FunctionToolDescription ?? DefaultPluginSearchFunctionDescription)
        ];
    }

    /// <inheritdoc />
    public override async ValueTask<AIContext> InvokingAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        if (this._searchTime != TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke)
        {
            // Expose the search tool for on-demand invocation.
            return new AIContext { Tools = this._tools }; // No automatic message injection.
        }

        // Aggregate text from memory + current request messages.
        var sbInput = new StringBuilder();
        var requestMessagesText = context.RequestMessages.Where(x => !string.IsNullOrWhiteSpace(x?.Text)).Select(x => x.Text);
        foreach (var messageText in this._recentMessagesText.Concat(requestMessagesText))
        {
            if (sbInput.Length > 0)
            {
                sbInput.Append('\n');
            }
            sbInput.Append(messageText);
        }

        string input = sbInput.ToString();

        try
        {
            // Search
            var results = await this._searchAsync(input, cancellationToken).ConfigureAwait(false);
            IList<TextSearchResult> materialized = results as IList<TextSearchResult> ?? results.ToList();
            this._logger?.LogInformation("TextSearchProvider: Retrieved {Count} search results.", materialized.Count);

            if (materialized.Count == 0)
            {
                return new AIContext();
            }

            // Format search results
            string formatted = this.FormatResults(materialized);

            this._logger?.LogTrace("TextSearchProvider: Search Results\nInput:{Input}\nOutput:{MessageText}", input, formatted);

            return new AIContext
            {
                Messages = [new ChatMessage(ChatRole.User, formatted) { AdditionalProperties = new AdditionalPropertiesDictionary() { ["IsTextSearchProviderOutput"] = true } }]
            };
        }
        catch (Exception ex)
        {
            this._logger?.LogError(ex, "TextSearchProvider: Failed to search for data due to error");
            return new AIContext();
        }
    }

    /// <inheritdoc />
    public override ValueTask InvokedAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        int limit = this._recentMessageMemoryLimit;
        if (limit <= 0)
        {
            return default; // Memory disabled.
        }

        if (context.InvokeException is not null)
        {
            return default; // Do not update memory on failed invocations.
        }

        var messagesText = context.RequestMessages
            .Concat(context.ResponseMessages ?? [])
            .Where(m =>
                this._recentMessageRolesIncluded.Contains(m.Role) &&
                !string.IsNullOrWhiteSpace(m.Text) &&
                // Filter out any messages that were added by this class in InvokingAsync, since we don't want
                // a feedback loop where previous search results are used to find new search results.
                (m.AdditionalProperties == null || m.AdditionalProperties.TryGetValue("IsTextSearchProviderOutput", out bool isTextSearchProviderOutput) == false || !isTextSearchProviderOutput))
            .Select(m => m.Text)
            .ToList();
        if (messagesText.Count > limit)
        {
            // If the current request/response exceeds the limit, only keep the most recent messages from it.
            messagesText = messagesText.Skip(messagesText.Count - limit).ToList();
        }

        foreach (var message in messagesText)
        {
            this._recentMessagesText.Enqueue(message);
        }

        while (this._recentMessagesText.Count > limit)
        {
            this._recentMessagesText.Dequeue();
        }

        return default;
    }

    /// <summary>
    /// Serializes the current provider state to a <see cref="JsonElement"/> containing any overridden prompts or descriptions.
    /// </summary>
    /// <param name="jsonSerializerOptions">Optional serializer options (ignored, source generated context is used).</param>
    /// <returns>A <see cref="JsonElement"/> with overridden values, or default if nothing was overridden.</returns>
    public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        // Only persist values that differ from defaults plus recent memory configuration & messages.
        TextSearchProviderState state = new();
        if (this._recentMessageMemoryLimit > 0 && this._recentMessagesText.Count > 0)
        {
            state.RecentMessagesText = this._recentMessagesText.Take(this._recentMessageMemoryLimit).ToList();
        }

        return JsonSerializer.SerializeToElement(state, AgentJsonUtilities.DefaultOptions.GetTypeInfo(typeof(TextSearchProviderState)));
    }

    /// <summary>
    /// Function callable by the AI model (when enabled) to perform an ad-hoc search.
    /// </summary>
    /// <param name="userQuestion">The query text.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>Formatted search results.</returns>
    internal async Task<string> SearchAsync(string userQuestion, CancellationToken cancellationToken = default)
    {
        var results = await this._searchAsync(userQuestion, cancellationToken).ConfigureAwait(false);
        IList<TextSearchResult> materialized = results as IList<TextSearchResult> ?? results.ToList();
        string outputText = this.FormatResults(materialized);

        this._logger?.LogInformation("TextSearchProvider: Retrieved {Count} search results.", materialized.Count);
        this._logger?.LogTrace("TextSearchProvider Input:{UserQuestion}\nOutput:{MessageText}", userQuestion, outputText);

        return outputText;
    }

    /// <summary>
    /// Formats search results into an output string for model consumption.
    /// </summary>
    /// <param name="results">The results.</param>
    /// <returns>Formatted string (may be empty).</returns>
    private string FormatResults(IList<TextSearchResult> results)
    {
        if (this._contextFormatter is not null)
        {
            return this._contextFormatter(results) ?? string.Empty;
        }

        if (results.Count == 0)
        {
            return string.Empty; // No extra context.
        }

        var sb = new StringBuilder();
        sb.AppendLine(this._contextPrompt);
        for (int i = 0; i < results.Count; i++)
        {
            var result = results[i];
            if (!string.IsNullOrWhiteSpace(result.SourceName))
            {
                sb.AppendLine($"SourceDocName: {result.SourceName}");
            }
            if (!string.IsNullOrWhiteSpace(result.SourceLink))
            {
                sb.AppendLine($"SourceDocLink: {result.SourceLink}");
            }
            sb.AppendLine($"Contents: {result.Text}");
            sb.AppendLine("----");
        }
        sb.AppendLine(this._citationsPrompt);
        sb.AppendLine();
        return sb.ToString();
    }

    /// <summary>
    /// Represents a single retrieved text search result.
    /// </summary>
    public sealed class TextSearchResult
    {
        /// <summary>
        /// Gets or sets the display name of the source document (optional).
        /// </summary>
        public string? SourceName { get; set; }

        /// <summary>
        /// Gets or sets a link/URL to the source document (optional).
        /// </summary>
        public string? SourceLink { get; set; }

        /// <summary>
        /// Gets or sets the textual content of the retrieved chunk.
        /// </summary>
        public string Text { get; set; } = string.Empty;

        /// <summary>
        /// Gets or sets the raw representation of the search result from the data source.
        /// </summary>
        /// <remarks>
        /// If a <see cref="TextSearchResult"/> is created to represent some underlying object from another object
        /// model, this property can be used to store that original object. This can be useful for debugging or
        /// for enabling the <see cref="TextSearchProviderOptions.ContextFormatter"/> to access the underlying object model if needed.
        /// </remarks>
        public object? RawRepresentation { get; set; }
    }

    internal sealed class TextSearchProviderState
    {
        public List<string>? RecentMessagesText { get; set; }
    }
}
