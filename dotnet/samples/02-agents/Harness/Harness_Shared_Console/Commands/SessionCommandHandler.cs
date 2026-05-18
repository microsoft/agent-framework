// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Agents.AI;

namespace Harness.Shared.Console.Commands;

/// <summary>
/// Handles <c>/session-export &lt;filename&gt;</c> and <c>/session-import &lt;filename&gt;</c>
/// commands for serializing the current session to a file and restoring a session from a file.
/// </summary>
public sealed class SessionCommandHandler : CommandHandler
{
    private readonly AIAgent _agent;

    /// <summary>
    /// Initializes a new instance of the <see cref="SessionCommandHandler"/> class.
    /// </summary>
    /// <param name="agent">The agent used for session serialization and deserialization.</param>
    public SessionCommandHandler(AIAgent agent)
    {
        this._agent = agent;
    }

    /// <inheritdoc/>
    public override string? GetHelpText() => "/session-export <file> | /session-import <file>";

    /// <inheritdoc/>
    public override async ValueTask<bool> TryHandleAsync(string input, AgentSession session, IUXStateDriver ux)
    {
        string command = input.Split(' ', 2)[0];

        if (command.Equals("/session-export", StringComparison.OrdinalIgnoreCase))
        {
            await this.HandleExportAsync(input, session, ux).ConfigureAwait(false);
            return true;
        }

        if (command.Equals("/session-import", StringComparison.OrdinalIgnoreCase))
        {
            await this.HandleImportAsync(input, ux).ConfigureAwait(false);
            return true;
        }

        return false;
    }

    private async Task HandleExportAsync(string input, AgentSession session, IUXStateDriver ux)
    {
        string[] parts = input.Split(' ', 2, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        if (parts.Length < 2)
        {
            await ux.WriteInfoLineAsync("Usage: /session-export <filename>").ConfigureAwait(false);
            return;
        }

        string filename = parts[1];
        try
        {
            JsonElement serialized = await this._agent.SerializeSessionAsync(session).ConfigureAwait(false);
            string json = JsonSerializer.Serialize(serialized);
            await File.WriteAllTextAsync(filename, json).ConfigureAwait(false);
            await ux.WriteInfoLineAsync($"Session exported to {filename}").ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            await ux.WriteInfoLineAsync($"Failed to export session to {filename}: {ex.Message}").ConfigureAwait(false);
        }
    }

    private async Task HandleImportAsync(string input, IUXStateDriver ux)
    {
        string[] parts = input.Split(' ', 2, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        if (parts.Length < 2)
        {
            await ux.WriteInfoLineAsync("Usage: /session-import <filename>").ConfigureAwait(false);
            return;
        }

        string filename = parts[1];
        try
        {
            string json = await File.ReadAllTextAsync(filename).ConfigureAwait(false);
            JsonElement element = JsonSerializer.Deserialize<JsonElement>(json);
            AgentSession newSession = await this._agent.DeserializeSessionAsync(element).ConfigureAwait(false);
            await ux.ReplaceSessionAsync(newSession).ConfigureAwait(false);
            await ux.WriteInfoLineAsync($"Session imported from {filename}").ConfigureAwait(false);
        }
        catch (FileNotFoundException)
        {
            await ux.WriteInfoLineAsync($"File not found: {filename}").ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            await ux.WriteInfoLineAsync($"Failed to import session from {filename}: {ex.Message}").ConfigureAwait(false);
        }
    }
}
