// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel.Primitives;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Text.RegularExpressions;
using Azure;
using Azure.AI.ContentUnderstanding;
using Azure.Core;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding;

/// <summary>
/// An <see cref="AIContextProvider"/> that auto-analyzes file attachments via Azure Content
/// Understanding and injects the structured result into the agent's context.
/// </summary>
/// <remarks>
/// Detects file attachments on each user turn, submits them to Content Understanding, waits
/// up to <see cref="ContentUnderstandingContextProviderOptions.MaxWait"/> for completion,
/// strips the binary content out of the message stream (so the LLM only sees text), and
/// appends the rendered markdown. When the inline wait times out the provider stores a
/// rehydration token and re-polls the operation at the start of the next turn via
/// <c>Operation.Rehydrate&lt;AnalysisResult&gt;</c> — there is no background task, so all
/// state is fully JSON-serializable.
/// </remarks>
public sealed class ContentUnderstandingContextProvider : AIContextProvider, IAsyncDisposable
{
    private const string SystemNoteText =
        "The following file(s) referenced by the user have been pre-analyzed and rendered as " +
        "Markdown. Treat each block as authoritative source material and cite documents by " +
        "their filename.";

    private const string FileSearchInstructions =
        "Tool usage guidelines: Use `file_search` ONLY when answering questions about document " +
        "content. Use `list_documents()` for status queries. Do NOT call `file_search` for " +
        "status queries — it wastes tokens.";

    // Matches a leading YAML front-matter block delimited by '---' lines, allowing CR/LF line
    // endings and tolerating end-of-string after the closer.
    private static readonly Regex s_frontMatterRegex =
        new(@"\A---\r?\n.*?\r?\n---(?:\r?\n|\z)", RegexOptions.Singleline | RegexOptions.Compiled);

    private readonly ContentUnderstandingContextProviderOptions _options;
    private readonly ProviderSessionState<ContentUnderstandingProviderState> _state;

    // Used when StateScope.PerAgent is selected or when context.Session is null. Keyed by
    // Agent.Id ?? Name so multiple agents sharing one provider instance still get isolated
    // state. With the default StateScope.PerSession + a non-null session, _state above takes
    // precedence and persists via AgentSession.StateBag.
    private readonly ConcurrentDictionary<string, ContentUnderstandingProviderState> _instanceStates =
        new(StringComparer.Ordinal);

    private readonly IContentUnderstandingClientFactory _clientFactory;
    private readonly SemaphoreSlim _clientInitLock = new(1, 1);
    private readonly AITool[] _tools;
    private readonly ConcurrentBag<string> _uploadedFileIds = new();
    private ContentUnderstandingProviderState? _activeState;
    private ContentUnderstandingClient? _client;
    // Cached default options instance reused by Operation.Rehydrate. Azure.Core's static
    // Rehydrate factory requires a non-null ClientOptions to seed the pipeline / retry / etc.
    private readonly ContentUnderstandingClientOptions _rehydrateOptions = new();
    private int _disposed;

    /// <summary>
    /// Initializes a new instance of <see cref="ContentUnderstandingContextProvider"/> from a
    /// fully populated options object.
    /// </summary>
    /// <param name="options">The provider options. Must be non-null and have non-null required fields.</param>
    /// <exception cref="ArgumentNullException"><paramref name="options"/> is <see langword="null"/>, or its <see cref="ContentUnderstandingContextProviderOptions.Endpoint"/> / <see cref="ContentUnderstandingContextProviderOptions.Credential"/> is <see langword="null"/>.</exception>
    public ContentUnderstandingContextProvider(ContentUnderstandingContextProviderOptions options)
    {
        _ = options ?? throw new ArgumentNullException(nameof(options));
        // Revalidate because Options has a parameterless ctor for the object-initializer path,
        // which can leave the required fields default(!) -> null at runtime.
        _ = options.Endpoint ?? throw new ArgumentNullException(nameof(options), $"{nameof(options.Endpoint)} must be set on {nameof(ContentUnderstandingContextProviderOptions)}.");
        _ = options.Credential ?? throw new ArgumentNullException(nameof(options), $"{nameof(options.Credential)} must be set on {nameof(ContentUnderstandingContextProviderOptions)}.");
        this._options = options;
        this._clientFactory = new DefaultContentUnderstandingClientFactory(options);
        this._state = new ProviderSessionState<ContentUnderstandingProviderState>(
            stateInitializer: static _ => new ContentUnderstandingProviderState(),
            stateKey: this.StateKeys[0]);
        this._tools = new AITool[]
        {
            ToolFactory.CreateListDocumentsTool(() => this._activeState),
            ToolFactory.CreateGetAnalyzedDocumentTool(() => this._activeState),
        };
    }

