// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.IO;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;
using OpenAI.Files;
using OpenAI.Responses;
using OpenAI.VectorStores;

#pragma warning disable OPENAI001

namespace Microsoft.Agents.AI.Foundry;

/// <summary>
/// Foundry chat-client decorator that unifies the three Foundry chat-client construction
/// modes (Responses Agent, Prompt Agent, Agent Endpoint) behind a single type and centralizes
/// Foundry-specific concerns: <c>microsoft.foundry</c> telemetry tagging,
/// <c>agent-framework-dotnet/{version}</c> User-Agent stamping, <c>x-ms-served-model</c>
/// response-header capture, and (for Prompt Agents) per-request payload mutation that injects
/// the agent reference and strips per-request overrides that the server owns.
/// </summary>
/// <remarks>
/// <para>
/// Replaces the previous <c>AzureAIProjectChatClient</c> and <c>AzureAIProjectResponsesChatClient</c>
/// decorators. All Foundry entry points (the public <c>FoundryAgent</c> constructors and the
/// <c>AIProjectClientExtensions.AsAIAgent</c> overloads) now construct a
/// <see cref="FoundryChatClient"/> internally, so telemetry and the agent-framework User-Agent
/// segment are uniform across paths.
/// </para>
/// <para>
/// The three construction modes are:
/// </para>
/// <list type="bullet">
///   <item><description><b>Responses Agent</b> (Mode 1): direct Responses API call against a project-level model id; no server-side agent definition exists. Constructed from <c>(AIProjectClient, modelId)</c>.</description></item>
///   <item><description><b>Prompt Agent</b> (Mode 2): server-side agent definition (a <see cref="ProjectsAgentDefinition"/>, typically a <see cref="DeclarativeAgentDefinition"/>) invoked by <see cref="AgentReference"/> against the project Responses URL. Constructed from <see cref="AgentReference"/>, <see cref="ProjectsAgentVersion"/>, or <see cref="ProjectsAgentRecord"/>.</description></item>
///   <item><description><b>Agent Endpoint</b> (Mode 3): invocation via the per-agent endpoint URL <c>…/projects/{p}/agents/{name}/endpoint/protocols/openai</c>. The agent behind the endpoint can be either a hosted (container-backed) agent or a Prompt Agent. Constructed from <c>(Uri agentEndpoint, credential)</c>.</description></item>
/// </list>
/// <para>
/// Note: "Hosted Agent" refers to a container-based runtime agent (see
/// <c>Microsoft.Agents.AI.Foundry.Hosting</c>) and is the <i>kind</i> of agent that may sit
/// behind an Agent Endpoint. It is not synonymous with the Agent Endpoint mode itself.
/// </para>
/// </remarks>
public sealed class FoundryChatClient : DelegatingChatClient
{
    private readonly ChatClientMetadata _metadata;
    private readonly AIProjectClient? _aiProjectClient;
    private readonly AgentReference? _agentReference;
    private readonly ProjectsAgentVersion? _agentVersion;
    private readonly ProjectsAgentRecord? _agentRecord;
    private readonly ChatOptions? _baseChatOptions;

    /// <summary>
    /// Initializes a new instance for the Responses Agent mode (Mode 1): direct Responses API
    /// call against a project-level model id; no server-side agent definition exists.
    /// </summary>
    /// <param name="aiProjectClient">The project client.</param>
    /// <param name="modelId">The model deployment id.</param>
    internal FoundryChatClient(AIProjectClient aiProjectClient, string modelId)
        : base(Throw.IfNull(aiProjectClient)
            .GetProjectOpenAIClient()
            .GetProjectResponsesClientForModel(Throw.IfNullOrWhitespace(modelId))
            .AsIChatClient())
    {
        this._aiProjectClient = aiProjectClient;
        this._metadata = new ChatClientMetadata("microsoft.foundry", defaultModelId: modelId);
        TryRegisterAgentFrameworkUserAgentPolicy(this.InnerClient);
        TryRegisterServedModelPolicy(this.InnerClient);
    }

