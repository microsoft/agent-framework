// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using OpenAI.Files;
using OpenAI.Responses;

namespace Demo.ComputerUse;

/// <summary>
/// Tracks the simulated browser state during the computer use loop.
/// See the README for the full state machine and screenshot mapping.
/// </summary>
internal enum SearchState { Initial, Typed, PressedEnter }

internal static class ComputerUseUtil
{
    internal static async Task<Dictionary<string, string>> UploadScreenshotAssetsAsync(OpenAIFileClient fileClient)
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
            ClientResult<OpenAIFile> result = await fileClient.UploadFileAsync(
                Path.Combine(assetsDir, fileName), FileUploadPurpose.Assistants);
            screenshots[key] = result.Value.Id;
        }

        return screenshots;
    }

    internal static async Task DeleteScreenshotAssetsAsync(OpenAIFileClient fileClient, Dictionary<string, string> screenshots)
    {
        foreach (var (_, fileId) in screenshots)
        {
            await fileClient.DeleteFileAsync(fileId);
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
