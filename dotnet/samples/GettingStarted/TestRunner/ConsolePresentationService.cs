// Copyright (c) Microsoft. All rights reserved.

using Spectre.Console;

namespace GettingStarted.TestRunner;

/// <summary>
/// Console presentation service for the test runner, handling all UI interactions.
/// </summary>
public class ConsolePresentationService
{
    private static readonly char[] SpaceSeparator = { ' ' };
    private readonly TestDiscoveryService _discoveryService;
    private readonly ConfigurationManager _configurationManager;
    private readonly TestExecutionService _executionService;

    public ConsolePresentationService(
        TestDiscoveryService discoveryService,
        ConfigurationManager configurationManager,
        TestExecutionService executionService)
    {
        this._discoveryService = discoveryService;
        this._configurationManager = configurationManager;
        this._executionService = executionService;
    }

    /// <summary>
    /// Runs the interactive console interface.
    /// </summary>
    public async Task<int> RunInteractiveAsync()
    {
        // Validate configuration first
        var validationResult = this._configurationManager.ValidateConfiguration();
        if (!validationResult.IsValid)
        {
            AnsiConsole.MarkupLine("[yellow]⚠ Missing configuration detected[/]");

            foreach (var config in validationResult.MissingConfigurations)
            {
                AnsiConsole.MarkupLine($"[red]✗ Missing: {config.FriendlyName} ({config.Key})[/]");
            }

            var setupConfig = AnsiConsole.Confirm("Would you like to set up the missing configuration now?");
            if (setupConfig)
            {
                var success = await this.SetupMissingConfigurationAsync(validationResult.MissingConfigurations);
                if (!success)
                {
                    AnsiConsole.MarkupLine("[red]Configuration setup failed. Please set up your configuration manually.[/]");
                    return 1;
                }
            }
            else
            {
                AnsiConsole.MarkupLine("[red]Configuration validation failed. Please set up your configuration first.[/]");
                return 1;
            }
        }
        else
        {
            AnsiConsole.MarkupLine("[green]✓ All required configuration is present[/]");
        }

        while (true)
        {
            // Clear the screen to ensure clean display when returning from submenus
            Console.Clear();
            ShowWelcome();

            var choice = ShowMainMenu();

            switch (choice)
            {
                case var _ when choice == NavigationConstants.MainMenu.RunSamples:
                    await this.RunSamplesMenuAsync();
                    break;
                case var _ when choice == NavigationConstants.MainMenu.Configuration:
                    await this.ConfigurationMenuAsync();
                    break;
                case var _ when choice == NavigationConstants.MainMenu.Exit:
                    return 0;
            }
        }
    }

    /// <summary>
    /// Runs a specific test using a filter.
    /// </summary>
    public async Task<int> RunTestAsync(string filter)
    {
        AnsiConsole.MarkupLine($"[blue]Running test with filter: {filter}[/]");

        var result = await this._executionService.ExecuteTestAsync(filter);

        if (result.Success)
        {
            AnsiConsole.MarkupLine("[green]✓ Test completed successfully[/]");
            if (!string.IsNullOrEmpty(result.Output))
            {
                AnsiConsole.WriteLine(result.Output);
            }
            return 0;
        }

        AnsiConsole.MarkupLine("[red]✗ Test failed[/]");
        if (!string.IsNullOrEmpty(result.Error))
        {
            AnsiConsole.MarkupLine($"[red]Error: {result.Error.EscapeMarkup()}[/]");
        }
        if (!string.IsNullOrEmpty(result.Output))
        {
            AnsiConsole.WriteLine(result.Output);
        }
        return result.ExitCode;
    }

    /// <summary>
    /// Shows the welcome message.
    /// </summary>
    private static void ShowWelcome()
    {
        var rule = new Rule("[blue]Microsoft Agent Framework - Getting Started Test Runner[/]");
        rule.Justification = Justify.Center;
        AnsiConsole.Write(rule);

        AnsiConsole.WriteLine();
        AnsiConsole.MarkupLine("[dim]Interactive test runner for Agent Framework samples[/]");
        AnsiConsole.WriteLine();
    }

