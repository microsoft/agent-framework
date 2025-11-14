// Copyright (c) Microsoft. All rights reserved.

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
    /// <summary>
    /// Load and convert screenshot images to base64 data URLs.
    /// </summary>
    internal static Dictionary<string, byte[]> LoadScreenshotAssets()
    {
        string baseDir = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Assets");

        ReadOnlySpan<(string key, string fileName)> screenshotFiles =
            [
                ("browser_search", "cua_browser_search.png"),
                ("search_typed", "cua_search_typed.png"),
                ("search_results", "cua_search_results.png")
            ];

        Dictionary<string, byte[]> screenshots = [];
        foreach (var (key, fileName) in screenshotFiles)
        {
            string fullPath = Path.GetFullPath(Path.Combine(baseDir, fileName));
            screenshots[key] = File.ReadAllBytes(fullPath);
        }

        return screenshots;
    }

    /// <summary>
    /// Process a computer action and simulate its execution.
    /// </summary>
    internal static (SearchState CurrentState, byte[] ImageBytes) HandleComputerActionAndTakeScreenshot(
        ComputerCallAction action,
        SearchState currentState,
        Dictionary<string, byte[]> screenshots)
    {
        Console.WriteLine($"Simulating the execution of computer action: {action.Kind}");

        SearchState newState = DetermineNextState(action, currentState);
        string imageKey = GetImageKey(newState);

        return (newState, screenshots[imageKey]);
    }

    private static SearchState DetermineNextState(ComputerCallAction action, SearchState currentState)
    {
        string actionType = action.Kind.ToString();

        if (actionType.Equals("type", StringComparison.OrdinalIgnoreCase) && action.TypeText is not null)
        {
            return SearchState.Typed;
        }

        if (IsEnterKeyAction(action, actionType))
        {
            Console.WriteLine("  -> Detected ENTER key press");
            return SearchState.PressedEnter;
        }

        if (actionType.Equals("click", StringComparison.OrdinalIgnoreCase) && currentState == SearchState.Typed)
        {
            Console.WriteLine("  -> Detected click after typing");
            return SearchState.PressedEnter;
        }

        return currentState;
    }

    private static bool IsEnterKeyAction(ComputerCallAction action, string actionType)
    {
        return (actionType.Equals("key", StringComparison.OrdinalIgnoreCase) ||
                actionType.Equals("keypress", StringComparison.OrdinalIgnoreCase)) &&
               action.KeyPressKeyCodes is not null &&
               (action.KeyPressKeyCodes.Contains("Return", StringComparer.OrdinalIgnoreCase) ||
                action.KeyPressKeyCodes.Contains("Enter", StringComparer.OrdinalIgnoreCase));
    }

    private static string GetImageKey(SearchState state) => state switch
    {
        SearchState.PressedEnter => "search_results",
        SearchState.Typed => "search_typed",
        _ => "browser_search"
    };
}
