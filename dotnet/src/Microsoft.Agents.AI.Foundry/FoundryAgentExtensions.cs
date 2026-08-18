// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects.Agents;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;
using OpenAI.Files;
using OpenAI.VectorStores;

#pragma warning disable OPENAI001

namespace Microsoft.Agents.AI.Foundry;

/// <summary>
/// Foundry-specific extensions on <see cref="FoundryAgent"/>. Hosts the prompt-agent converter
/// plus thin forwarders that surface the file and vector-store helpers from the inner
/// <see cref="FoundryChatClient"/> at the agent level so callers do not need to drop down to
/// <c>agent.GetService&lt;FoundryChatClient&gt;().X()</c> for common workflows.
/// </summary>
public static class FoundryAgentExtensions
{
    /// <summary>
    /// Converts the supplied <see cref="FoundryAgent"/> into a <see cref="ProjectsAgentDefinition"/>
    /// ready to publish via <c>AgentAdministrationClient.CreateAgentVersionAsync</c>.
    /// </summary>
    /// <remarks>
    /// The Agent Endpoint construction mode (Mode 3) is not convertible because no local
    /// definition exists; conversion in that case throws <see cref="InvalidOperationException"/>.
    /// </remarks>
    /// <param name="agent">The Foundry agent to convert.</param>
    /// <param name="cancellationToken">A token that can cancel an internal server-side fetch when the agent was constructed from a bare <see cref="AgentReference"/>.</param>
    /// <returns>A <see cref="ProjectsAgentDefinition"/> suitable for publishing.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="agent"/> is <see langword="null"/>.</exception>
    /// <exception cref="InvalidOperationException">The agent's chat client is not a <see cref="FoundryChatClient"/>; the agent was constructed via the Agent Endpoint mode (Mode 3); no model id is set on the agent's <see cref="ChatOptions"/> for the Responses Agent mode (Mode 1); or the agent contains an <see cref="AITool"/> that cannot be converted to a <c>ResponseTool</c>.</exception>
    public static Task<ProjectsAgentDefinition> ToPromptAgentAsync(this FoundryAgent agent, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agent);