    /// <summary>
    /// Shows the main menu and returns the user's choice.
    /// </summary>
    private static string ShowMainMenu()
    {
        var selectionPrompt = new SelectionPrompt<string>()
            .Title("[green]Main Menu[/]")
            .HighlightStyle(new Style().Foreground(Color.Yellow))
            .AddChoices(
                NavigationConstants.MainMenu.Exit,
                NavigationConstants.MainMenu.RunSamples,
                NavigationConstants.MainMenu.Configuration);

        return AnsiConsole.Prompt(selectionPrompt);
    }

    /// <summary>
    /// Handles the sample running menu.
    /// </summary>
    private async Task RunSamplesMenuAsync()
    {
        while (true)
        {
            // Clear the screen to ensure clean display when returning from submenus
            Console.Clear();

            var folders = this._discoveryService.DiscoverTestFolders();

            if (folders.Count == 0)
            {
                AnsiConsole.MarkupLine("[red]No sample category found[/]");
                return;
            }

            var folderChoice = ShowInteractiveMenuWithDescriptions(
                "Select Sample Category:",
                folders,
                f => f.Name,
                f => BuildHierarchicalDescription(f),
                NavigationConstants.CommonUI.Back,
                minDescriptionHeight: 9,
                backDescription: "Getting Started with Agent Framework: Step-by-step tutorial examples that demonstrate the core functionality of the Microsoft Agent Framework. Each sample builds upon previous concepts, providing a progressive learning path from basic agent creation to advanced features like function tools, file handling, and telemetry. These examples serve as the foundation for understanding how to create, configure, and interact with AI agents using various providers and capabilities.");

            if (folderChoice == NavigationConstants.CommonUI.Back)
            {
                return;
            }

            var selectedFolder = folders.First(f => f.Name == folderChoice);
            await this.ShowFolderMenuAsync(selectedFolder);
        }
    }

    /// <summary>
    /// Shows the menu for a specific test folder.
    /// </summary>
    private async Task ShowFolderMenuAsync(TestFolder folder)
    {
        while (true)
        {
            var choice = ShowInteractiveMenuWithDescriptions(
                $"Samples in {folder.Name}:",
                folder.Classes,
                c => c.Name,
                c => BuildHierarchicalDescription(folder, c),
                NavigationConstants.CommonUI.Back,
                minDescriptionHeight: 12,
                backDescription: BuildHierarchicalDescription(folder));

            if (choice == NavigationConstants.CommonUI.Back)
            {
                return;
            }

            var testClass = folder.Classes.First(c => c.Name == choice);
            await this.ShowClassMenuAsync(testClass, folder);
        }
    }

    /// <summary>
    /// Shows the menu for a specific test class with flattened test method selection and hierarchical context.
    /// </summary>
    private async Task ShowClassMenuAsync(TestClass testClass, TestFolder folder)
    {
        while (true)
        {
            // Create a list of menu items with their descriptions
            var menuItems = new List<(string Display, string Description)>();

            // Add all test methods (Facts and individual Theory cases) at the same level
            foreach (var method in testClass.Methods)
            {
                if (!method.IsTheory || method.TheoryData.Count == 0)
                {
                    // Simple fact test or theory without data - add as single method
                    var description = BuildHierarchicalDescription(folder, testClass, method);
                    menuItems.Add((method.Name, description));
                }
                else
                {
                    // Theory with data - add each theory case as individual test
                    foreach (var theoryCase in method.TheoryData)
                    {
                        var description = BuildHierarchicalDescription(folder, testClass, method);
                        menuItems.Add(($"{method.Name} ({theoryCase.DisplayName})", description));
                    }
                }
            }

            var choice = ShowInteractiveMenuWithDescriptions(
                $"Samples in {testClass.Name}:",
                menuItems,
                item => item.Display,
                item => item.Description,
                "Back",
                minDescriptionHeight: 12,
                backDescription: BuildHierarchicalDescription(folder, testClass));

            if (choice == "Back")
            {
                return;
            }

            // Execute the selected test
            await this.ExecuteSelectedTestAsync(testClass, choice);
        }
    }