    /// <summary>
    /// Initializes a new instance for the Prompt Agent mode (Mode 2): server-side agent
    /// definition invoked by <see cref="AgentReference"/>.
    /// </summary>
    internal FoundryChatClient(AIProjectClient aiProjectClient, AgentReference agentReference, string? defaultModelId, ChatOptions? baseChatOptions)
        : base(Throw.IfNull(aiProjectClient)
            .GetProjectOpenAIClient()
            .GetProjectResponsesClientForAgent(Throw.IfNull(agentReference))
            .AsIChatClient())
    {
        this._aiProjectClient = aiProjectClient;
        this._agentReference = agentReference;
        this._metadata = new ChatClientMetadata("microsoft.foundry", defaultModelId: defaultModelId);
        this._baseChatOptions = baseChatOptions;
        this.AgentName = agentReference.Name;
        TryRegisterAgentFrameworkUserAgentPolicy(this.InnerClient);
        TryRegisterServedModelPolicy(this.InnerClient);
    }

    /// <summary>
    /// Initializes a new instance for the Prompt Agent mode (Mode 2, record variant):
    /// server-side agent definition invoked by record, resolving to the latest version.
    /// </summary>
    internal FoundryChatClient(AIProjectClient aiProjectClient, ProjectsAgentRecord agentRecord, ChatOptions? baseChatOptions)
        : this(aiProjectClient, Throw.IfNull(agentRecord).GetLatestVersion(), baseChatOptions)
    {
        this._agentRecord = agentRecord;
    }

    /// <summary>
    /// Initializes a new instance for the Prompt Agent mode (Mode 2, version variant):
    /// server-side agent definition invoked by a specific version.
    /// </summary>
    internal FoundryChatClient(AIProjectClient aiProjectClient, ProjectsAgentVersion agentVersion, ChatOptions? baseChatOptions)
        : this(
              aiProjectClient,
              CreateAgentReference(Throw.IfNull(agentVersion)),
              (agentVersion.Definition as DeclarativeAgentDefinition)?.Model,
              baseChatOptions)
    {
        this._agentVersion = agentVersion;
    }

    /// <summary>
    /// Initializes a new instance for the Agent Endpoint mode (Mode 3): invocation via the
    /// per-agent endpoint URL. Parses the URL into its per-agent
    /// <see cref="ProjectOpenAIClient"/> shape internally and forwards through the resulting
    /// responses client.
    /// </summary>
    /// <param name="agentEndpoint">
    /// The agent-specific endpoint URI. Must be of the shape
    /// <c>https://&lt;host&gt;/.../projects/&lt;project&gt;/agents/&lt;agentName&gt;/endpoint/protocols/openai</c>.
    /// </param>
    /// <param name="credential">The authentication credential.</param>
    /// <param name="clientOptions">Optional per-agent client options. <c>Endpoint</c> and <c>AgentName</c> are owned by this ctor and overridden with values derived from <paramref name="agentEndpoint"/>.</param>
    internal FoundryChatClient(Uri agentEndpoint, AuthenticationTokenProvider credential, ProjectOpenAIClientOptions? clientOptions)
        : this(BuildAgentEndpointInner(agentEndpoint, credential, clientOptions))
    {
    }

    /// <summary>
    /// Initializes a new instance for the Agent Endpoint mode (Mode 3) by reusing an existing
    /// <see cref="AIProjectClient"/>'s pipeline. Equivalent to the
    /// <see cref="FoundryChatClient(Uri, AuthenticationTokenProvider, ProjectOpenAIClientOptions?)"/>
    /// constructor but skips building a fresh per-agent pipeline: the project-level
    /// <see cref="ProjectOpenAIClient"/> on <paramref name="aiProjectClient"/> is used directly.
    /// </summary>
    /// <param name="aiProjectClient">The project client already configured at the project root containing <paramref name="agentEndpoint"/>.</param>
    /// <param name="agentEndpoint">The per-agent endpoint URI. Same shape constraints as the other agent-endpoint ctor.</param>
    /// <param name="clientOptions">Optional per-agent client options applied to the per-agent <c>GetProjectResponsesClientForAgentEndpoint</c> call.</param>
    internal FoundryChatClient(AIProjectClient aiProjectClient, Uri agentEndpoint, ProjectOpenAIClientOptions? clientOptions)
        : this(BuildAgentEndpointInnerFromProjectClient(aiProjectClient, agentEndpoint, clientOptions))
    {
    }