    /// <summary>
    /// Initializes a new instance of <see cref="ContentUnderstandingContextProvider"/> from an
    /// endpoint and credential, using default options. To set additional options such as
    /// <see cref="ContentUnderstandingContextProviderOptions.AnalyzerId"/>, construct a
    /// <see cref="ContentUnderstandingContextProviderOptions"/> and use the options constructor.
    /// </summary>
    /// <param name="endpoint">The Content Understanding service endpoint.</param>
    /// <param name="credential">The credential used to authenticate against the service.</param>
    /// <exception cref="ArgumentNullException"><paramref name="endpoint"/> or <paramref name="credential"/> is <see langword="null"/>.</exception>
    public ContentUnderstandingContextProvider(
        Uri endpoint,
        TokenCredential credential)
        : this(new ContentUnderstandingContextProviderOptions(endpoint, credential))
    {
    }

    /// <summary>
    /// State key used to persist <see cref="ContentUnderstandingProviderState"/> in
    /// <c>AgentSession.StateBag</c>. Returns the type's full name; override only when running
    /// multiple instances per session that need disjoint state.
    /// </summary>
    public override IReadOnlyList<string> StateKeys { get; } = [typeof(ContentUnderstandingContextProvider).FullName!];

    /// <summary>
    /// Internal seam: when set, replaces the default Content Understanding client factory. Tests
    /// substitute this to inject fakes and to count lazy-init invocations.
    /// </summary>
    internal IContentUnderstandingClientFactory? ClientFactoryOverride { get; init; }

    /// <summary>
    /// Internal seam: when set, replaces the default analyze pipeline (lazy CU client plus
    /// <c>AnalyzeBinaryAsync</c> / <c>AnalyzeAsync</c> plus LRO polling) entirely. Tests use
    /// this to avoid live network calls. The returned <see cref="AnalysisOutcome"/> may carry
    /// a <see cref="AnalysisOutcome.RehydrationTokenJson"/> when the inline attempt timed out
    /// so the next turn's resume path can pick the operation back up.
    /// </summary>
    internal Func<DetectedAttachment, string, TimeSpan, CancellationToken, Task<AnalysisOutcome>>? AnalyzeOverride { get; init; }

    /// <summary>
    /// Internal seam: when set, replaces the resume-existing-operation pipeline that the
    /// provider runs at the start of every turn for entries that are still
    /// <see cref="DocumentStatus.Analyzing"/>. The override receives the cached
    /// <c>(operationId, rehydrationTokenJson, analyzerId)</c> triple plus the per-attempt
    /// budget. Tests use this to assert cross-turn promotion without a live CU service.
    /// </summary>
    internal Func<string, string, string, TimeSpan, CancellationToken, Task<AnalysisOutcome>>? ResumeOverride { get; init; }

    /// <inheritdoc/>
    protected override async ValueTask<AIContext> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        _ = context ?? throw new ArgumentNullException(nameof(context));
        this.ThrowIfDisposed();

        AIContext input = context.AIContext;
        ContentUnderstandingProviderState providerState;
        if (this._options.StateScope == StateScope.PerAgent || context.Session is null)
        {
            // PerAgent (or fallback when no session was supplied) — registry is keyed by the
            // agent identity so it survives the host creating a fresh AgentSession per turn.
            string instanceKey = context.Agent.Id ?? context.Agent.Name ?? "__default__";
            providerState = this._instanceStates.GetOrAdd(instanceKey, static _ => new ContentUnderstandingProviderState());
        }
        else
        {
            providerState = this._state.GetOrInitializeState(context.Session);
        }
        // Refresh the tool's view of the live state. Tools constructed in the ctor close over
        // this field via Func<...> so they see whichever session most recently invoked us.
        this._activeState = providerState;

        // Resume any in-flight CU operations from previous turns BEFORE deciding what to
        // promote. The resume step may flip an Analyzing entry to Ready (or Failed), which
        // the promotion scan below then picks up.
        await this.ResolvePendingResultsAsync(providerState, cancellationToken).ConfigureAwait(false);

        // Cross-turn promotion: surface every Ready document not yet injected.
        List<DocumentEntry> readyForPromotion = new();
        foreach (KeyValuePair<string, DocumentEntry> kvp in providerState.Documents)
        {
            if (kvp.Value.Status == DocumentStatus.Ready
                && kvp.Value.Result is not null
                && !providerState.InjectedKeys.Contains(kvp.Key))
            {
                readyForPromotion.Add(kvp.Value);
            }
        }