    /// <summary>
    /// Executes the selected test based on the user's choice.
    /// </summary>
    private async Task ExecuteSelectedTestAsync(TestClass testClass, string choice)
    {
        // Check if it's a theory case (contains parentheses)
        if (choice.Contains('(') && choice.Contains(')'))
        {
            // Extract method name and theory case display name
            var openParen = choice.IndexOf('(');
            var methodName = choice.Substring(0, openParen).Trim();
            var theoryDisplayName = choice.Substring(openParen + 1, choice.Length - openParen - 2);

            var method = testClass.Methods.First(m => m.Name == methodName);
            var theoryCase = method.TheoryData.First(t => t.DisplayName == theoryDisplayName);
            var filter = TestExecutionService.GenerateTheoryFilter(method, theoryCase);
            await this.ExecuteTestWithResultAsync(filter);
        }
        else
        {
            // Simple fact test or theory without data
            var method = testClass.Methods.First(m => m.Name == choice);
            var filter = TestExecutionService.GenerateMethodFilter(method);
            await this.ExecuteTestWithResultAsync(filter);
        }
    }

    /// <summary>
    /// Executes a test and shows the result.
    /// </summary>
    private async Task ExecuteTestWithResultAsync(string filter)
    {
        var result = await this._executionService.ExecuteTestAsync(filter);

        if (result.Success)
        {
            AnsiConsole.MarkupLine("[green]✓ Test completed successfully[/]");
        }
        else
        {
            AnsiConsole.MarkupLine("[red]✗ Test failed[/]");
            if (!string.IsNullOrEmpty(result.Error))
            {
                AnsiConsole.MarkupLine($"[red]Error: {result.Error.EscapeMarkup()}[/]");
            }
        }

        if (!string.IsNullOrEmpty(result.Output))
        {
            // Escape markup characters to prevent parsing errors with file paths
            var escapedOutput = result.Output.EscapeMarkup();
            var panel = new Panel(escapedOutput)
                .Header(NavigationConstants.CommonUI.TestOutput)
                .Border(BoxBorder.Rounded);
            AnsiConsole.Write(panel);
        }

        AnsiConsole.MarkupLine(NavigationConstants.CommonUI.PressAnyKeyToContinue);
        Console.ReadKey();
    }

    /// <summary>
    /// Handles configuration setup.
    /// </summary>
    private async Task ConfigurationMenuAsync()
    {
        await this.ManageConfigurationAsync();
    }

