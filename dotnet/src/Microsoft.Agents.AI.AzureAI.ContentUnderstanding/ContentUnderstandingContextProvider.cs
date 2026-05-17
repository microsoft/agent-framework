// Copyright (c) Microsoft. All rights reserved.

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
/// Phase 5 ships the single-document happy path: detect attachments, submit them to Content
/// Understanding, wait up to <see cref="ContentUnderstandingContextProviderOptions.MaxWait"/>
/// for completion, strip the binary content out of the message stream (Strategy C from the
/// Phase 0 spike), and append the rendered markdown so the LLM only sees text. Background
/// continuation, multi-document tools, and FileSearch are implemented in Phases 6–9. See
/// <c>features/sdk/dotnet-cu-context-provider/design-doc-dotnet-cu-context-provider.md</c>.
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

    // Mirrors Python `_FRONT_MATTER_RE`: matches a leading YAML front-matter block delimited by
    // '---' lines, allowing CR/LF line endings and tolerating end-of-string after the closer.
    private static readonly Regex s_frontMatterRegex =
        new(@"\A---\r?\n.*?\r?\n---(?:\r?\n|\z)", RegexOptions.Singleline | RegexOptions.Compiled);

    private readonly ContentUnderstandingContextProviderOptions _options;
    private readonly ProviderSessionState<ContentUnderstandingProviderState> _state;
    private readonly IContentUnderstandingClientFactory _clientFactory;
    private readonly SemaphoreSlim _clientInitLock = new(1, 1);
    private readonly BackgroundAnalysisRunner _runner = new();
    private readonly ConcurrentBag<Task> _runnerTasks = new();
    private readonly CancellationTokenSource _disposeCts = new();
    private readonly AITool[] _tools;
    private readonly ConcurrentBag<string> _uploadedFileIds = new();
    private ContentUnderstandingProviderState? _activeState;
    private ContentUnderstandingClient? _client;
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
    /// endpoint and credential, with optional inline configuration of additional options.
    /// </summary>
    /// <param name="endpoint">The Content Understanding service endpoint.</param>
    /// <param name="credential">The credential used to authenticate against the service.</param>
    /// <param name="configure">Optional callback to set additional options.</param>
    /// <exception cref="ArgumentNullException"><paramref name="endpoint"/> or <paramref name="credential"/> is <see langword="null"/>.</exception>
    public ContentUnderstandingContextProvider(
        Uri endpoint,
        TokenCredential credential,
        Action<ContentUnderstandingContextProviderOptions>? configure = null)
        : this(BuildOptions(endpoint, credential, configure))
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
    /// this to avoid live network calls. Returns an <see cref="AnalysisAttempt"/> whose
    /// <c>Continuation</c> is non-null only when the outer attempt timed out before reaching a
    /// terminal state and the background runner should resume polling.
    /// </summary>
    internal Func<DetectedAttachment, string, TimeSpan, CancellationToken, Task<AnalysisAttempt>>? AnalyzeOverride { get; init; }

    /// <inheritdoc/>
    protected override async ValueTask<AIContext> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        _ = context ?? throw new ArgumentNullException(nameof(context));
        this.ThrowIfDisposed();

        AIContext input = context.AIContext;
        ContentUnderstandingProviderState providerState = this._state.GetOrInitializeState(context.Session);
        // Refresh the tool's view of the live state. Tools constructed in the ctor close over
        // this field via Func<...> so they see whichever session most recently invoked us.
        this._activeState = providerState;

        // Phase 6 cross-turn promotion: surface every Ready document not yet injected. The
        // background runner already mutated state.Documents in place (the StateBag caches the
        // live object), so a simple scan picks up the latest status without any explicit
        // rehydrate call.
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

        foreach (DetectedAttachment att in detected)
        {
            toStrip.Add(att.OriginalContent);

            if (providerState.Documents.ContainsKey(att.Filename))
            {
                throw new InvalidOperationException(
                    $"Duplicate document filename in session: '{att.Filename}'. Each filename may be analyzed at most once per session.");
            }

            string analyzerId = AnalyzerSelector.Select(att.ResolvedMediaType, this._options.AnalyzerId);
            AnalysisAttempt attempt;
            try
            {
                attempt = this.AnalyzeOverride is not null
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

            AnalysisOutcome outcome = attempt.Outcome;
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
                    AnalysisSection.Markdown,
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
                    SizeBytes = att.Data?.Length,
                };
            }

            providerState.Documents[att.Filename] = entry;

            // If the foreground attempt timed out and the caller produced a continuation,
            // resume polling on a background task scoped to disposal.
            if (entry.Status == DocumentStatus.Analyzing && attempt.Continuation is not null)
            {
                Task runner = this._runner.StartAsync(
                    att.Filename,
                    attempt.Continuation,
                    providerState,
                    this._options.OutputSections,
                    this._options.FileSearchConfig,
                    this._disposeCts.Token);
                this._runnerTasks.Add(runner);
            }
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
                        ?? $"Document `{doc.Filename}`: indexed in vector store.";
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

        // Signal background runners to stop. They observe _disposeCts.Token and swallow OCE.
        try
        {
            this._disposeCts.Cancel();
        }
        catch (ObjectDisposedException)
        {
            // Already disposed elsewhere — safe to ignore.
        }

        // Snapshot in-flight runners; bounded wait so a stuck poll cannot block disposal forever.
        Task[] snapshot = this._runnerTasks.ToArray();
        if (snapshot.Length > 0)
        {
            Task all = Task.WhenAll(snapshot);
            Task completed = await Task.WhenAny(all, Task.Delay(TimeSpan.FromSeconds(2))).ConfigureAwait(false);
            if (ReferenceEquals(completed, all))
            {
                try
                {
                    await all.ConfigureAwait(false);
                }
                catch (OperationCanceledException)
                {
                    // Expected on cancellation.
                }
                catch
                {
                    // Runners are documented to never let exceptions escape; defensive swallow.
                }
            }
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

        this._disposeCts.Dispose();
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
    /// Internal test seam: awaits every background analysis runner spawned so far, in order
    /// to make Phase 6 cross-turn promotion tests deterministic without polling.
    /// </summary>
    internal Task WaitForBackgroundTasksAsync()
    {
        Task[] snapshot = this._runnerTasks.ToArray();
        return snapshot.Length == 0 ? Task.CompletedTask : Task.WhenAll(snapshot);
    }

    /// <summary>
    /// Internal test seam: reads the provider state for a session without going through
    /// <see cref="InvokingCoreAsync"/> and without the disposal check, so tests can inspect
    /// state both before and after <see cref="DisposeAsync"/>.
    /// </summary>
    internal ContentUnderstandingProviderState GetStateForTesting(AgentSession? session)
        => this._state.GetOrInitializeState(session);

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
                $"Document `{entry.Filename}`: indexed in vector store — call `file_search` to query its contents.");
        }

        string? payload = entry.SearchPayload;
        if (!HasRenderableBody(payload))
        {
            // Empty / front-matter-only payload would create a vacuous vector-store record.
            // Skip the upload but keep the entry Ready so list_documents reflects truth.
            return FileSearchOutcome.Skip(
                entry,
                $"Document `{entry.Filename}`: no searchable text after analysis (skipped vector-store upload).");
        }

        if (budget <= TimeSpan.Zero)
        {
            DocumentEntry timeoutEntry = entry with
            {
                Status = DocumentStatus.Failed,
                Error = "Vector-store upload skipped: foreground budget already exhausted by analysis.",
            };
            return FileSearchOutcome.Fail(
                timeoutEntry,
                $"Document `{entry.Filename}`: failed to upload (foreground time budget exhausted).");
        }

        Stopwatch sw = Stopwatch.StartNew();
        using CancellationTokenSource linked = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        linked.CancelAfter(budget);
        try
        {
            string fileId = await config.Backend
                .UploadAsync(config.VectorStoreId, entry.Filename + ".md", payload!, linked.Token)
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
                $"Document `{entry.Filename}`: indexed in vector store — call `file_search` (and pass the filename when asking content questions) to retrieve passages.");
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
            };
            return FileSearchOutcome.Fail(
                timeoutEntry,
                $"Document `{entry.Filename}`: failed to upload (timed out after {sw.Elapsed.TotalSeconds:F1}s).");
        }
        catch (Exception ex)
        {
            sw.Stop();
            DocumentEntry failed = entry with
            {
                Status = DocumentStatus.Failed,
                Error = ex.Message,
                UploadDuration = sw.Elapsed,
            };
            return FileSearchOutcome.Fail(
                failed,
                $"Document `{entry.Filename}`: failed to upload — {ex.Message}");
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

    private async Task<AnalysisAttempt> AnalyzeWithCUClientAsync(
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
            return new AnalysisAttempt(
                new AnalysisOutcome(
                    Completed: true,
                    Result: response.Value,
                    OperationId: op.Id,
                    Error: null,
                    Duration: stopwatch.Elapsed),
                Continuation: null);
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            // Caller's CT not cancelled → the MaxWait timer fired. Hand the still-running
            // operation off to the background runner.
            stopwatch.Stop();
            TimeSpan elapsed = stopwatch.Elapsed;
            Operation<AnalysisResult> capturedOp = op;
            return new AnalysisAttempt(
                new AnalysisOutcome(
                    Completed: false,
                    Result: null,
                    OperationId: capturedOp.Id,
                    Error: null,
                    Duration: elapsed),
                Continuation: async ct =>
                {
                    Stopwatch innerSw = Stopwatch.StartNew();
                    Response<AnalysisResult> r = await capturedOp.WaitForCompletionAsync(ct).ConfigureAwait(false);
                    innerSw.Stop();
                    return new AnalysisOutcome(
                        Completed: true,
                        Result: r.Value,
                        OperationId: capturedOp.Id,
                        Error: null,
                        Duration: elapsed + innerSw.Elapsed);
                });
        }
    }