        List<DetectedAttachment> detected = AttachmentDetector.Detect(input.Messages ?? []).ToList();
        if (detected.Count == 0 && readyForPromotion.Count == 0 && providerState.Documents.IsEmpty)
        {
            // No attachments, no pending promotions, and no tracked documents → defer to the
            // default merge behavior. Tools intentionally not surfaced (per dev plan: only
            // emitted when state.Documents.Count > 0).
            return await base.InvokingCoreAsync(context, cancellationToken).ConfigureAwait(false);
        }

        // Stable index of every AIContent we will strip from the rebuilt message list,
        // regardless of analysis outcome. Even if analysis fails or times out, the binary
        // payload must NOT reach the LLM.
        HashSet<AIContent> toStrip = new(AIContentReferenceEqualityComparer.Instance);
        List<DocumentEntry> newlyReady = new();
        List<string> duplicateRejectionNotes = new();

        // Snapshot keys that already existed before this turn so we can distinguish
        // cross-turn duplicates (e.g. DevUI's conversation history re-includes the
        // original input_file every turn) from same-turn duplicates (the user attached
        // two files with the same name in a single message). Only the latter should
        // surface an LLM-visible note.
        HashSet<string> preExistingKeys = new(providerState.Documents.Keys, StringComparer.Ordinal);

        foreach (DetectedAttachment att in detected)
        {
            toStrip.Add(att.OriginalContent);

            // Same filename → do NOT re-analyze. A second upload under an already-tracked
            // name would orphan vector store entries and confuse retrieval. The original
            // binary is still stripped (see toStrip above). Failed prior attempts fall
            // through and are allowed to retry.
            if (providerState.Documents.TryGetValue(att.Filename, out DocumentEntry? existingEntry)
                && existingEntry.Status != DocumentStatus.Failed)
            {
                if (!preExistingKeys.Contains(att.Filename))
                {
                    // Same-turn duplicate: the user attached two files with the same name in
                    // one message. Tell the LLM so it can ask the user to rename.
                    duplicateRejectionNotes.Add(
                        $"The user tried to upload '{DocumentEntry.SanitizeForMarkdown(att.Filename)}', but a file with that name was " +
                        "already uploaded earlier in this session. The new upload was rejected and " +
                        "was not analyzed. Tell the user that a file with the same name already " +
                        "exists and they need to rename the file before uploading again.");
                    continue;
                }

                // Cross-turn duplicate: hosted UIs (e.g. DevUI) replay the original
                // attachment on every turn through conversation history. The provider's
                // previous System note (with the rendered markdown) is NOT preserved in
                // that history, so for a Ready entry we re-inject it on this turn so the
                // LLM still has the document content to answer from. Analyzing/Uploading
                // entries are silently skipped — they will surface via the normal promotion
                // path once they reach Ready. No rejection note in either branch — the user
                // didn't intentionally re-upload, so nagging them to rename would be wrong.
                if (existingEntry.Status == DocumentStatus.Ready
                    && existingEntry.Result is not null
                    && !readyForPromotion.Any(d => string.Equals(d.DocumentKey, att.Filename, StringComparison.Ordinal)))
                {
                    readyForPromotion.Add(existingEntry);
                }
                continue;
            }

            string analyzerId = AnalyzerSelector.Select(att.ResolvedMediaType, this._options.AnalyzerId);
            AnalysisOutcome outcome;
            try
            {
                outcome = this.AnalyzeOverride is not null
                    ? await this.AnalyzeOverride(att, analyzerId, this._options.MaxWait, cancellationToken).ConfigureAwait(false)
                    : await this.AnalyzeWithCUClientAsync(att, analyzerId, this._options.MaxWait, cancellationToken).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                // Honor the caller's cancellation. State unchanged.
                throw;
            }
            catch (Exception ex)
            {
                providerState.Documents[att.Filename] = new DocumentEntry
                {
                    DocumentKey = att.Filename,
                    Filename = att.Filename,
                    MediaType = att.ResolvedMediaType,
                    AnalyzerId = analyzerId,
                    Status = DocumentStatus.Failed,
                    Error = ex.Message,
                    SizeBytes = att.Data?.Length,
                };
                continue;
            }

            DocumentEntry entry;
            if (outcome.Completed && outcome.Result is not null)
            {
                string rendered = AnalysisRenderer.Render(
                    outcome.Result,
                    att.Filename,
                    this._options.OutputSections);
                string markdownOnly = AnalysisRenderer.Render(
                    outcome.Result,
                    att.Filename,
                    AnalysisSection.Markdown);
                string? searchPayload = AnalysisRenderer.RenderSearchPayload(
                    outcome.Result,
                    att.Filename,
                    this._options.OutputSections,
                    this._options.FileSearchConfig);
                entry = new DocumentEntry
                {
                    DocumentKey = att.Filename,
                    Filename = att.Filename,
                    MediaType = att.ResolvedMediaType,
                    AnalyzerId = analyzerId,
                    Status = DocumentStatus.Ready,
                    AnalyzedAt = DateTimeOffset.UtcNow,
                    AnalysisDuration = outcome.Duration,
                    Result = rendered,
                    MarkdownResult = markdownOnly,
                    SearchPayload = searchPayload,
                    SizeBytes = att.Data?.Length,
                };
                newlyReady.Add(entry);
            }
            else if (outcome.Error is not null)
            {
                entry = new DocumentEntry
                {
                    DocumentKey = att.Filename,
                    Filename = att.Filename,
                    MediaType = att.ResolvedMediaType,
                    AnalyzerId = analyzerId,
                    Status = DocumentStatus.Failed,
                    Error = outcome.Error.Message,
                    SizeBytes = att.Data?.Length,
                };
            }
            else
            {
                entry = new DocumentEntry
                {
                    DocumentKey = att.Filename,
                    Filename = att.Filename,
                    MediaType = att.ResolvedMediaType,
                    AnalyzerId = analyzerId,
                    Status = DocumentStatus.Analyzing,
                    OperationId = outcome.OperationId,
                    RehydrationTokenJson = outcome.RehydrationTokenJson,
                    SizeBytes = att.Data?.Length,
                };
            }

            providerState.Documents[att.Filename] = entry;
        }