    private FoundryChatClient(AgentEndpointInner inner)
        : base(inner.ChatClient)
    {
        this._aiProjectClient = inner.AIProjectClient;
        this.AgentName = inner.AgentName;
        this._metadata = new ChatClientMetadata("microsoft.foundry");
        TryRegisterAgentFrameworkUserAgentPolicy(this.InnerClient);
        TryRegisterServedModelPolicy(this.InnerClient);
    }

    /// <summary>
    /// Gets the agent name associated with this chat client.
    /// </summary>
    /// <remarks>
    /// <para>Set in two cases:</para>
    /// <list type="bullet">
    /// <item>
    /// <description>
    /// Prompt Agent mode (Mode 2): the value of <see cref="AgentReference.Name"/> supplied at
    /// construction.
    /// </description>
    /// </item>
    /// <item>
    /// <description>
    /// Agent Endpoint mode (Mode 3): the agent name segment parsed from the supplied agent
    /// endpoint URI.
    /// </description>
    /// </item>
    /// </list>
    /// <para>
    /// Returns <see langword="null"/> for the Responses Agent mode (Mode 1) where no agent name
    /// exists.
    /// </para>
    /// </remarks>
    internal string? AgentName { get; }

    /// <inheritdoc/>
    public override object? GetService(Type serviceType, object? serviceKey = null)
    {
        return (serviceKey is null && serviceType == typeof(ChatClientMetadata))
            ? this._metadata
            : (serviceKey is null && serviceType == typeof(AIProjectClient))
            ? this._aiProjectClient
            : (serviceKey is null && serviceType == typeof(AgentReference))
            ? this._agentReference
            : (serviceKey is null && serviceType == typeof(ProjectsAgentVersion))
            ? this._agentVersion
            : (serviceKey is null && serviceType == typeof(ProjectsAgentRecord))
            ? this._agentRecord
            : base.GetService(serviceType, serviceKey);
    }

    /// <inheritdoc/>
    public override async Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
    {
        var effectiveOptions = this._agentReference is not null
            ? this.GetAgentEnabledChatOptions(options)
            : options;

        var box = new StrongBox<string?>(null);
        var previous = ServedModelScope.Current;
        ServedModelScope.Current = box;

        try
        {
            var response = await base.GetResponseAsync(messages, effectiveOptions, cancellationToken).ConfigureAwait(false);

            if (box.Value is { } servedModel)
            {
                response.ModelId = servedModel;
            }

            return response;
        }
        finally
        {
            ServedModelScope.Current = previous;
        }
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var effectiveOptions = this._agentReference is not null
            ? this.GetAgentEnabledChatOptions(options)
            : options;

        var box = new StrongBox<string?>(null);
        var previous = ServedModelScope.Current;
        ServedModelScope.Current = box;

        try
        {
            await foreach (var chunk in base.GetStreamingResponseAsync(messages, effectiveOptions, cancellationToken).ConfigureAwait(false))
            {
                if (box.Value is { } servedModel)
                {
                    chunk.ModelId = servedModel;
                }

                yield return chunk;
            }
        }
        finally
        {
            ServedModelScope.Current = previous;
        }
    }

    #region File and vector-store helpers (mirrors Python's foundry_chat_client surface)

    /// <summary>
    /// Uploads a single file to the project for the supplied purpose. The upload is performed
    /// against the project-level <see cref="AIProjectClient"/> reachable via
    /// <see cref="GetService(Type, object?)"/>, so this method works uniformly across all three
    /// FoundryChatClient construction modes.
    /// </summary>
    /// <param name="filePath">Absolute or relative path to the file to upload. The file must exist.</param>
    /// <param name="purpose">The file upload purpose (e.g. <see cref="FileUploadPurpose.Assistants"/>).</param>
    /// <param name="cancellationToken">A token that can cancel the upload.</param>
    /// <returns>The created <see cref="OpenAIFile"/> as returned by the service.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="filePath"/> is <see langword="null"/>.</exception>
    /// <exception cref="FileNotFoundException">The file at <paramref name="filePath"/> does not exist.</exception>
    public async Task<OpenAIFile> UploadFileAsync(string filePath, FileUploadPurpose purpose, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(filePath);
        if (!File.Exists(filePath))
        {
            throw new FileNotFoundException($"File not found: '{filePath}'.", filePath);
        }

        var fileClient = this.GetOpenAIFileClient();
        // Use the Stream overload to honor cancellation; the (string, purpose) overload has no
        // CancellationToken parameter in the OpenAI SDK.
        using var stream = File.OpenRead(filePath);
        var result = await fileClient.UploadFileAsync(stream, Path.GetFileName(filePath), purpose, cancellationToken).ConfigureAwait(false);
        return result.Value;
    }

