// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Buffers;
using System.Diagnostics.CodeAnalysis;
using System.IO;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Provides a file-system backed implementation of <see cref="AgentSessionStore"/> that persists
/// the serialized session JSON for each conversation to disk under a configurable root directory.
/// </summary>
/// <remarks>
/// <para>
/// When running in a Foundry hosted environment, sessions are stored under the well-known
/// <c>/.checkpoints</c> path; locally, they fall under <c>{cwd}/.checkpoints</c>. The session
/// JSON produced when the agent serializes the session already contains the workflow's
/// in-memory checkpoint manager state, so a single file per (agent, conversation) pair is
/// sufficient to resume long-running workflows across process restarts.
/// </para>
/// <para>
/// Files are written atomically via a temp-file + <see cref="File.Move(string, string, bool)"/>
/// rename so a partially-written file cannot be observed by a concurrent reader.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AIOpenAIResponses)]
public sealed class FileSystemAgentSessionStore : AgentSessionStore
{
    /// <summary>
    /// The well-known absolute path used when running inside a Foundry hosted environment.
    /// </summary>
    public const string HostedCheckpointDirectory = "/.checkpoints";

    /// <summary>
    /// The directory name used under the current working directory when running locally.
    /// </summary>
    public const string LocalCheckpointDirectoryName = ".checkpoints";

    /// <summary>
    /// Initializes a new instance of the <see cref="FileSystemAgentSessionStore"/> class
    /// that stores serialized sessions under <paramref name="rootDirectory"/>.
    /// </summary>
    /// <param name="rootDirectory">
    /// The absolute or relative directory where session files will be written.
    /// The directory is created on first write if it does not already exist.
    /// </param>
    public FileSystemAgentSessionStore(string rootDirectory)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(rootDirectory);
        this.RootDirectory = Path.GetFullPath(rootDirectory);
    }

    /// <summary>
    /// Gets the root directory under which session files are written.
    /// </summary>
    public string RootDirectory { get; }

    /// <summary>
    /// Creates a <see cref="FileSystemAgentSessionStore"/> rooted at the default location:
    /// <see cref="HostedCheckpointDirectory"/> when running in a Foundry hosted environment,
    /// otherwise <see cref="LocalCheckpointDirectoryName"/> under the current working directory.
    /// </summary>
    /// <returns>A new <see cref="FileSystemAgentSessionStore"/> instance.</returns>
    public static FileSystemAgentSessionStore CreateDefault()
    {
        string root = FoundryEnvironment.IsHosted
            ? HostedCheckpointDirectory
            : Path.Combine(Environment.CurrentDirectory, LocalCheckpointDirectoryName);
        return new FileSystemAgentSessionStore(root);
    }

    /// <inheritdoc/>
    public override async ValueTask SaveSessionAsync(AIAgent agent, string conversationId, AgentSession session, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(agent);
        ArgumentException.ThrowIfNullOrWhiteSpace(conversationId);
        ArgumentNullException.ThrowIfNull(session);

        JsonElement serialized = await agent.SerializeSessionAsync(session, cancellationToken: cancellationToken).ConfigureAwait(false);

        Directory.CreateDirectory(this.RootDirectory);

        string path = this.GetSessionPath(agent, conversationId);
        string? parentDir = Path.GetDirectoryName(path);
        if (!string.IsNullOrEmpty(parentDir))
        {
            Directory.CreateDirectory(parentDir);
        }

        // Each save writes to its own temp file before atomically renaming over the
        // destination. Last writer wins for the final file, but no reader can observe
        // a torn or partially-written JSON document.
        string tempPath = $"{path}.{Guid.NewGuid():N}.tmp";

        try
        {
            using (FileStream stream = new(tempPath, FileMode.Create, FileAccess.Write, FileShare.None))
            using (Utf8JsonWriter writer = new(stream))
            {
                serialized.WriteTo(writer);
            }

            File.Move(tempPath, path, overwrite: true);
        }
        catch
        {
            try { File.Delete(tempPath); } catch { /* best-effort cleanup */ }
            throw;
        }
    }

    /// <inheritdoc/>
    public override async ValueTask<AgentSession> GetSessionAsync(AIAgent agent, string conversationId, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(agent);
        ArgumentException.ThrowIfNullOrWhiteSpace(conversationId);

        string path = this.GetSessionPath(agent, conversationId);
        if (!File.Exists(path))
        {
            return await agent.CreateSessionAsync(cancellationToken).ConfigureAwait(false);
        }

        byte[] bytes = await File.ReadAllBytesAsync(path, cancellationToken).ConfigureAwait(false);
        if (bytes.Length == 0)
        {
            return await agent.CreateSessionAsync(cancellationToken).ConfigureAwait(false);
        }

        // Parse and clone so the document buffer can be released.
        using JsonDocument document = JsonDocument.Parse(bytes);
        JsonElement element = document.RootElement.Clone();
        return await agent.DeserializeSessionAsync(element, cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    private string GetSessionPath(AIAgent agent, string conversationId)
    {
        // When agent.Name is set we bucket sessions into a per-agent subdirectory so
        // multiple keyed agents sharing a single in-process default store cannot
        // collide on the same conversationId. agent.Id is intentionally NOT used
        // because it is regenerated on every startup for in-memory-defined agents.
        string fileName = $"{Sanitize(conversationId)}.json";
        if (string.IsNullOrEmpty(agent.Name))
        {
            return Path.Combine(this.RootDirectory, fileName);
        }

        string agentDir = Path.Combine(this.RootDirectory, Sanitize(agent.Name!));
        return Path.Combine(agentDir, fileName);
    }

    private static string Sanitize(string value)
    {
        // stackalloc is bounded so an externally-controlled length cannot crash the
        // hosting process with StackOverflowException.
        const int StackLimit = 256;
        char[] invalid = Path.GetInvalidFileNameChars();

        string sanitized;
        if (value.Length <= StackLimit)
        {
            Span<char> buffer = stackalloc char[value.Length];
            SanitizeCore(value, invalid, buffer);
            sanitized = new string(buffer);
        }
        else
        {
            char[] rented = ArrayPool<char>.Shared.Rent(value.Length);
            try
            {
                Span<char> buffer = rented.AsSpan(0, value.Length);
                SanitizeCore(value, invalid, buffer);
                sanitized = new string(buffer);
            }
            finally
            {
                ArrayPool<char>.Shared.Return(rented);
            }
        }

        // Path.GetInvalidFileNameChars() on Linux only contains NUL and '/', so the
        // segments "." and ".." would otherwise pass through and could resolve to the
        // current/parent directory when used as a bare path component (e.g. agent.Name).
        // Neutralize any segment composed entirely of dots so the result can never escape
        // its parent directory.
        if (sanitized.Length > 0 && IsAllDots(sanitized))
        {
            return new string('_', sanitized.Length);
        }

        return sanitized;
    }

    private static bool IsAllDots(string value)
    {
        for (int i = 0; i < value.Length; i++)
        {
            if (value[i] != '.')
            {
                return false;
            }
        }

        return true;
    }

    private static void SanitizeCore(string value, char[] invalid, Span<char> buffer)
    {
        for (int i = 0; i < value.Length; i++)
        {
            char c = value[i];
            buffer[i] = Array.IndexOf(invalid, c) >= 0 ? '_' : c;
        }
    }
}