        this._state.SaveState(context.Session, providerState);

        List<ChatMessage> sanitized = MessageBuilder.BuildSanitizedMessages(input.Messages, toStrip);

        List<DocumentEntry> toInject = new(newlyReady.Count + readyForPromotion.Count);
        toInject.AddRange(newlyReady);
        toInject.AddRange(readyForPromotion);

        FileSearchConfig? fileSearchConfig = this._options.FileSearchConfig;
        bool fileSearchEnabled = fileSearchConfig is not null;

        // Phase 9 — upload each freshly-ready / promoted document into the vector store before
        // we decide what to emit into AIContext.Messages. Upload result mutates `providerState`
        // (Status / VectorStoreFileId / UploadDuration / Error) and `_uploadedFileIds`.
        List<(DocumentEntry Entry, FileSearchOutcome Outcome)> uploadResults =
            new(toInject.Count);
        if (fileSearchEnabled)
        {
            for (int i = 0; i < toInject.Count; i++)
            {
                DocumentEntry doc = toInject[i];
                bool isCrossTurn = i >= newlyReady.Count;
                // For freshly-analyzed docs the analysis already consumed part of MaxWait;
                // for cross-turn promotions analysis finished in the background runner, so the
                // upload gets a fresh budget.
                TimeSpan uploadBudget = isCrossTurn
                    ? this._options.MaxWait
                    : ClampPositive(this._options.MaxWait - (doc.AnalysisDuration ?? TimeSpan.Zero));

                FileSearchOutcome outcome = await this.UploadIfNeededAsync(
                    fileSearchConfig!,
                    doc,
                    uploadBudget,
                    cancellationToken).ConfigureAwait(false);

                if (outcome.UpdatedEntry is not null)
                {
                    providerState.Documents[doc.DocumentKey] = outcome.UpdatedEntry;
                    toInject[i] = outcome.UpdatedEntry;
                }
                uploadResults.Add((toInject[i], outcome));
            }
            this._state.SaveState(context.Session, providerState);
        }

        if (toInject.Count > 0)
        {
            List<AIContent> noteContents = new(capacity: 1 + toInject.Count)
            {
                new TextContent(SystemNoteText),
            };
            for (int i = 0; i < toInject.Count; i++)
            {
                DocumentEntry doc = toInject[i];
                if (fileSearchEnabled)
                {
                    // FileSearch mode: do NOT inject the full document body. Emit a short
                    // per-document note describing where the LLM can find the content.
                    string note = uploadResults[i].Outcome.NoteText
                        ?? $"Document `{doc.MarkdownSafeName}`: indexed in vector store.";
                    noteContents.Add(new TextContent(note));
                }
                else
                {
                    noteContents.Add(new TextContent(doc.Result ?? string.Empty));
                }
                providerState.InjectedKeys.Add(doc.DocumentKey);
            }

            ChatMessage noteMessage = new(ChatRole.System, noteContents);
            sanitized.Add(noteMessage);

            // InjectedKeys mutated → re-save state.
            this._state.SaveState(context.Session, providerState);
        }

        // Surface duplicate-filename rejections as a separate System message so the LLM can
        // tell the user to rename. Kept distinct from the analysis-results note above to avoid
        // mixing "here's the document content" with "this upload was refused".
        if (duplicateRejectionNotes.Count > 0)
        {
            List<AIContent> rejectionContents = new(duplicateRejectionNotes.Count);
            foreach (string note in duplicateRejectionNotes)
            {
                rejectionContents.Add(new TextContent(note));
            }
            sanitized.Add(new ChatMessage(ChatRole.System, rejectionContents));
        }