    /// <summary>Deletes a file previously uploaded to the project.</summary>
    /// <param name="fileId">The file id returned by <see cref="UploadFileAsync(string, FileUploadPurpose, CancellationToken)"/>.</param>
    /// <param name="cancellationToken">A token that can cancel the delete.</param>
    /// <returns>The deletion result.</returns>
    /// <exception cref="ArgumentException"><paramref name="fileId"/> is <see langword="null"/> or whitespace.</exception>
    public async Task<FileDeletionResult> DeleteFileAsync(string fileId, CancellationToken cancellationToken = default)
    {
        Throw.IfNullOrWhitespace(fileId);
        var fileClient = this.GetOpenAIFileClient();
        var result = await fileClient.DeleteFileAsync(fileId, cancellationToken).ConfigureAwait(false);
        return result.Value;
    }

    /// <summary>
    /// Uploads the supplied files, creates a vector store containing them, waits until the
    /// store finishes ingesting its files (status leaves <see cref="VectorStoreStatus.InProgress"/>),
    /// and returns the <see cref="VectorStore"/>. Mirrors Python's
    /// <c>foundry_chat_client.create_vector_store(name, files, expires_after_days)</c>.
    /// </summary>
    /// <param name="name">The vector store name.</param>
    /// <param name="filePaths">Paths to files to upload and attach to the store.</param>
    /// <param name="expiresAfter">Optional last-active-at expiration window. When supplied, the vector store expires this many days after its last use.</param>
    /// <param name="pollingTimeout">Optional upper bound on the wait for the vector store to leave <see cref="VectorStoreStatus.InProgress"/>. Defaults to 5 minutes when not supplied; pass <see cref="Timeout.InfiniteTimeSpan"/> to disable. Independent of <paramref name="cancellationToken"/>: cancellation always wins.</param>
    /// <param name="cancellationToken">A token that can cancel the orchestration.</param>
    /// <returns>The created and fully-ready <see cref="VectorStore"/>. The returned instance reflects the state observed after polling completes; it may be in <see cref="VectorStoreStatus.Completed"/> (typical), <see cref="VectorStoreStatus.Expired"/>, or any other terminal status returned by the service. Only <see cref="VectorStoreStatus.InProgress"/> is polled.</returns>
    /// <remarks>
    /// <para>
    /// File-upload semantics are best-effort: when one of the per-file uploads throws, this method
    /// makes a best-effort attempt to delete the files it has already uploaded so they do not
    /// accumulate as orphaned resources on the project, then rethrows the original exception. The
    /// cleanup itself does not throw — its failures are silently ignored because the caller is
    /// already receiving a more meaningful exception from the original upload failure.
    /// </para>
    /// <para>
    /// Cancellation aborts the polling loop with an <see cref="OperationCanceledException"/>; any
    /// already-uploaded files and the partially-created vector store remain on the project and are
    /// the caller's responsibility to clean up. The same applies when the polling timeout elapses
    /// (a <see cref="TimeoutException"/> is thrown instead).
    /// </para>
    /// </remarks>
    /// <exception cref="ArgumentException"><paramref name="name"/> is <see langword="null"/> or whitespace, or <paramref name="filePaths"/> is <see langword="null"/>.</exception>
    /// <exception cref="TimeoutException">The vector store did not leave <see cref="VectorStoreStatus.InProgress"/> within <paramref name="pollingTimeout"/>.</exception>
    public async Task<VectorStore> CreateVectorStoreAsync(string name, IEnumerable<string> filePaths, TimeSpan? expiresAfter = null, TimeSpan? pollingTimeout = null, CancellationToken cancellationToken = default)
    {
        Throw.IfNullOrWhitespace(name);
        Throw.IfNull(filePaths);

        var fileIds = new List<string>();
        try
        {
            foreach (var path in filePaths)
            {
                cancellationToken.ThrowIfCancellationRequested();
                var uploaded = await this.UploadFileAsync(path, FileUploadPurpose.Assistants, cancellationToken).ConfigureAwait(false);
                fileIds.Add(uploaded.Id);
            }
        }
        catch
        {
            // Q-B: best-effort cleanup of files already uploaded before the mid-loop failure so
            // they do not accumulate as orphaned resources on the project. Swallow cleanup
            // exceptions — the caller is already going to see the original upload exception, and
            // there is nothing useful we can do with a secondary delete failure.
            await this.BestEffortDeleteFilesAsync(fileIds).ConfigureAwait(false);
            throw;
        }

        var options = new VectorStoreCreationOptions
        {
            Name = name,
        };
        foreach (var id in fileIds)
        {
            options.FileIds.Add(id);
        }
        if (expiresAfter is { } window)
        {
            options.ExpirationPolicy = new VectorStoreExpirationPolicy(VectorStoreExpirationAnchor.LastActiveAt, (int)Math.Ceiling(window.TotalDays));
        }

        var vectorStoreClient = this.GetVectorStoreClient();
        var createResult = await vectorStoreClient.CreateVectorStoreAsync(options, cancellationToken).ConfigureAwait(false);
        var created = createResult.Value;

        // Q-A: poll until the vector store leaves the in-progress state. Without this the helper
        // hands the caller a vector store whose file ingestion may still be running, defeating
        // the purpose of the one-call wrapper.
        return await WaitForVectorStoreReadyAsync(vectorStoreClient, created, pollingTimeout ?? s_defaultPollingTimeout, cancellationToken).ConfigureAwait(false);
    }