        var innerChatClient = agent.GetService<IChatClient>()
            ?? throw new InvalidOperationException(
                "ToPromptAgentAsync could not resolve the inner IChatClient on the FoundryAgent.");
        var chatOptions = agent.GetService<ChatOptions>();
        return FoundryPromptAgentConverter.ConvertAsync(innerChatClient, chatOptions, cancellationToken);
    }

    /// <summary>
    /// Uploads a file to the project. Thin forwarder to
    /// <see cref="FoundryChatClient.UploadFileAsync(string, FileUploadPurpose, CancellationToken)"/>
    /// on the agent's inner <see cref="FoundryChatClient"/>.
    /// </summary>
    /// <param name="agent">The Foundry agent whose inner chat client owns the upload pipeline.</param>
    /// <param name="filePath">Path to the file to upload.</param>
    /// <param name="purpose">The upload purpose (e.g. <see cref="FileUploadPurpose.Assistants"/>).</param>
    /// <param name="cancellationToken">A token that can cancel the upload.</param>
    /// <exception cref="ArgumentNullException"><paramref name="agent"/> is <see langword="null"/>.</exception>
    /// <exception cref="InvalidOperationException">The agent does not expose a <see cref="FoundryChatClient"/> via <see cref="AIAgent.GetService{TService}(object?)"/>.</exception>
    public static Task<OpenAIFile> UploadFileAsync(this FoundryAgent agent, string filePath, FileUploadPurpose purpose, CancellationToken cancellationToken = default)
        => RequireFoundryChatClient(agent).UploadFileAsync(filePath, purpose, cancellationToken);

    /// <summary>
    /// Deletes a previously uploaded file. Thin forwarder to
    /// <see cref="FoundryChatClient.DeleteFileAsync(string, CancellationToken)"/>.
    /// </summary>
    /// <param name="agent">The Foundry agent whose inner chat client owns the file pipeline.</param>
    /// <param name="fileId">The file id returned by <see cref="UploadFileAsync(FoundryAgent, string, FileUploadPurpose, CancellationToken)"/>.</param>
    /// <param name="cancellationToken">A token that can cancel the delete.</param>
    /// <exception cref="ArgumentNullException"><paramref name="agent"/> is <see langword="null"/>.</exception>
    /// <exception cref="InvalidOperationException">The agent does not expose a <see cref="FoundryChatClient"/>.</exception>
    public static Task<FileDeletionResult> DeleteFileAsync(this FoundryAgent agent, string fileId, CancellationToken cancellationToken = default)
        => RequireFoundryChatClient(agent).DeleteFileAsync(fileId, cancellationToken);

    /// <summary>
    /// Uploads the supplied files, creates a vector store containing them, and waits until the
    /// store leaves the in-progress state. Thin forwarder to
    /// <see cref="FoundryChatClient.CreateVectorStoreAsync(string, IEnumerable{string}, TimeSpan?, TimeSpan?, CancellationToken)"/>.
    /// </summary>
    /// <param name="agent">The Foundry agent whose inner chat client owns the file and vector-store pipeline.</param>
    /// <param name="name">The vector store name.</param>
    /// <param name="filePaths">Paths to files to upload and attach to the store.</param>
    /// <param name="expiresAfter">Optional last-active-at expiration window.</param>
    /// <param name="pollingTimeout">Optional upper bound on the wait for the vector store to leave the in-progress state. Defaults to 5 minutes; pass <see cref="Timeout.InfiniteTimeSpan"/> to disable.</param>
    /// <param name="cancellationToken">A token that can cancel the orchestration.</param>
    /// <exception cref="ArgumentNullException"><paramref name="agent"/> is <see langword="null"/>.</exception>
    /// <exception cref="InvalidOperationException">The agent does not expose a <see cref="FoundryChatClient"/>.</exception>
    /// <exception cref="TimeoutException">The vector store did not leave the in-progress state within <paramref name="pollingTimeout"/>.</exception>
    public static Task<VectorStore> CreateVectorStoreAsync(this FoundryAgent agent, string name, IEnumerable<string> filePaths, TimeSpan? expiresAfter = null, TimeSpan? pollingTimeout = null, CancellationToken cancellationToken = default)
        => RequireFoundryChatClient(agent).CreateVectorStoreAsync(name, filePaths, expiresAfter, pollingTimeout, cancellationToken);

    /// <summary>
    /// Deletes a vector store. Thin forwarder to
    /// <see cref="FoundryChatClient.DeleteVectorStoreAsync(string, CancellationToken)"/>.
    /// </summary>
    /// <param name="agent">The Foundry agent whose inner chat client owns the vector-store pipeline.</param>
    /// <param name="vectorStoreId">The vector store id.</param>
    /// <param name="cancellationToken">A token that can cancel the delete.</param>
    /// <exception cref="ArgumentNullException"><paramref name="agent"/> is <see langword="null"/>.</exception>
    /// <exception cref="InvalidOperationException">The agent does not expose a <see cref="FoundryChatClient"/>.</exception>
    public static Task<VectorStoreDeletionResult> DeleteVectorStoreAsync(this FoundryAgent agent, string vectorStoreId, CancellationToken cancellationToken = default)
        => RequireFoundryChatClient(agent).DeleteVectorStoreAsync(vectorStoreId, cancellationToken);

    private static FoundryChatClient RequireFoundryChatClient(FoundryAgent agent)
    {
        Throw.IfNull(agent);
        return agent.GetService<FoundryChatClient>()
            ?? throw new InvalidOperationException(
                "FoundryAgent does not expose a FoundryChatClient via GetService<FoundryChatClient>(). " +
                "File and vector-store helpers require the agent's inner chat client to be a FoundryChatClient.");
    }
}