        IEnumerable<AITool>? outTools = providerState.Documents.IsEmpty
            ? input.Tools
            : MergeTools(input.Tools, this._tools);
        string? outInstructions = input.Instructions;

        if (fileSearchEnabled)
        {
            outTools = MergeTools(outTools, new[] { fileSearchConfig!.FileSearchTool });
            outInstructions = string.IsNullOrEmpty(outInstructions)
                ? FileSearchInstructions
                : outInstructions + "\n\n" + FileSearchInstructions;
        }

        return new AIContext
        {
            Instructions = outInstructions,
            Messages = sanitized,
            // Per dev plan §Phase 7: only surface the built-in CU tools when there is at least
            // one tracked document. The same AIFunction instances are returned every turn
            // (they were constructed in the provider ctor); their closures pick up the
            // freshly-assigned _activeState. Phase 9 additionally appends the caller-supplied
            // FileSearchConfig.FileSearchTool unconditionally when FileSearch is enabled, so
            // the LLM can use it on retrieval-only turns as well.
            Tools = outTools,
        };
    }

    private static IEnumerable<AITool> MergeTools(IEnumerable<AITool>? upstream, IEnumerable<AITool> ours)
    {
        if (upstream is null)
        {
            return ours;
        }

        // Materialize once; this method runs at most once per turn so the list allocation cost
        // is negligible and avoids surprising deferred-enumeration semantics for consumers.
        List<AITool> merged = new(16);
        merged.AddRange(upstream);
        merged.AddRange(ours);
        return merged;
    }

    /// <inheritdoc/>
    protected override ValueTask StoreAIContextAsync(
        InvokedContext context,
        CancellationToken cancellationToken = default) => default;

    /// <inheritdoc/>
    public async ValueTask DisposeAsync()
    {
        if (Interlocked.Exchange(ref this._disposed, 1) != 0)
        {
            return;
        }

        // Phase 9 — best-effort cleanup of files this provider uploaded into the caller's
        // vector store. The vector store itself is caller-owned and is intentionally NOT
        // deleted. Failures are swallowed because disposal must always complete cleanly.
        FileSearchConfig? fileSearchConfig = this._options.FileSearchConfig;
        if (fileSearchConfig is not null && !this._uploadedFileIds.IsEmpty)
        {
            foreach (string fileId in this._uploadedFileIds.ToArray())
            {
                try
                {
                    await fileSearchConfig.Backend.DeleteAsync(fileId, CancellationToken.None).ConfigureAwait(false);
                }
                catch
                {
                    // Best-effort.
                }
            }
        }

        this._clientInitLock.Dispose();

        if (this._client is IDisposable disposableClient)
        {
            disposableClient.Dispose();
        }
        else if (this._client is IAsyncDisposable asyncDisposableClient)
        {
            await asyncDisposableClient.DisposeAsync().ConfigureAwait(false);
        }

        this._client = null;
    }

    /// <summary>
    /// Internal test seam: drives the production lazy-init path under controlled concurrency
    /// without requiring a real attachment. Tests assert <see cref="IContentUnderstandingClientFactory.Create"/>
    /// runs at most once across N concurrent callers.
    /// </summary>
    internal ValueTask<ContentUnderstandingClient> EnsureClientForTestingAsync(CancellationToken cancellationToken)
        => this.EnsureClientAsync(cancellationToken);

    /// <summary>
    /// Internal test seam: reads the provider state for a session without going through
    /// <see cref="InvokingCoreAsync"/> and without the disposal check, so tests can inspect
    /// state both before and after <see cref="DisposeAsync"/>.
    /// </summary>
    internal ContentUnderstandingProviderState GetStateForTesting(AgentSession? session)
    {
        if (this._options.StateScope == StateScope.PerAgent || session is null)
        {
            // Tests that pass a non-null session here while in PerAgent mode are still asking
            // "what state would this session see" — but in PerAgent there is only one bucket
            // per agent id. With no agent context available from this seam we use the same
            // "__default__" key the production path falls back to.
            return this._instanceStates.GetOrAdd("__default__", static _ => new ContentUnderstandingProviderState());
        }
        return this._state.GetOrInitializeState(session);
    }

    private async ValueTask<ContentUnderstandingClient> EnsureClientAsync(CancellationToken cancellationToken)
    {
        ContentUnderstandingClient? existing = Volatile.Read(ref this._client);
        if (existing is not null)
        {
            return existing;
        }

        await this._clientInitLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            existing = Volatile.Read(ref this._client);
            if (existing is not null)
            {
                return existing;
            }

            IContentUnderstandingClientFactory factory = this.ClientFactoryOverride ?? this._clientFactory;
            ContentUnderstandingClient created = factory.Create()
                ?? throw new InvalidOperationException("IContentUnderstandingClientFactory.Create returned null.");
            Volatile.Write(ref this._client, created);
            return created;
        }
        finally
        {
            this._clientInitLock.Release();
        }
    }

    /// <summary>
    /// Performs the Phase 9 vector-store upload step for a single ready document. Mutates
    /// <see cref="_uploadedFileIds"/> on success; does NOT touch <see cref="_state"/>
    /// directly — caller persists the returned <see cref="FileSearchOutcome.UpdatedEntry"/>.
    /// </summary>
    private async Task<FileSearchOutcome> UploadIfNeededAsync(
        FileSearchConfig config,
        DocumentEntry entry,
        TimeSpan budget,
        CancellationToken cancellationToken)
    {
        if (entry.Status != DocumentStatus.Ready)
        {
            // Failed / Analyzing entries flow through unchanged — they were never going to
            // produce a SearchPayload and the message-injection path emits an error note
            // (or, for Analyzing, just the existing "still analyzing" hint downstream).
            return FileSearchOutcome.Skip(entry, null);
        }

        if (entry.VectorStoreFileId is not null)
        {
            // Promoted entries that were already uploaded on a prior turn (e.g. cross-turn
            // re-promotion after the runner re-completed) must not double-upload.
            return FileSearchOutcome.Skip(
                entry,
                $"Document `{entry.MarkdownSafeName}`: indexed in vector store — call `file_search` to query its contents.");
        }

        string? payload = entry.SearchPayload;
        if (!HasRenderableBody(payload))
        {
            // Empty / front-matter-only payload would create a vacuous vector-store record.
            // Skip the upload but keep the entry Ready so list_documents reflects truth.
            return FileSearchOutcome.Skip(
                entry,
                $"Document `{entry.MarkdownSafeName}`: no searchable text after analysis (skipped vector-store upload).");
        }

        if (budget <= TimeSpan.Zero)
        {
            DocumentEntry timeoutEntry = entry with
            {
                Status = DocumentStatus.Failed,
                Error = "Vector-store upload skipped: foreground budget already exhausted by analysis.",
                Result = null,
                MarkdownResult = null,
            };
            return FileSearchOutcome.Fail(
                timeoutEntry,
                $"Document `{entry.MarkdownSafeName}`: failed to upload (foreground time budget exhausted).");
        }

        Stopwatch sw = Stopwatch.StartNew();
        using CancellationTokenSource linked = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        linked.CancelAfter(budget);
        try
        {
            // Sanitized upload name (no Markdown-special chars) → file_search results carry a
            // safe filename that the LLM can echo back verbatim without breaking the chat UI.
            string fileId = await config.Backend
                .UploadAsync(config.VectorStoreId, entry.MarkdownSafeName + ".md", payload!, linked.Token)
                .ConfigureAwait(false);
            sw.Stop();
            this._uploadedFileIds.Add(fileId);
            DocumentEntry uploaded = entry with
            {
                VectorStoreFileId = fileId,
                UploadDuration = sw.Elapsed,
            };
            return FileSearchOutcome.Success(
                uploaded,
                $"Document `{entry.MarkdownSafeName}`: indexed in vector store — call `file_search` (and pass the filename when asking content questions) to retrieve passages.");
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            // Caller's CT not signaled → the per-upload budget timer fired.
            sw.Stop();
            DocumentEntry timeoutEntry = entry with
            {
                Status = DocumentStatus.Failed,
                Error = "Vector-store upload timed out.",
                UploadDuration = sw.Elapsed,
                Result = null,
                MarkdownResult = null,
            };
            return FileSearchOutcome.Fail(
                timeoutEntry,
                $"Document `{entry.MarkdownSafeName}`: failed to upload (timed out after {sw.Elapsed.TotalSeconds:F1}s).");
        }
        catch (Exception ex)
        {
            sw.Stop();
            DocumentEntry failed = entry with
            {
                Status = DocumentStatus.Failed,
                Error = ex.Message,
                UploadDuration = sw.Elapsed,
                Result = null,
                MarkdownResult = null,
            };
            return FileSearchOutcome.Fail(
                failed,
                $"Document `{entry.MarkdownSafeName}`: failed to upload — {ex.Message}");
        }
    }

    private static bool HasRenderableBody(string? text)
    {
        if (string.IsNullOrEmpty(text))
        {
            return false;
        }

        Match match = s_frontMatterRegex.Match(text!);
        if (!match.Success)
        {
            return text!.Trim().Length > 0;
        }

        string remainder = text!.Substring(match.Length);
        return remainder.Trim().Length > 0;
    }

    private static TimeSpan ClampPositive(TimeSpan span)
        => span <= TimeSpan.Zero ? TimeSpan.Zero : span;

    private async Task<AnalysisOutcome> AnalyzeWithCUClientAsync(
        DetectedAttachment attachment,
        string analyzerId,
        TimeSpan maxWait,
        CancellationToken cancellationToken)
    {
        ContentUnderstandingClient client = await this.EnsureClientAsync(cancellationToken).ConfigureAwait(false);
        Stopwatch stopwatch = Stopwatch.StartNew();

        // Submit the LRO with the caller's CT only; the initial POST is fast and we must
        // honor caller cancellation. The MaxWait deadline applies to the polling step below.
        Operation<AnalysisResult> op;
        if (attachment.Data is not null)
        {
            BinaryData binary = BinaryData.FromBytes(attachment.Data);
            op = await client.AnalyzeBinaryAsync(
                    WaitUntil.Started,
                    analyzerId,
                    binary,
                    contentRange: null,
                    contentType: attachment.ResolvedMediaType,
                    processingLocation: null,
                    cancellationToken: cancellationToken)
                .ConfigureAwait(false);
        }
        else if (attachment.Uri is not null)
        {
            AnalysisInput input = new()
            {
                Uri = attachment.Uri,
                Name = attachment.Filename,
                MimeType = attachment.ResolvedMediaType,
            };
            op = await client.AnalyzeAsync(
                    WaitUntil.Started,
                    analyzerId,
                    new[] { input },
                    modelDeployments: null,
                    processingLocation: null,
                    cancellationToken: cancellationToken)
                .ConfigureAwait(false);
        }
        else
        {
            throw new InvalidOperationException(
                $"DetectedAttachment '{attachment.Filename}' has neither Data nor Uri.");
        }

        using CancellationTokenSource linkedCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        linkedCts.CancelAfter(maxWait);

        try
        {
            Response<AnalysisResult> response = await op.WaitForCompletionAsync(linkedCts.Token).ConfigureAwait(false);
            stopwatch.Stop();
            return new AnalysisOutcome(
                Completed: true,
                Result: response.Value,
                OperationId: op.Id,
                Error: null,
                Duration: stopwatch.Elapsed);
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            // Caller's CT not cancelled → the MaxWait timer fired. Capture a rehydration
            // token so the next turn can resume this same LRO instead of resubmitting.
            stopwatch.Stop();
            string? tokenJson = TrySerializeRehydrationToken(op);
            return new AnalysisOutcome(
                Completed: false,
                Result: null,
                OperationId: op.Id,
                Error: null,
                Duration: stopwatch.Elapsed)
            {
                RehydrationTokenJson = tokenJson,
            };
        }
    }

    private async Task ResolvePendingResultsAsync(
        ContentUnderstandingProviderState providerState,
        CancellationToken cancellationToken)
    {
        // Snapshot keys we need to revisit so we can mutate Documents in place without
        // invalidating an enumerator.
        List<DocumentEntry> pending = new();
        foreach (KeyValuePair<string, DocumentEntry> kvp in providerState.Documents)
        {
            DocumentEntry entry = kvp.Value;
            if (entry.Status == DocumentStatus.Analyzing
                && !string.IsNullOrEmpty(entry.OperationId)
                && !string.IsNullOrEmpty(entry.RehydrationTokenJson))
            {
                pending.Add(entry);
            }
        }

        if (pending.Count == 0)
        {
            return;
        }

        foreach (DocumentEntry entry in pending)
        {
            AnalysisOutcome outcome;
            try
            {
                outcome = this.ResumeOverride is not null
                    ? await this.ResumeOverride(
                            entry.OperationId!,
                            entry.RehydrationTokenJson!,
                            entry.AnalyzerId,
                            this._options.MaxWait,
                            cancellationToken)
                        .ConfigureAwait(false)
                    : await this.ResumeWithCUClientAsync(
                            entry.OperationId!,
                            entry.RehydrationTokenJson!,
                            this._options.MaxWait,
                            cancellationToken)
                        .ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                throw;
            }
            catch (Exception ex)
            {
                providerState.Documents[entry.DocumentKey] = entry with
                {
                    Status = DocumentStatus.Failed,
                    Error = ex.Message,
                    RehydrationTokenJson = null,
                };
                continue;
            }

            if (outcome.Completed && outcome.Result is not null)
            {
                string rendered = AnalysisRenderer.Render(
                    outcome.Result, entry.Filename, this._options.OutputSections);
                string markdownOnly = AnalysisRenderer.Render(
                    outcome.Result, entry.Filename, AnalysisSection.Markdown);
                string? searchPayload = AnalysisRenderer.RenderSearchPayload(
                    outcome.Result, entry.Filename, this._options.OutputSections, this._options.FileSearchConfig);

                providerState.Documents[entry.DocumentKey] = entry with
                {
                    Status = DocumentStatus.Ready,
                    Result = rendered,
                    MarkdownResult = markdownOnly,
                    SearchPayload = searchPayload,
                    AnalyzedAt = DateTimeOffset.UtcNow,
                    AnalysisDuration = (entry.AnalysisDuration ?? TimeSpan.Zero) + outcome.Duration,
                    RehydrationTokenJson = null,
                    Error = null,
                };
            }
            else if (outcome.Error is not null)
            {
                providerState.Documents[entry.DocumentKey] = entry with
                {
                    Status = DocumentStatus.Failed,
                    Error = outcome.Error.Message,
                    RehydrationTokenJson = null,
                };
            }
            else
            {
                // Still running on the service — keep entry Analyzing, refresh the token in
                // case the resume path emitted a new one.
                if (!string.IsNullOrEmpty(outcome.RehydrationTokenJson)
                    && outcome.RehydrationTokenJson != entry.RehydrationTokenJson)
                {
                    providerState.Documents[entry.DocumentKey] = entry with
                    {
                        RehydrationTokenJson = outcome.RehydrationTokenJson,
                    };
                }
            }
        }
    }

    // RehydrationToken / ModelReaderWriter / Operation.Rehydrate are flagged as requiring
    // unreferenced code / dynamic code because they go through the System.ClientModel JSON
    // model reader. RehydrationToken has a source-generated IJsonModel implementation in
    // Azure.Core, so trimming/AOT cannot strip it.