    /// <summary>
    /// Shows an interactive menu with dynamic descriptions that update based on the currently highlighted item.
    /// </summary>
    private static string ShowInteractiveMenuWithDescriptions<T>(
        string? title,
        IEnumerable<T> items,
        Func<T, string> displaySelector,
        Func<T, string> descriptionSelector,
        string? backOption = null,
        int minDescriptionHeight = 6,
        string? backDescription = null)
    {
        var itemList = items.ToList();
        var choices = new List<string>();

        if (!string.IsNullOrEmpty(backOption))
        {
            choices.Add(backOption);
        }

        choices.AddRange(itemList.Select(displaySelector));

        var currentIndex = 0;
        var maxIndex = choices.Count - 1;

        while (true)
        {
            Console.Clear();

            if (!string.IsNullOrEmpty(title))
            {
                // Show title
                AnsiConsole.MarkupLine($"[green]{title}[/]");
                AnsiConsole.WriteLine();
            }

            // Show description for current selection
            string description = string.Empty;
            if (currentIndex == 0 && !string.IsNullOrEmpty(backOption))
            {
                description = backDescription ?? NavigationConstants.CommonUI.BackDescription;
            }
            else
            {
                var itemIndex = !string.IsNullOrEmpty(backOption) ? currentIndex - 1 : currentIndex;
                if (itemIndex >= 0 && itemIndex < itemList.Count)
                {
                    description = descriptionSelector(itemList[itemIndex]);
                }
            }

            // Always show a panel with fixed content height, regardless of original content
            var panel = new Panel(description ?? NavigationConstants.CommonUI.NoDescriptionAvailable)
            {
                Height = minDescriptionHeight,
                Expand = true
            }
            .Header("[bold]Description[/]")
            .Border(BoxBorder.Rounded)
            .BorderColor(Color.Blue);

            AnsiConsole.Write(panel);
            AnsiConsole.WriteLine();

            // Show menu choices
            for (int i = 0; i < choices.Count; i++)
            {
                var prefix = i == currentIndex ? "> " : "  ";
                var style = i == currentIndex ? "[bold yellow]" : "";
                var endStyle = i == currentIndex ? "[/]" : "";
                AnsiConsole.MarkupLine($"{style}{prefix}{choices[i]}{endStyle}");
            }

            // Handle input
            var key = Console.ReadKey(true);
            switch (key.Key)
            {
                case ConsoleKey.UpArrow:
                    currentIndex = currentIndex > 0 ? currentIndex - 1 : maxIndex;
                    break;
                case ConsoleKey.DownArrow:
                    currentIndex = currentIndex < maxIndex ? currentIndex + 1 : 0;
                    break;
                case ConsoleKey.Enter:
                    return choices[currentIndex];
                case ConsoleKey.Escape:
                    return backOption ?? choices[0];
            }
        }
    }

    /// <summary>
    /// Builds a hierarchical description showing folder, class, and method context.
    /// </summary>
    private static string BuildHierarchicalDescription(TestFolder folder, TestClass? testClass = null, TestMethod? method = null)
    {
        var parts = new List<string>();

        // Add folder description (top level)
        if (!string.IsNullOrEmpty(folder.Description))
        {
            parts.Add($"[dim]{folder.Name}:[/] {folder.Description}");
        }

        // Add class description (second level)
        if (!string.IsNullOrEmpty(testClass?.Description))
        {
            parts.Add($"[dim]{testClass.Name}:[/] {testClass.Description}");
        }

        // Add method description (bottom level)
        if (!string.IsNullOrEmpty(method?.Description))
        {
            parts.Add($"[dim]{method.Name}:[/] {method.Description}");
        }

        if (parts.Count == 0)
        {
            return NavigationConstants.CommonUI.NoDescriptionAvailable;
        }

        return string.Join("\n\n", parts);
    }

    /// <summary>
    /// Sets up missing configuration interactively.
    /// </summary>
    private async Task<bool> SetupMissingConfigurationAsync(List<ConfigurationMissingInfoResult> missingConfigs)
    {
        AnsiConsole.MarkupLine(NavigationConstants.ConfigurationMessages.SettingUpConfiguration);

        var configValues = new Dictionary<string, string>();

        foreach (var configInfo in missingConfigs)
        {
            var value = this.PromptForConfigValue(configInfo.Key);
            if (!string.IsNullOrEmpty(value))
            {
                configValues[configInfo.Key] = value;
            }
        }

        if (configValues.Count == 0)
        {
            AnsiConsole.MarkupLine(NavigationConstants.ConfigurationMessages.NoValuesProvided);
            return false;
        }

        var result = await this._configurationManager.SetupConfigurationAsync(configValues);
        if (result.Success)
        {
            AnsiConsole.MarkupLine(NavigationConstants.ConfigurationMessages.SavedSuccessfully);
            AnsiConsole.MarkupLine(NavigationConstants.ConfigurationMessages.RestartNote);
            return true;
        }

        AnsiConsole.MarkupLine("[red]Configuration setup failed. Please set up your configuration manually.[/]");
        foreach (var errorMessage in result.ErrorMessages)
        {
            AnsiConsole.MarkupLine($"[red]Failed to set {errorMessage}[/]");
        }
        return false;
    }