    private async Task BestEffortDeleteFilesAsync(IEnumerable<string> fileIds)
    {
        foreach (var id in fileIds)
        {
            try
            {
                // Pass CancellationToken.None: cleanup runs in the catch path; the caller's
                // token may already be cancelled and we still want to do our best to free
                // orphaned resources before propagating the original exception.
                await this.DeleteFileAsync(id, CancellationToken.None).ConfigureAwait(false);
            }
            catch
            {
                // Silently ignore cleanup failures; see XML doc on CreateVectorStoreAsync.
            }
        }
    }

    /// <summary>Upper bound on <see cref="WaitForVectorStoreReadyAsync"/> when the caller does not supply one. Chosen to comfortably cover normal Foundry vector-store ingestion (seconds to a minute for modest file sets) while still surfacing a clear failure if the server is stuck.</summary>
    private static readonly TimeSpan s_defaultPollingTimeout = TimeSpan.FromMinutes(5);

    private static async Task<VectorStore> WaitForVectorStoreReadyAsync(VectorStoreClient client, VectorStore initial, TimeSpan timeout, CancellationToken cancellationToken)
    {
        if (initial.Status != VectorStoreStatus.InProgress)
        {
            return initial;
        }

        var stopwatch = System.Diagnostics.Stopwatch.StartNew();
        var delay = TimeSpan.FromMilliseconds(250);
        var maxDelay = TimeSpan.FromSeconds(2);
        var current = initial;
        while (current.Status == VectorStoreStatus.InProgress)
        {
            if (timeout != Timeout.InfiniteTimeSpan && stopwatch.Elapsed >= timeout)
            {
                throw new TimeoutException(
                    $"Vector store '{current.Id}' did not leave the in-progress state within {timeout.TotalSeconds:0.##} seconds.");
            }

            await Task.Delay(delay, cancellationToken).ConfigureAwait(false);
            var refreshed = await client.GetVectorStoreAsync(current.Id, cancellationToken).ConfigureAwait(false);
            current = refreshed.Value;

            if (delay < maxDelay)
            {
                var next = TimeSpan.FromMilliseconds(delay.TotalMilliseconds * 2);
                delay = next < maxDelay ? next : maxDelay;
            }
        }

        return current;
    }