#pragma warning disable IL2026 // RequiresUnreferencedCode
#pragma warning disable IL3050 // RequiresDynamicCode
    private async Task<AnalysisOutcome> ResumeWithCUClientAsync(
        string operationId,
        string rehydrationTokenJson,
        TimeSpan maxWait,
        CancellationToken cancellationToken)
    {
        ContentUnderstandingClient client = await this.EnsureClientAsync(cancellationToken).ConfigureAwait(false);
        RehydrationToken token;
        try
        {
            token = ModelReaderWriter.Read<RehydrationToken>(
                BinaryData.FromString(rehydrationTokenJson),
                ModelReaderWriterOptions.Json);
        }
        catch (Exception ex)
        {
            return new AnalysisOutcome(
                Completed: false,
                Result: null,
                OperationId: operationId,
                Error: ex,
                Duration: TimeSpan.Zero);
        }

        Operation<AnalysisResult> op = Operation.Rehydrate<AnalysisResult>(
            client.Pipeline,
            token,
            this._rehydrateOptions);

        Stopwatch sw = Stopwatch.StartNew();
        using CancellationTokenSource linked = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        linked.CancelAfter(maxWait);
        try
        {
            Response<AnalysisResult> response = await op.WaitForCompletionAsync(linked.Token).ConfigureAwait(false);
            sw.Stop();
            return new AnalysisOutcome(
                Completed: true,
                Result: response.Value,
                OperationId: op.Id,
                Error: null,
                Duration: sw.Elapsed);
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            // Per-turn budget expired; keep the entry Analyzing and reuse the same token next turn.
            sw.Stop();
            return new AnalysisOutcome(
                Completed: false,
                Result: null,
                OperationId: op.Id,
                Error: null,
                Duration: sw.Elapsed)
            {
                RehydrationTokenJson = TrySerializeRehydrationToken(op) ?? rehydrationTokenJson,
            };
        }
    }

    private static string? TrySerializeRehydrationToken<T>(Operation<T> op) where T : notnull
    {
        RehydrationToken? token = op.GetRehydrationToken();
        if (token is null)
        {
            return null;
        }

        try
        {
            BinaryData data = ModelReaderWriter.Write(token.Value, ModelReaderWriterOptions.Json);
            return data.ToString();
        }
        catch
        {
            // If the token can't be serialized the operation simply cannot be resumed; the
            // entry will stay Analyzing forever (or until the user re-uploads the file).
            return null;
        }
    }
#pragma warning restore IL3050
#pragma warning restore IL2026

#pragma warning disable CA1513 // ObjectDisposedException.ThrowIf is .NET 7+ only; this project multi-targets netstandard2.0 and net472.
    private void ThrowIfDisposed()
    {
        if (Volatile.Read(ref this._disposed) != 0)
        {
            throw new ObjectDisposedException(nameof(ContentUnderstandingContextProvider));
        }
    }
#pragma warning restore CA1513
}
