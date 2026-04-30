// Copyright (c) Microsoft. All rights reserved.

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
    PressedEnter   // Enter key pressed, transitioning to results
}

internal static class ComputerUseUtil
{
    internal static async Task<Dictionary<string, string>> UploadScreenshotAssetsAsync(IHostedFileClient fileClient)
    {
        string assetsDir = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Assets");

        (string key, string fileName)[] files =
        [
            ("browser_search", "cua_browser_search.jpg"),
            ("search_typed", "cua_search_typed.jpg"),
            ("search_results", "cua_search_results.jpg")
        ];

        Dictionary<string, string> screenshots = [];

        foreach (var (key, fileName) in files)
        {
            HostedFileContent result = await fileClient.UploadAsync(
                Path.Combine(assetsDir, fileName), new HostedFileClientOptions() { Purpose = "assistants" });
            screenshots[key] = result.FileId;
        }

        return screenshots;
    }

    internal static async Task EnsureDeleteScreenshotAssetsAsync(IHostedFileClient fileClient, Dictionary<string, string> screenshots)
    {
        foreach (var (_, fileId) in screenshots)
        {
            try
            {
                await fileClient.DeleteAsync(fileId);
            }
            catch
            {
            }
        }
    }

    /// <summary>
    /// Simulates executing a computer action by advancing the state
    /// and returning the screenshot file ID for the new state.
    /// </summary>
    internal static async Task<(SearchState State, string FileId)> GetScreenshotAsync(
        ComputerCallAction action,
        SearchState currentState,
        Dictionary<string, string> screenshots)
    {
        if (action.Kind == ComputerCallActionKind.Wait)
        {
            await Task.Delay(TimeSpan.FromSeconds(5));
        }

        SearchState nextState = action.Kind switch
        {
            ComputerCallActionKind.Click when currentState == SearchState.Typed => SearchState.PressedEnter,
            ComputerCallActionKind.Type when action.TypeText is not null => SearchState.Typed,
            ComputerCallActionKind.KeyPress when IsEnterKey(action) => SearchState.PressedEnter,
            _ => currentState
        };

        string imageKey = nextState switch
        {
            SearchState.PressedEnter => "search_results",
            SearchState.Typed => "search_typed",
            _ => "browser_search"
        };

        return (nextState, screenshots[imageKey]);
    }

    private static bool IsEnterKey(ComputerCallAction action) =>
        action.KeyPressKeyCodes is not null &&
        (action.KeyPressKeyCodes.Contains("Return", StringComparer.OrdinalIgnoreCase) ||
         action.KeyPressKeyCodes.Contains("Enter", StringComparer.OrdinalIgnoreCase));
}