    /// <summary>Deletes a vector store. The associated files (if any) are not deleted by this method; call <see cref="DeleteFileAsync(string, CancellationToken)"/> separately to clean them up.</summary>
    /// <param name="vectorStoreId">The vector store id.</param>
    /// <param name="cancellationToken">A token that can cancel the delete.</param>
    /// <returns>The deletion result.</returns>
    /// <exception cref="ArgumentException"><paramref name="vectorStoreId"/> is <see langword="null"/> or whitespace.</exception>
    public async Task<VectorStoreDeletionResult> DeleteVectorStoreAsync(string vectorStoreId, CancellationToken cancellationToken = default)
    {
        Throw.IfNullOrWhitespace(vectorStoreId);
        var vectorStoreClient = this.GetVectorStoreClient();
        var result = await vectorStoreClient.DeleteVectorStoreAsync(vectorStoreId, cancellationToken).ConfigureAwait(false);
        return result.Value;
    }

    private OpenAIFileClient GetOpenAIFileClient()
    {
        var projectClient = this._aiProjectClient
            ?? throw new InvalidOperationException("This FoundryChatClient does not have an AIProjectClient available. File and vector-store helpers require an AIProjectClient.");
        return projectClient.GetProjectOpenAIClient().GetOpenAIFileClient();
    }

    private VectorStoreClient GetVectorStoreClient()
    {
        var projectClient = this._aiProjectClient
            ?? throw new InvalidOperationException("This FoundryChatClient does not have an AIProjectClient available. File and vector-store helpers require an AIProjectClient.");
        return projectClient.GetProjectOpenAIClient().GetVectorStoreClient();
    }

    #endregion

