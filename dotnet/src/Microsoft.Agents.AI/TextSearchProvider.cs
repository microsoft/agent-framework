// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
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
public sealed class TextSearchProvider : AIContextProvider<TextSearchProvider.TextSearchProviderState>
{
    private const string DefaultPluginSearchFunctionName = "Search";
    private const string DefaultPluginSearchFunctionDescription = "Allows searching for additional information to help answer the user question.";
    private const string DefaultContextPrompt = "## Additional Context\nConsider the following information from source documents when responding to the user:";
    private const string DefaultCitationsPrompt = "Include citations to the source document with document name and link if document name and link is available.";

    private readonly Func<string, CancellationToken, Task<IEnumerable<TextSearchResult>>> _searchAsync;
    private readonly ILogger<TextSearchProvider>? _logger;
    private readonly AITool[] _tools;
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
    /// <param name="options">Optional configuration options.</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="searchAsync"/> is <see langword="null"/>.</exception>
    public TextSearchProvider(
        Func<string, CancellationToken, Task<IEnumerable<TextSearchResult>>> searchAsync,
        TextSearchProviderOptions? options = null,
        ILoggerFactory? loggerFactory = null)
        : base(_ => new TextSearchProviderState(), options?.StateKey, AgentJsonUtilities.DefaultOptions, options?.SearchInputMessageFilter, options?.StorageInputMessageFilter)
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
    protected override async ValueTask<AIContext> ProvideAIContextAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        if (this._searchTime != TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke)
        {
            // Expose the search tool for on-demand invocation.
            return new AIContext
            {
                Tools = this._tools
            };
        }

        // Retrieve recent messages from the session state.
        var recentMessagesText = this.GetOrInitializeState(context.Session).RecentMessagesText
            ?? [];

        // Aggregate text from memory + current request messages.
        var sbInput = new StringBuilder();
        var requestMessagesText =
            (context.AIContext.Messages ?? [])
            .Where(x => !string.IsNullOrWhiteSpace(x?.Text)).Select(x => x.Text);
        foreach (var messageText in recentMessagesText.Concat(requestMessagesText))
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

            if (this._logger?.IsEnabled(LogLevel.Information) is true)
            {
                this._logger?.LogInformation("TextSearchProvider: Retrieved {Count} search results.", materialized.Count);
            }

            if (materialized.Count == 0)
            {
                return new AIContext();
            }

            // Format search results
            string formatted = this.FormatResults(materialized);

            if (this._logger?.IsEnabled(LogLevel.Trace) is true)
            {
                this._logger.LogTrace("TextSearchProvider: Search Results\nInput:{Input}\nOutput:{MessageText}", input, formatted);
            }

            return new AIContext
            {
                Messages = [new ChatMessage(ChatRole.User, formatted)]
            };
        }
        catch (Exception ex)
        {
            this._logger?.LogError(ex, "TextSearchProvider: Failed to search for data due to error");
            return new AIContext();
        }
    }

    /// <inheritdoc />
    protected override ValueTask StoreAIContextAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        int limit = this._recentMessageMemoryLimit;
        if (limit <= 0)
        {
            return default; // Memory disabled.
        }

        if (context.Session is null)
        {
            return default; // No session to store state in.
        }

        // Retrieve existing recent messages from the session state.
        var recentMessagesText = this.GetOrInitializeState(context.Session).RecentMessagesText
            ?? [];

        var newMessagesText = context.RequestMessages
            .Concat(context.ResponseMessages ?? [])
            .Where(m =>
                this._recentMessageRolesIncluded.Contains(m.Role) &&
                !string.IsNullOrWhiteSpace(m.Text))
            .Select(m => m.Text);

        // Combine existing messages with new messages, then take the most recent up to the limit.
        var allMessages = recentMessagesText.Concat(newMessagesText).ToList();
        var updatedMessages = allMessages.Count > limit
            ? allMessages.Skip(allMessages.Count - limit).ToList()
            : allMessages;

        // Store updated state back to the session.
        this.SaveState(
            context.Session,
            new TextSearchProviderState { RecentMessagesText = updatedMessages });

        return default;
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

        if (this._logger?.IsEnabled(LogLevel.Information) is true)
        {
            this._logger.LogInformation("TextSearchProvider: Retrieved {Count} search results.", materialized.Count);

            if (this._logger.IsEnabled(LogLevel.Trace))
            {
                this._logger.LogTrace("TextSearchProvider Input:{UserQuestion}\nOutput:{MessageText}", userQuestion, outputText);
            }
        }

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

    /// <summary>
    /// Represents the per-session state of a <see cref="TextSearchProvider"/> stored in the <see cref="AgentSession.StateBag"/>.
    /// </summary>
    public sealed class TextSearchProviderState
    {
        /// <summary>
        /// Gets or sets the list of recent message texts retained for multi-turn search context.
        /// </summary>
        public List<string>? RecentMessagesText { get; set; }
    }
}