    /// <summary>
    /// Interactively manages all configuration settings (add/update/remove).
    /// </summary>
    private async Task<bool> ManageConfigurationAsync()
    {
        while (true)
        {
            AnsiConsole.MarkupLine(NavigationConstants.ConfigurationMenu.Title);
            AnsiConsole.WriteLine();

            var allConfigKeys = this._configurationManager.GetAllConfigurationKeys();
            var choices = new List<string>();

            foreach (var keyInfo in allConfigKeys)
            {
                // Converted to switch expression
                string statusIcon = (keyInfo.HasValue, keyInfo.IsRequired) switch
                {
                    (true, _) => NavigationConstants.ConfigurationDisplay.SetStatusIcon,
                    (false, true) => NavigationConstants.ConfigurationDisplay.NotSetStatusIcon,
                    _ => NavigationConstants.ConfigurationDisplay.OptionalFieldIndicator
                };

                var displayValue = keyInfo.HasValue
                    ? $"{NavigationConstants.ConfigurationDisplay.CurrentValuePrefix}{keyInfo.CurrentValue}{NavigationConstants.ConfigurationDisplay.ClosingParenthesis}"
                    : (keyInfo.IsRequired ? NavigationConstants.ConfigurationDisplay.NotSetSuffix : NavigationConstants.ConfigurationDisplay.OptionalSuffix);

                choices.Add($"{statusIcon} {keyInfo.Key}{displayValue}");
            }

            choices.Add(NavigationConstants.CommonUI.Back);

            var choice = AnsiConsole.Prompt(
                new SelectionPrompt<string>()
                    .Title(NavigationConstants.ConfigurationMenu.SelectPrompt)
                    .HighlightStyle(new Style().Foreground(Color.Yellow))
                    .AddChoices(choices));

            if (choice == NavigationConstants.CommonUI.Back)
            {
                return true;
            }

            // Extract the config key from the choice
            var configKey = ExtractConfigKeyFromChoice(choice, [.. allConfigKeys.Select(k => k.Key)]);

            // Update the configuration and continue the loop regardless of result
            await this.UpdateSingleConfigurationAsync(configKey);

            // Clear the screen for the next iteration
            AnsiConsole.Clear();
        }
    }

    /// <summary>
    /// Updates a single configuration value interactively.
    /// </summary>
    private async Task<bool> UpdateSingleConfigurationAsync(string configKey)
    {
        var keyInfo = this._configurationManager.GetAllConfigurationKeys().FirstOrDefault(k => k.Key == configKey);
        if (keyInfo == null)
        {
            return false;
        }

        AnsiConsole.MarkupLine($"[blue]Updating: {configKey}[/]");

        if (keyInfo.HasValue)
        {
            AnsiConsole.MarkupLine($"[dim]Current value: {keyInfo.CurrentValue}[/]");
        }
        else
        {
            AnsiConsole.MarkupLine(NavigationConstants.ConfigurationMessages.NoCurrentValue);
        }

        var actions = new List<string> { NavigationConstants.ConfigurationActions.SetNewValue };

        if (keyInfo.HasValue)
        {
            actions.Add(NavigationConstants.ConfigurationActions.RemoveCurrentValue);
        }

        actions.Add(NavigationConstants.ConfigurationActions.Cancel);

        var action = AnsiConsole.Prompt(
            new SelectionPrompt<string>()
                .Title(NavigationConstants.ConfigurationActions.ActionPrompt)
                .AddChoices(actions));

        switch (action)
        {
            case var _ when action == NavigationConstants.ConfigurationActions.SetNewValue:
                var existingValue = keyInfo.HasValue && !keyInfo.IsSecret ? keyInfo.CurrentValue : null;
                var newValue = this.PromptForConfigValue(configKey, existingValue);
                if (!string.IsNullOrEmpty(newValue))
                {
                    var success = await this._configurationManager.UpdateConfigurationValueAsync(configKey, newValue);
                    if (success)
                    {
                        AnsiConsole.MarkupLine(NavigationConstants.ConfigurationMessages.UpdatedSuccessfully);
                        return true;
                    }
                }
                return false;

            case var _ when action == NavigationConstants.ConfigurationActions.RemoveCurrentValue:
                var removed = await this._configurationManager.RemoveConfigurationValueAsync(configKey);
                if (removed)
                {
                    AnsiConsole.MarkupLine(NavigationConstants.ConfigurationMessages.RemovedSuccessfully);
                    return true;
                }
                return false;

            case var _ when action == NavigationConstants.ConfigurationActions.Cancel:
                return true;

            default:
                return false;
        }
    }

