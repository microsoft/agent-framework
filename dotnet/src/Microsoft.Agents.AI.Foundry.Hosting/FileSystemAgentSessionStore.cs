// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Buffers;
using System.Diagnostics.CodeAnalysis;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Provides a file-system backed implementation of <see cref="AgentSessionStore"/> that persists
/// the agent-framework's serialized <see cref="AgentSession"/> state for each (agent, conversation)
/// pair to disk. This complements Foundry storage (which owns conversation messages, agent
/// definitions, and threads) — it is not a replacement for it.
/// </summary>
/// <remarks>
/// <para>
/// The session JSON stored here is the AF runtime's own state (workflow checkpoint manager,
/// pending external requests, internal port state) that is required to resume an
/// <see cref="AgentSession"/> across HTTP requests or process restarts but is not part of
/// Foundry's data model.
/// </para>
/// <para>
/// When running in a Foundry hosted environment, sessions are stored under
/// <c>{$HOME}/.checkpoints</c> (the platform sets <c>HOME</c> to <c>/home/session</c> by
/// default). This is the only container directory that is writable and durably preserved
/// across requests for the lifetime of the session; the container's root filesystem is
/// read-only and paths outside <c>$HOME</c> may be cleared between requests. Locally,
/// sessions fall under <c>{cwd}/.checkpoints</c>. The session JSON produced when the agent
/// serializes the session already contains the workflow's in-memory checkpoint manager
/// state, so a single file per (agent, conversation) pair is sufficient to resume
/// long-running workflows across process restarts.
/// </para>
/// <para>
/// Files are written atomically via a temp-file + <see cref="File.Move(string, string, bool)"/>
/// rename so a partially-written file cannot be observed by a concurrent reader.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class FileSystemAgentSessionStore : AgentSessionStore
{
    /// <summary>
    /// The name of the environment variable whose value is the writable, durable session-data
    /// directory in a Foundry hosted container. The platform injects it (default
    /// <see cref="DefaultHostedSessionDataDirectory"/>).
    /// </summary>
    public const string SessionDataDirectoryEnvironmentVariable = "HOME";

    /// <summary>
    /// The default value of <see cref="SessionDataDirectoryEnvironmentVariable"/> used when the
    /// platform has not injected <c>HOME</c>. This is the only writable, durable location in a
    /// Foundry hosted container; the container's root filesystem is read-only.
    /// </summary>
    public const string DefaultHostedSessionDataDirectory = "/home/session";

    /// <summary>
    /// The directory name used for checkpoint files, appended under the hosted session-data
    /// directory (<c>$HOME</c>) or, locally, under the current working directory.
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
    /// <c>{$HOME}/.checkpoints</c> when running in a Foundry hosted environment (the platform
    /// sets <c>HOME</c> to <see cref="DefaultHostedSessionDataDirectory"/> by default), otherwise
    /// <see cref="LocalCheckpointDirectoryName"/> under the current working directory.
    /// </summary>
    /// <returns>A new <see cref="FileSystemAgentSessionStore"/> instance.</returns>
    public static FileSystemAgentSessionStore CreateDefault()
        => new(ResolveDefaultRootDirectory(
            FoundryEnvironment.IsHosted,
            Environment.GetEnvironmentVariable(SessionDataDirectoryEnvironmentVariable),
            Environment.CurrentDirectory));

    /// <summary>
    /// Resolves the default root directory for <see cref="CreateDefault"/>. Factored out so the
    /// hosted-vs-local path selection can be unit-tested without depending on the process-wide,
    /// statically-cached <c>FoundryEnvironment.IsHosted</c> value.
    /// </summary>
    /// <param name="isHosted">Whether the process is running in a Foundry hosted environment.</param>
    /// <param name="homeDirectory">The value of the <c>HOME</c> environment variable, if any.</param>
    /// <param name="currentDirectory">The current working directory, used for the local fallback.</param>
    /// <returns>The root directory under which session files are written.</returns>
    internal static string ResolveDefaultRootDirectory(bool isHosted, string? homeDirectory, string currentDirectory)
    {
        if (isHosted)
        {
            // In a Foundry hosted container only the session-state directory ($HOME, default
            // /home/session) is writable and durably preserved across requests. Writing under the
            // filesystem root (the previous "/.checkpoints" default) fails because the root
            // filesystem is read-only — see issue #6231. HOME is settable on the agent definition,
            // so fall back to the default when it is missing, blank, a filesystem root (e.g. "/"),
            // or otherwise unusable, to guarantee the store never lands directly under the root.
            string home = IsUsableHostedHomeDirectory(homeDirectory) ? homeDirectory! : DefaultHostedSessionDataDirectory;
            return Path.Combine(home, LocalCheckpointDirectoryName);
        }

        return Path.Combine(currentDirectory, LocalCheckpointDirectoryName);
    }

    /// <summary>
    /// Determines whether a hosted <c>HOME</c> value can safely root the session store. Rejects
    /// null/blank values, a filesystem root (e.g. <c>"/"</c> or a drive root, which would put the
    /// store back under the read-only container root and reintroduce issue #6231), and paths that
    /// cannot be normalized.
    /// </summary>
    private static bool IsUsableHostedHomeDirectory(string? homeDirectory)
    {
        if (string.IsNullOrWhiteSpace(homeDirectory))
        {
            return false;
        }

        try
        {
            string full = Path.GetFullPath(homeDirectory);
            return !string.Equals(full, Path.GetPathRoot(full), StringComparison.Ordinal);
        }
        catch (Exception ex) when (ex is ArgumentException or NotSupportedException or PathTooLongException)
        {
            return false;
        }
    }

    /// <inheritdoc/>
    public override async ValueTask SaveSessionAsync(AIAgent agent, string conversationId, AgentSession session, string? userId, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(agent);
        ArgumentException.ThrowIfNullOrWhiteSpace(conversationId);
        ArgumentNullException.ThrowIfNull(session);

        JsonElement serialized = await agent.SerializeSessionAsync(session, cancellationToken: cancellationToken).ConfigureAwait(false);

        string path = this.GetSessionPath(agent, conversationId, userId);

        // Each save writes to its own temp file before atomically renaming over the
        // destination. Last writer wins for the final file, but no reader can observe
        // a torn or partially-written JSON document.
        string tempPath = $"{path}.{Guid.NewGuid():N}.tmp";

        try
        {
            Directory.CreateDirectory(this.RootDirectory);

            string? parentDir = Path.GetDirectoryName(path);
            if (!string.IsNullOrEmpty(parentDir))
            {
                Directory.CreateDirectory(parentDir);
            }

            using (FileStream stream = new(tempPath, FileMode.Create, FileAccess.Write, FileShare.None))
            using (Utf8JsonWriter writer = new(stream))
            {
                serialized.WriteTo(writer);
            }

            File.Move(tempPath, path, overwrite: true);
        }
        catch (Exception ex)
        {
            try { File.Delete(tempPath); } catch { /* best-effort cleanup */ }

            // A non-writable session directory is fatal: the caller asked to persist the session
            // and we could not. Replace the opaque raw error (e.g. "Read-only file system :
            // '/.checkpoints'") with an actionable message — in a Foundry hosted container only
            // $HOME (default /home/session) is writable and durable. See issue #6231.
            if (ex is IOException or UnauthorizedAccessException)
            {
                throw new IOException(this.BuildNotWritableMessage(path), ex);
            }

            throw;
        }
    }

    private string BuildNotWritableMessage(string sessionFilePath) =>
        $"Failed to persist the agent session to '{sessionFilePath}'. The session store directory " +
        $"'{this.RootDirectory}' could not be created or written to. In a Foundry hosted container only the " +
        $"session-state directory referenced by the '{SessionDataDirectoryEnvironmentVariable}' environment " +
        $"variable (default '{DefaultHostedSessionDataDirectory}') is writable and durably preserved across " +
        "requests; the container's root filesystem is read-only and paths outside it may be cleared between " +
        $"requests. Use {nameof(FileSystemAgentSessionStore)}.{nameof(CreateDefault)}() (which targets that " +
        $"directory), construct the store with a path under it, or register a different {nameof(AgentSessionStore)} " +
        $"(for example {nameof(InMemoryAgentSessionStore)}) via AddFoundryResponses(agent, agentSessionStore).";

    /// <inheritdoc/>
    public override async ValueTask<AgentSession> GetSessionAsync(AIAgent agent, string conversationId, string? userId, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(agent);
        ArgumentException.ThrowIfNullOrWhiteSpace(conversationId);

        string path = this.GetSessionPath(agent, conversationId, userId);
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

    private string GetSessionPath(AIAgent agent, string conversationId, string? userId)
    {
        // Path layout uses self-describing, prefixed segments so every layer is unambiguous and a
        // collapsed layout can never be confused with a different layer (e.g. a user id can never
        // masquerade as an agent name):
        //
        //   {root}/a-{agent}/u-{userId}/c-{conversationId}.json
        //
        // - a-{agent}  buckets per hosted agent, because a single container hosts multiple keyed
        //              agents that must not collide on the same conversationId. (agent.Id is NOT
        //              used: it is regenerated on every startup for in-memory-defined agents.)
        // - u-{userId} partitions per end user (x-agent-user-id) for multi-tenant isolation. Present
        //              only when a user id was resolved; absent for local runs with no platform header.
        // - c-{conv}   the conversation/context key. {conversationId} is HostedConversationKey.Resolve's
        //              output (conversation_id, else the partition of previous_response_id / response id).
        //
        // The prefixes are constant literals applied AFTER sanitizing/validating each untrusted value,
        // so they can never themselves introduce path traversal.
        string dir = this.RootDirectory;

        if (!string.IsNullOrEmpty(agent.Name))
        {
            dir = Path.Combine(dir, "a-" + Sanitize(agent.Name!));
        }

        if (!string.IsNullOrWhiteSpace(userId))
        {
            // The user id is the platform-injected, untrusted partition key. Reject (do not sanitize)
            // anything that is not a single safe path component so a forged value cannot escape the root.
            ValidatePathSegment(userId!, "user id");
            dir = Path.Combine(dir, "u-" + Sanitize(userId!));
        }

        string path = Path.Combine(dir, "c-" + Sanitize(conversationId) + ".json");

        // Defense in depth: regardless of per-segment handling, the fully-resolved path must remain
        // under the storage root. Reject anything that escapes (CWE-22).
        string fullRoot = Path.GetFullPath(this.RootDirectory);
        string fullPath = Path.GetFullPath(path);
        string rootWithSeparator = fullRoot.EndsWith(Path.DirectorySeparatorChar.ToString(), StringComparison.Ordinal)
            ? fullRoot
            : fullRoot + Path.DirectorySeparatorChar;
        if (!fullPath.StartsWith(rootWithSeparator, StringComparison.Ordinal))
        {
            throw new InvalidOperationException(
                $"Refusing to resolve a session path outside of the storage root '{fullRoot}'.");
        }

        return path;
    }

    /// <summary>
    /// Validates that <paramref name="segment"/> is a single safe path component (CWE-22).
    /// </summary>
    /// <remarks>
    /// The value originates from caller-controlled or platform-injected fields (such as the
    /// <c>x-agent-user-id</c> partition key). It must be treated as an untrusted single path segment:
    /// path separators, drive letters, parent references and similar would otherwise let the resulting
    /// directory escape the configured storage root. We deliberately do not URL-decode the value (the
    /// hosting layer never decodes these ids before joining them, so forms such as <c>%2e%2e</c> are
    /// accepted as literal directory names), and we do not "sanitize" by stripping characters because
    /// that can introduce collisions between distinct ids — a non-conforming value is rejected outright.
    /// </remarks>
    private static void ValidatePathSegment(string segment, string kind)
    {
        // Reject any value that is not a single safe path component. This covers POSIX/Windows
        // separators, NUL bytes, drive letters, rooted paths, and all-dot segments (".", "..", "...").
        if (segment.IndexOf('/') >= 0
            || segment.IndexOf('\\') >= 0
            || segment.IndexOf('\0') >= 0
            || segment.Trim('.').Length == 0
            || Path.IsPathRooted(segment)
            || !string.IsNullOrEmpty(Path.GetPathRoot(segment)))
        {
            throw new InvalidOperationException($"Invalid {kind}: '{segment}'.");
        }
    }

    private static string Sanitize(string value)
    {
        // Percent-encode every character that is invalid in a filename, plus '%' itself
        // so the encoding is unambiguous. This is reversible and avoids the collision
        // hazard of a lossy character substitution (e.g. "foo/bar" and "foo_bar" sharing
        // a sanitized name).
        char[] invalid = Path.GetInvalidFileNameChars();

        int encodedLength = ComputeEncodedLength(value, invalid);

        // stackalloc is bounded so an externally-controlled length cannot crash the
        // hosting process with StackOverflowException.
        const int StackLimit = 512;
        string sanitized;
        if (encodedLength <= StackLimit)
        {
            Span<char> buffer = stackalloc char[encodedLength];
            SanitizeCore(value, invalid, buffer);
            sanitized = new string(buffer);
        }
        else
        {
            char[] rented = ArrayPool<char>.Shared.Rent(encodedLength);
            try
            {
                Span<char> buffer = rented.AsSpan(0, encodedLength);
                SanitizeCore(value, invalid, buffer);
                sanitized = new string(buffer);
            }
            finally
            {
                ArrayPool<char>.Shared.Return(rented);
            }
        }

        // '.' and '..' are valid filename characters but resolve to current/parent
        // directory when used as a bare path component. Windows additionally strips
        // trailing dots from filenames, so a segment like "..." would survive on disk
        // as "" and a partial-encode like "%2E.." would survive as "%2E". Encode every
        // dot in any all-dot segment so the result has no special meaning to the OS.
        if (sanitized.Length > 0 && IsAllDots(sanitized))
        {
            return string.Concat(Enumerable.Repeat("%2E", sanitized.Length));
        }

        return sanitized;
    }

    private static int ComputeEncodedLength(string value, char[] invalid)
    {
        int extra = 0;
        for (int i = 0; i < value.Length; i++)
        {
            char c = value[i];
            if (c == '%' || Array.IndexOf(invalid, c) >= 0)
            {
                extra += 2; // 1 char ('%' or invalid) becomes 3 chars ("%XX")
            }
        }
        return value.Length + extra;
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
        int j = 0;
        for (int i = 0; i < value.Length; i++)
        {
            char c = value[i];
            if (c == '%' || Array.IndexOf(invalid, c) >= 0)
            {
                buffer[j++] = '%';
                buffer[j++] = HexChar((c >> 4) & 0xF);
                buffer[j++] = HexChar(c & 0xF);
            }
            else
            {
                buffer[j++] = c;
            }
        }
    }

    private static char HexChar(int n) => (char)(n < 10 ? '0' + n : 'A' + n - 10);
}