#pragma warning disable CA1513 // ObjectDisposedException.ThrowIf is .NET 7+ only; this project multi-targets netstandard2.0 and net472.
    private void ThrowIfDisposed()
    {
        if (Volatile.Read(ref this._disposed) != 0)
        {
            throw new ObjectDisposedException(nameof(ContentUnderstandingContextProvider));
        }
    }
#pragma warning restore CA1513

    private static ContentUnderstandingContextProviderOptions BuildOptions(
        Uri endpoint,
        TokenCredential credential,
        Action<ContentUnderstandingContextProviderOptions>? configure)
    {
        // ContentUnderstandingContextProviderOptions' constructor null-checks endpoint and
        // credential, so the convenience overload reuses that validation rather than duplicating it.
        var options = new ContentUnderstandingContextProviderOptions(endpoint, credential);
        configure?.Invoke(options);
        return options;
    }
}

/// <summary>
/// Result of one analysis attempt. <see cref="Completed"/> distinguishes "finished within
/// MaxWait" (Result is set) from "timed out" (OperationId may be set for Phase 6 resumption)
/// from "failed" (Error is set).
/// </summary>
internal sealed record AnalysisOutcome(
    bool Completed,
    AnalysisResult? Result,
    string? OperationId,
    Exception? Error,
    TimeSpan Duration);

/// <summary>
/// One foreground analysis attempt plus, when the attempt timed out before the LRO reached a
/// terminal state, a <paramref name="Continuation"/> the background runner can resume to drive
/// the same operation to completion. Continuation is <see langword="null"/> when there is no
/// further polling work (success / failure / caller-cancelled).
/// </summary>
internal sealed record AnalysisAttempt(
    AnalysisOutcome Outcome,
    Func<CancellationToken, Task<AnalysisOutcome>>? Continuation);

/// <summary>
/// Phase 9 — outcome of an attempted vector-store upload for one document. Carries the updated
/// <see cref="DocumentEntry"/> (status/error/file-id/upload-duration stamps) and an optional
/// short note to splice into <c>AIContext.Messages</c>. <see cref="UpdatedEntry"/> may be
/// reference-equal to the input when no mutation is needed (skip path).
/// </summary>
internal readonly record struct FileSearchOutcome(DocumentEntry? UpdatedEntry, string? NoteText)
{
    public static FileSearchOutcome Success(DocumentEntry entry, string note) => new(entry, note);
    public static FileSearchOutcome Fail(DocumentEntry entry, string note) => new(entry, note);
    public static FileSearchOutcome Skip(DocumentEntry entry, string? note) => new(entry, note);
}
