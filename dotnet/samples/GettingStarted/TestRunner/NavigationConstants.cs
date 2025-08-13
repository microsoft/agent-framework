// Copyright (c) Microsoft. All rights reserved.

namespace GettingStarted.TestRunner;

/// <summary>
/// Contains string constants for navigation menus and actions to centralize UI text.
/// </summary>
public static class NavigationConstants
{
    /// <summary>
    /// Main menu navigation options.
    /// </summary>
    public static class MainMenu
    {
        public const string RunTests = "Run Tests";
        public const string ViewConfiguration = "View Configuration";
        public const string ManageSecrets = "Manage Secrets";
        public const string Exit = "Exit";
    }

    /// <summary>
    /// Configuration management menu options.
    /// </summary>
    public static class ConfigurationMenu
    {
        public const string Title = "[blue]Configuration Management[/]";
        public const string SelectPrompt = "[green]Select a configuration to update:[/]";
    }

    /// <summary>
    /// Configuration update actions.
    /// </summary>
    public static class ConfigurationActions
    {
        public const string SetNewValue = "Set new value";
        public const string RemoveCurrentValue = "Remove current value";
        public const string Cancel = "Cancel";
        public const string ActionPrompt = "[green]What would you like to do?[/]";
    }

    /// <summary>
    /// Status messages for configuration operations.
    /// </summary>
    public static class ConfigurationMessages
    {
        public const string UpdatedSuccessfully = "[green]✓ Configuration updated successfully![/]";
        public const string RemovedSuccessfully = "[green]✓ Configuration removed successfully![/]";
        public const string SavedSuccessfully = "[green]✓ Configuration saved successfully![/]";
        public const string NoValuesProvided = "[red]No configuration values provided[/]";
        public const string SettingUpConfiguration = "[blue]Setting up configuration using user secrets...[/]";
        public const string RestartNote = "[yellow]Note: You may need to restart the application for changes to take effect.[/]";
        public const string NotSet = "[dim]Not set[/]";
        public const string NoCurrentValue = "[dim]No current value set[/]";
    }

    /// <summary>
    /// Configuration key display formatting.
    /// </summary>
    public static class ConfigurationDisplay
    {
        public const string SetStatusIcon = "✓";
        public const string NotSetStatusIcon = "✗";
        public const string CurrentValuePrefix = " (Current: ";
        public const string NotSetSuffix = " (Not set)";
        public const string ClosingParenthesis = ")";
        public const string OptionalFieldIndicator = "[dim]○[/]";
        public const string OptionalSuffix = " (Optional)";
    }

    /// <summary>
    /// Test execution and folder navigation.
    /// </summary>
    public static class TestNavigation
    {
        public const string BackToFolderSelection = "Back to Folder Selection";
    }

    /// <summary>
    /// Common UI elements.
    /// </summary>
    public static class CommonUI
    {
        public const string PressAnyKeyToContinue = "[dim]Press any key to continue...[/]";
        public const string TestOutput = "Test Output";
        public const string Back = "Back";
    }
}
