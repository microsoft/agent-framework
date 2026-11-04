// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel.Primitives;
using System.Text.Json;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

namespace Demo.ComputerUse;

/// <summary>
/// Enum for tracking the state of the simulated web search flow.
/// </summary>
internal enum SearchState
{
    Initial,        // Browser search page
    Typed,          // Text entered in search box
    PressedEnter    // Search submitted, showing results
}

/// <summary>
/// One action of a computer call batch, reduced to the fields this simulation needs.
/// </summary>
internal sealed record ComputerActionRequest(string Type, string? Text, IReadOnlyList<string> Keys);

internal static class ComputerUseUtil
{
    internal static async Task<Dictionary<string, string>> UploadScreenshotAssetsAsync(IHostedFileClient fileClient)
    {
        string assetsDir = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Assets");

        (string Key, string FileName)[] files =
        [
            ("browser_search", "cua_browser_search.jpg"),
            ("search_typed", "cua_search_typed.jpg"),
            ("search_results", "cua_search_results.jpg")
        ];

        Dictionary<string, string> screenshots = [];

        foreach ((string key, string fileName) in files)
        {
            HostedFileContent result = await fileClient.UploadAsync(
                Path.Combine(assetsDir, fileName),
                new HostedFileClientOptions { Purpose = "assistants" });
            screenshots[key] = result.FileId;
        }

        return screenshots;
    }

    internal static async Task DeleteScreenshotAssetsAsync(
        IHostedFileClient fileClient,
        Dictionary<string, string> screenshots)
    {
        foreach ((string key, string fileId) in screenshots)
        {
            try
            {
                await fileClient.DeleteAsync(fileId);
            }
            catch (Exception exception)
            {
                // Continue so one failed deletion does not leave every remaining sample asset behind.
                Console.Error.WriteLine($"Failed to delete screenshot '{key}' ({fileId}): {exception.Message}");
            }
        }
    }

    /// <summary>
    /// Reads the ordered actions of a computer call.
    /// </summary>
    /// <remarks>
    /// The OpenAI .NET SDK does not expose the GA <c>actions</c> batch as a typed property yet, so the call is
    /// re-serialized and the batch is read from its JSON. A preview call carries a single <c>action</c> instead.
    /// </remarks>
    internal static IReadOnlyList<ComputerActionRequest> GetActions(ComputerCallResponseItem computerCall)
    {
        using JsonDocument json = JsonDocument.Parse(ModelReaderWriter.Write(computerCall, ModelReaderWriterOptions.Json));

        if (json.RootElement.TryGetProperty("actions", out JsonElement actions) && actions.ValueKind == JsonValueKind.Array)
        {
            return [.. actions.EnumerateArray().Select(ToActionRequest)];
        }

        if (json.RootElement.TryGetProperty("action", out JsonElement action) && action.ValueKind == JsonValueKind.Object)
        {
            return [ToActionRequest(action)];
        }

        return [];
    }

    /// <summary>
    /// Simulates executing a computer action by advancing the state.
    /// </summary>
    internal static async Task<SearchState> ApplyAsync(ComputerActionRequest action, SearchState currentState)
    {
        if (action.Type == "wait")
        {
            await Task.Delay(TimeSpan.FromSeconds(1));
        }

        return action.Type switch
        {
            "click" when currentState == SearchState.Typed => SearchState.PressedEnter,
            "type" when action.Text is not null => SearchState.Typed,
            "keypress" when IsEnterKey(action) => SearchState.PressedEnter,
            _ => currentState
        };
    }

    /// <summary>
    /// Returns the key of the screenshot that shows the given state.
    /// </summary>
    internal static string GetScreenshotKey(SearchState state) => state switch
    {
        SearchState.PressedEnter => "search_results",
        SearchState.Typed => "search_typed",
        _ => "browser_search"
    };

    private static ComputerActionRequest ToActionRequest(JsonElement action)
    {
        string type = action.TryGetProperty("type", out JsonElement typeElement) ? typeElement.GetString() ?? string.Empty : string.Empty;
        string? text = action.TryGetProperty("text", out JsonElement textElement) ? textElement.GetString() : null;
        IReadOnlyList<string> keys = action.TryGetProperty("keys", out JsonElement keysElement) && keysElement.ValueKind == JsonValueKind.Array
            ? [.. keysElement.EnumerateArray().Select(k => k.GetString() ?? string.Empty)]
            : [];

        return new ComputerActionRequest(type, text, keys);
    }

    private static bool IsEnterKey(ComputerActionRequest action) =>
        action.Keys.Contains("Return", StringComparer.OrdinalIgnoreCase) ||
        action.Keys.Contains("Enter", StringComparer.OrdinalIgnoreCase);
}
