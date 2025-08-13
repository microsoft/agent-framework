// Copyright (c) Microsoft. All rights reserved.

using Spectre.Console;

namespace GettingStarted.TestRunner;

/// <summary>
/// Interactive console interface for the test runner.
/// </summary>
public class InteractiveConsole
{
    private static readonly string[] BackToMainMenuOptions = { NavigationConstants.TestNavigation.BackToMainMenu };

    private readonly TestDiscoveryService _discoveryService;
    private readonly ConfigurationManager _configurationManager;
    private readonly TestExecutionService _executionService;

    public InteractiveConsole(
        TestDiscoveryService discoveryService,
        ConfigurationManager configurationManager,
        TestExecutionService executionService)
    {
        _discoveryService = discoveryService;
        _configurationManager = configurationManager;
        _executionService = executionService;
    }

    /// <summary>
    /// Runs the interactive console interface.
    /// </summary>
    public async Task<int> RunInteractiveAsync()
    {
        ShowWelcome();

        // Validate configuration first
        var configValid = await _configurationManager.ValidateConfigurationAsync();
        if (!configValid)
        {
            AnsiConsole.MarkupLine("[red]Configuration validation failed. Please set up your configuration first.[/]");
            return 1;
        }

        while (true)
        {
            var choice = ShowMainMenu();

            switch (choice)
            {
                case var _ when choice == NavigationConstants.MainMenu.RunTests:
                    await RunTestsMenuAsync();
                    break;
                case var _ when choice == NavigationConstants.MainMenu.ViewConfiguration:
                    ShowConfiguration();
                    break;
                case var _ when choice == NavigationConstants.MainMenu.ManageSecrets:
                    await ConfigureSecretsAsync();
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

        var result = await _executionService.ExecuteTestAsync(filter);

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
            AnsiConsole.MarkupLine($"[red]Error: {result.Error}[/]");
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
        return AnsiConsole.Prompt(
            new SelectionPrompt<string>()
                .Title("[green]What would you like to do?[/]")
                .AddChoices(
                    NavigationConstants.MainMenu.Exit,
                    NavigationConstants.MainMenu.RunTests,
                    NavigationConstants.MainMenu.ViewConfiguration,
                    NavigationConstants.MainMenu.ManageSecrets));
    }

    /// <summary>
    /// Handles the test running menu.
    /// </summary>
    private async Task RunTestsMenuAsync()
    {
        while (true)
        {
            var folders = _discoveryService.DiscoverTestFolders();

            if (folders.Count == 0)
            {
                AnsiConsole.MarkupLine("[red]No test folders found[/]");
                return;
            }

            var folderChoice = AnsiConsole.Prompt(
                new SelectionPrompt<string>()
                    .Title("[green]Select a test folder:[/]")
                    .AddChoices(BackToMainMenuOptions.Concat(folders.Select(f => f.Name))));

            if (folderChoice == NavigationConstants.TestNavigation.BackToMainMenu)
            {
                return;
            }

            var selectedFolder = folders.First(f => f.Name == folderChoice);
            await ShowFolderMenuAsync(selectedFolder);
        }
    }

    /// <summary>
    /// Shows the menu for a specific test folder.
    /// </summary>
    private async Task ShowFolderMenuAsync(TestFolder folder)
    {
        while (true)
        {
            var choices = new List<string>
            {
                NavigationConstants.TestNavigation.BackToFolderSelection
            };
            choices.AddRange(folder.Classes.Select(c => $"Class: {c.Name}"));

            var choice = AnsiConsole.Prompt(
                new SelectionPrompt<string>()
                    .Title($"[green]Tests in {folder.Name}:[/]")
                    .AddChoices(choices));

            if (choice == NavigationConstants.TestNavigation.BackToFolderSelection)
            {
                return;
            }

            if (choice.StartsWith("Class: ", StringComparison.Ordinal))
            {
                var className = choice.Substring("Class: ".Length);
                var testClass = folder.Classes.First(c => c.Name == className);
                await ShowClassMenuAsync(testClass);
            }
        }
    }

    /// <summary>
    /// Shows the menu for a specific test class with flattened test method selection.
    /// </summary>
    private async Task ShowClassMenuAsync(TestClass testClass)
    {
        while (true)
        {
            var choices = new List<string>
            {
                "Back"
            };

            // Add all test methods (Facts and individual Theory cases) at the same level
            foreach (var method in testClass.Methods)
            {
                if (!method.IsTheory || method.TheoryData.Count == 0)
                {
                    // Simple fact test or theory without data - add as single method
                    choices.Add(method.Name);
                }
                else
                {
                    // Theory with data - add each theory case as individual test
                    foreach (var theoryCase in method.TheoryData)
                    {
                        choices.Add($"{method.Name} ({theoryCase.DisplayName})");
                    }
                }
            }

            var choice = AnsiConsole.Prompt(
                new SelectionPrompt<string>()
                    .Title($"[green]Test methods in {testClass.Name}:[/]")
                    .AddChoices(choices));

            if (choice == "Back")
            {
                return;
            }

            // Execute the selected test
            await ExecuteSelectedTestAsync(testClass, choice);
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
            await ExecuteTestWithResultAsync(filter);
        }
        else
        {
            // Simple fact test or theory without data
            var method = testClass.Methods.First(m => m.Name == choice);
            var filter = TestExecutionService.GenerateMethodFilter(method);
            await ExecuteTestWithResultAsync(filter);
        }
    }

    /// <summary>
    /// Executes a test and shows the result.
    /// </summary>
    private async Task ExecuteTestWithResultAsync(string filter)
    {
        var result = await _executionService.ExecuteTestAsync(filter);

        if (result.Success)
        {
            AnsiConsole.MarkupLine("[green]✓ Test completed successfully[/]");
        }
        else
        {
            AnsiConsole.MarkupLine("[red]✗ Test failed[/]");
            if (!string.IsNullOrEmpty(result.Error))
            {
                AnsiConsole.MarkupLine($"[red]Error: {result.Error}[/]");
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
    /// Shows the current configuration.
    /// </summary>
    private void ShowConfiguration()
    {
        var table = new Table();
        table.AddColumn("Configuration");
        table.AddColumn("Status");
        table.AddColumn("Value");

        // Get all configuration keys dynamically from TestConfiguration
        var allConfigKeys = ConfigurationKeyExtractor.GetConfigurationKeys();

        foreach (var key in allConfigKeys)
        {
            var hasValue = _configurationManager.HasCurrentConfigurationValue(key);
            var isRequired = ConfigurationKeyExtractor.IsRequiredKey(key);

            string statusIcon;
            if (hasValue)
            {
                statusIcon = "[green]✓[/]";
            }
            else if (isRequired)
            {
                statusIcon = "[red]✗[/]";
            }
            else
            {
                statusIcon = "[dim]○[/]"; // Optional field indicator
            }

            var currentValue = _configurationManager.GetCurrentConfigurationValue(key);

            // Create a friendly display name from the key
            var displayName = GetFriendlyConfigurationName(key);

            table.AddRow(displayName, statusIcon, currentValue);
        }

        AnsiConsole.Write(table);

        AnsiConsole.MarkupLine(NavigationConstants.CommonUI.PressAnyKeyToContinue);
        Console.ReadKey();
    }

    /// <summary>
    /// Converts a configuration key to a friendly display name.
    /// </summary>
    private static string GetFriendlyConfigurationName(string key)
    {
        return ConfigurationKeyExtractor.GetFriendlyDescription(key);
    }

    /// <summary>
    /// Handles configuration setup.
    /// </summary>
    private async Task ConfigureSecretsAsync()
    {
        await _configurationManager.ManageConfigurationAsync();
    }
}