    /// <summary>
    /// Prompts the user for a configuration value with an optional current value as default.
    /// </summary>
    private string PromptForConfigValue(string configKey, string? currentValue = null)
    {
        var configInfo = this._configurationManager.GetConfigurationKeyInfo(configKey);
        var isOptional = !configInfo.IsRequired;

        // Build prompt text with current value display
        string promptText;
        string? formatedValue = (configInfo.IsSecret) ? MaskSecret(currentValue) : currentValue;

        // Show detailed description as contextual help if available
        if (!string.IsNullOrEmpty(configInfo.DetailedDescription))
        {
            AnsiConsole.WriteLine();
            AnsiConsole.MarkupLine($"[white]{configInfo.DetailedDescription}[/]");
        }

        promptText = $"[blue]Enter {configInfo.FriendlyName}:[/]";
        var prompt = new TextPrompt<string?>(promptText);

        // Configure prompt based on attributes
        if (configInfo.IsSecret)
        {
            prompt.PromptStyle("red").Secret();
        }

        if (isOptional)
        {
            prompt.AllowEmpty();
        }

        // Set default value if provided
        if (!string.IsNullOrEmpty(formatedValue))
        {
            // For secrets, allow empty input to keep current value
            prompt.DefaultValue(formatedValue);
            AnsiConsole.MarkupLine("[dim]Press Enter to keep current value, or enter a new value[/]");
        }

        var userInput = AnsiConsole.Prompt(prompt);

        // If user pressed Enter for a secret with current value, return the current value
        if (configInfo.IsSecret && string.IsNullOrWhiteSpace(userInput) && !string.IsNullOrEmpty(currentValue))
        {
            return currentValue!;
        }

        return userInput ?? string.Empty;
    }

    /// <summary>
    /// Masks a secret value for display.
    /// </summary>
    private static string? MaskSecret(string? value)
    {
        if (string.IsNullOrEmpty(value))
        {
            return null;
        }

        if (value.Length <= 4)
        {
            return new string('*', value.Length);
        }

#if NET8_0_OR_GREATER
        return string.Concat(value.AsSpan(0, 2), new string('*', value.Length - 4), value.AsSpan(value.Length - 2));
#else
        return value.Substring(0, 2) + new string('*', value.Length - 4) + value.Substring(value.Length - 2);
#endif
    }

    /// <summary>
    /// Extracts the configuration key from a menu choice string.
    /// </summary>
    private static string ExtractConfigKeyFromChoice(string choice, List<string> allConfigKeys)
    {
        // Try to find the key by checking if the choice contains the key
        foreach (var key in allConfigKeys)
        {
            // Check if the choice starts with a status icon followed by space and then the key
            if (choice.Contains($" {key}"))
            {
                return key;
            }
        }

        // Fallback: try the original split method if no match found
        var parts = choice.Split(SpaceSeparator, StringSplitOptions.RemoveEmptyEntries);
        return parts.Length > 1 ? parts[1] : choice;
    }
}