    /// <summary>
    /// Parses an agent endpoint URI of shape
    /// <c>https://&lt;host&gt;/.../projects/&lt;project&gt;/agents/&lt;agentName&gt;/endpoint/protocols/openai</c>
    /// and returns the agent name and the derived project-root URI.
    /// </summary>
    /// <remarks>
    /// Tolerates trailing slash, casing variants on <c>/agents/</c> and the suffix segment, and
    /// strips query string and fragment. Throws <see cref="ArgumentException"/> for inputs that
    /// do not match the expected shape.
    /// </remarks>
    /// <exception cref="ArgumentException">
    /// The endpoint is missing the <c>/agents/</c> segment, has an empty agent name, or has a
    /// suffix other than <c>/endpoint/protocols/openai</c>.
    /// </exception>
    internal static (string AgentName, Uri ProjectRoot) ParseAgentEndpoint(Uri agentEndpoint)
    {
        Throw.IfNull(agentEndpoint);

        const string AgentsSegment = "/agents/";
        const string ExpectedSuffix = "/endpoint/protocols/openai";

        var path = agentEndpoint.AbsolutePath.TrimEnd('/');
        var idx = path.IndexOf(AgentsSegment, StringComparison.OrdinalIgnoreCase);
        if (idx < 0)
        {
            throw new ArgumentException(
                $"Expected an agent endpoint of shape 'https://<host>/.../projects/<project>/agents/<agentName>/endpoint/protocols/openai' but got '{agentEndpoint}'. " +
                "If you want to construct a FoundryAgent against a project endpoint, use the (Uri projectEndpoint, AuthenticationTokenProvider credential, string model, string instructions, ...) constructor instead.",
                nameof(agentEndpoint));
        }

        var afterAgents = path.Substring(idx + AgentsSegment.Length);
        var nextSlash = afterAgents.IndexOf('/');
        if (nextSlash <= 0)
        {
            throw new ArgumentException(
                $"Agent endpoint '{agentEndpoint}' is missing the '<agentName>{ExpectedSuffix}' suffix.",
                nameof(agentEndpoint));
        }

        var agentName = afterAgents.Substring(0, nextSlash);
        var suffix = afterAgents.Substring(nextSlash);
        if (!string.Equals(suffix, ExpectedSuffix, StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException(
                $"Agent endpoint '{agentEndpoint}' has an unexpected suffix '{suffix}'. Expected '{ExpectedSuffix}'.",
                nameof(agentEndpoint));
        }

        var rootPath = path.Substring(0, idx);
        var projectRoot = new UriBuilder(agentEndpoint)
        {
            Path = rootPath,
            Query = string.Empty,
            Fragment = string.Empty,
        }.Uri;

        return (agentName, projectRoot);
    }

    private ChatOptions GetAgentEnabledChatOptions(ChatOptions? options)
    {
        // Start with a clone of the base chat options defined for the agent, if any.
        ChatOptions agentEnabledChatOptions = this._baseChatOptions?.Clone() ?? new();

        // Ignore per-request all options that can't be overridden.
        agentEnabledChatOptions.Instructions = null;
        agentEnabledChatOptions.Tools = null;
        agentEnabledChatOptions.Temperature = null;
        agentEnabledChatOptions.TopP = null;
        agentEnabledChatOptions.PresencePenalty = null;
        agentEnabledChatOptions.ResponseFormat = null;

        // Use the conversation from the request, or the one defined at the client level.
        agentEnabledChatOptions.ConversationId = options?.ConversationId ?? this._baseChatOptions?.ConversationId;

        // Preserve the original RawRepresentationFactory.
        var originalFactory = options?.RawRepresentationFactory;

        agentEnabledChatOptions.RawRepresentationFactory = (client) =>
        {
            if (originalFactory?.Invoke(this) is not CreateResponseOptions responseCreationOptions)
            {
                responseCreationOptions = new CreateResponseOptions();
            }

            responseCreationOptions.Agent = this._agentReference;
#pragma warning disable SCME0001 // Type is for evaluation purposes only and is subject to change or removal in future updates.
            responseCreationOptions.Patch.Remove("$.model"u8);
#pragma warning restore SCME0001

            return responseCreationOptions;
        };

        return agentEnabledChatOptions;
    }

    private static AgentReference CreateAgentReference(ProjectsAgentVersion agentVersion)
    {
        // If the version is null, empty, or whitespace, use "latest" as the default. This handles
        // cases where hosted agents (like MCP agents) may not have a version assigned.
        var version = string.IsNullOrWhiteSpace(agentVersion.Version) ? "latest" : agentVersion.Version;
        return new AgentReference(agentVersion.Name, version);
    }

    private static AgentEndpointInner BuildAgentEndpointInner(
        Uri agentEndpoint,
        AuthenticationTokenProvider credential,
        ProjectOpenAIClientOptions? clientOptions)
    {
        Throw.IfNull(agentEndpoint);
        Throw.IfNull(credential);

        var (agentName, projectRoot) = ParseAgentEndpoint(agentEndpoint);

        var perAgentOptions = clientOptions ?? new ProjectOpenAIClientOptions();
        perAgentOptions.Endpoint = agentEndpoint;
        perAgentOptions.AgentName = agentName;

        var authPolicy = new BearerTokenPolicy(credential, AzureAiResourceScope);
        var perAgentClient = new ProjectOpenAIClient(authPolicy, perAgentOptions);

        var chatClient = perAgentClient.GetProjectResponsesClient().AsIChatClient();

        // Materialize a project-level AIProjectClient from the parsed project root so
        // GetService<AIProjectClient>() returns non-null for all FoundryChatClient
        // construction modes. Project-level helpers (file upload, vector store create/delete)
        // depend on this. RBAC for those calls is at the project level; if the supplied
        // credential lacks project-scope permissions, the SDK surfaces a clean 401/403 at
        // call time. The four observable primitive ClientPipelineOptions properties are
        // propagated from the caller's per-agent options bag so test-injected transports and
        // explicit RetryPolicy / NetworkTimeout / UserAgentApplicationId reach the
        // project-level pipeline. Pipeline policies added via AddPolicy on the caller bag are
        // NOT propagated because ClientPipelineOptions does not publicly enumerate policies.
        var aiProjectClientOptions = new AIProjectClientOptions();
        if (clientOptions is not null)
        {
            if (clientOptions.RetryPolicy is not null)
            {
                aiProjectClientOptions.RetryPolicy = clientOptions.RetryPolicy;
            }
            if (clientOptions.NetworkTimeout is not null)
            {
                aiProjectClientOptions.NetworkTimeout = clientOptions.NetworkTimeout;
            }
            if (clientOptions.Transport is not null)
            {
                aiProjectClientOptions.Transport = clientOptions.Transport;
            }
            if (!string.IsNullOrEmpty(clientOptions.UserAgentApplicationId))
            {
                aiProjectClientOptions.UserAgentApplicationId = clientOptions.UserAgentApplicationId;
            }
        }
        var aiProjectClient = new AIProjectClient(projectRoot, credential, aiProjectClientOptions);

        return new AgentEndpointInner(chatClient, aiProjectClient, agentName);
    }

    private static AgentEndpointInner BuildAgentEndpointInnerFromProjectClient(
        AIProjectClient aiProjectClient,
        Uri agentEndpoint,
        ProjectOpenAIClientOptions? clientOptions)
    {
        Throw.IfNull(aiProjectClient);
        Throw.IfNull(agentEndpoint);

        var (agentName, _) = ParseAgentEndpoint(agentEndpoint);

        var perAgentOptions = clientOptions ?? new ProjectOpenAIClientOptions();
        perAgentOptions.Endpoint = agentEndpoint;
        perAgentOptions.AgentName = agentName;

        var chatClient = aiProjectClient.GetProjectOpenAIClient()
            .GetProjectResponsesClientForAgentEndpoint(agentName, options: perAgentOptions)
            .AsIChatClient();

        // Reuse the caller's AIProjectClient verbatim — no new pipeline is materialized.
        return new AgentEndpointInner(chatClient, aiProjectClient, agentName);
    }

    /// <summary>Best-effort registration of <see cref="AgentFrameworkUserAgentPolicy"/> via the MEAI <see cref="OpenAIRequestPolicies"/> hook with at-most-once dedup per pipeline.</summary>
    private static void TryRegisterAgentFrameworkUserAgentPolicy(IChatClient? innerClient)
    {
#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
        if (innerClient?.GetService<OpenAIRequestPolicies>() is { } policies)
        {
            // OpenAIRequestPoliciesReflection.AddPolicyIfMissing performs a check-then-add against
            // the private _entries collection on the OpenAIRequestPolicies instance, so the
            // policy is registered at most once even when many FoundryChatClient instances share
            // the same underlying chat client.
            OpenAIRequestPoliciesReflection.AddPolicyIfMissing(
                policies,
                AgentFrameworkUserAgentPolicy.Instance,
                PipelinePosition.PerCall);
        }
#pragma warning restore MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
    }

    /// <summary>
    /// Best-effort registration of <see cref="ServedModelPolicy"/> via the MEAI
    /// <see cref="OpenAIRequestPolicies"/> hook. The policy captures the
    /// <c>x-ms-served-model</c> response header from Azure OpenAI and writes it into
    /// <see cref="ServedModelScope"/> so the <see cref="GetResponseAsync"/> and
    /// <see cref="GetStreamingResponseAsync"/> overrides can overwrite
    /// <see cref="ChatResponse.ModelId"/> with the actual model snapshot.
    /// </summary>
    private static void TryRegisterServedModelPolicy(IChatClient? innerClient)
    {
#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
        if (innerClient?.GetService<OpenAIRequestPolicies>() is { } policies)
        {
            OpenAIRequestPoliciesReflection.AddPolicyIfMissing(
                policies,
                ServedModelPolicy.Instance,
                PipelinePosition.PerCall);
        }
#pragma warning restore MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
    }

    /// <summary>Default OAuth scope for the Azure AI resource. Matches the scope used by <c>Azure.AI.Extensions.OpenAI</c>'s internal authentication helper so the bearer token is accepted by the Foundry control plane.</summary>
    private const string AzureAiResourceScope = "https://ai.azure.com/.default";

    private readonly struct AgentEndpointInner
    {
        public AgentEndpointInner(IChatClient chatClient, AIProjectClient aiProjectClient, string agentName)
        {
            this.ChatClient = chatClient;
            this.AIProjectClient = aiProjectClient;
            this.AgentName = agentName;
        }

        public IChatClient ChatClient { get; }
        public AIProjectClient AIProjectClient { get; }
        public string AgentName { get; }
    }
}
