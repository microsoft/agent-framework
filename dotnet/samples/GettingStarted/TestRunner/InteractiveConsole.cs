// Copyright (c) Microsoft. All rights reserved.

using Spectre.Console;

namespace GettingStarted.TestRunner;

/// <summary>
/// Interactive console interface for the test runner.
/// </summary>
public class InteractiveConsole
{
    private static readonly string[] BackToMainMenuOptions = { "Back to Main Menu" };
    private static readonly string[] BackOptions = { "Back" };

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
                case "Run Tests":
                    await RunTestsMenuAsync();
                    break;
                case "View Configuration":
                    ShowConfiguration();
                    break;
                case "Manage Secrets":
                    await ConfigureSecretsAsync();
                    break;
                case "Exit":
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

        var result = await _executionService.ExecuteTestAsync(filter, verbose: true);

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
                .AddChoices("Run Tests", "View Configuration", "Manage Secrets", "Exit"));
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
                    .AddChoices(folders.Select(f => f.Name).Concat(BackToMainMenuOptions)));

            if (folderChoice == "Back to Main Menu")
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
                $"Run All Tests in {folder.Name}",
                "Select Specific Test Class"
            };
            choices.AddRange(folder.Classes.Select(c => $"Class: {c.Name}"));
            choices.Add("Back to Folder Selection");

            var choice = AnsiConsole.Prompt(
                new SelectionPrompt<string>()
                    .Title($"[green]Tests in {folder.Name}:[/]")
                    .AddChoices(choices));

            if (choice == "Back to Folder Selection")
            {
                return;
            }

            if (choice == "Select Specific Test Class")
            {
                await ShowClassSelectionMenuAsync(folder);
            }
            else if (choice.StartsWith("Class: ", StringComparison.Ordinal))
            {
                var className = choice.Substring("Class: ".Length);
                var testClass = folder.Classes.First(c => c.Name == className);
                await ShowClassMenuAsync(testClass);
            }
        }
    }

    /// <summary>
    /// Shows the class selection menu.
    /// </summary>
    private async Task ShowClassSelectionMenuAsync(TestFolder folder)
    {
        var classChoice = AnsiConsole.Prompt(
            new SelectionPrompt<string>()
                .Title("[green]Select a test class:[/]")
                .AddChoices(folder.Classes.Select(c => c.Name).Concat(BackOptions)));

        if (classChoice == "Back")
        {
            return;
        }

        var selectedClass = folder.Classes.First(c => c.Name == classChoice);
        await ShowClassMenuAsync(selectedClass);
    }

    /// <summary>
    /// Shows the menu for a specific test class.
    /// </summary>
    private async Task ShowClassMenuAsync(TestClass testClass)
    {
        while (true)
        {
            var choices = new List<string>
            {
                $"Run All Methods in {testClass.Name}"
            };
            choices.AddRange(testClass.Methods.Select(m => $"Method: {m.Name}"));
            choices.Add("Back");

            var choice = AnsiConsole.Prompt(
                new SelectionPrompt<string>()
                    .Title($"[green]Methods in {testClass.Name}:[/]")
                    .AddChoices(choices));

            if (choice == "Back")
            {
                return;
            }

            if (choice == $"Run All Methods in {testClass.Name}")
            {
                var filter = TestExecutionService.GenerateClassFilter(testClass);
                await ExecuteTestWithResultAsync(filter);
            }
            else if (choice.StartsWith("Method: ", StringComparison.Ordinal))
            {
                var methodName = choice.Substring("Method: ".Length);
                var method = testClass.Methods.First(m => m.Name == methodName);
                await ShowMethodMenuAsync(method);
            }
        }
    }

    /// <summary>
    /// Shows the menu for a specific test method.
    /// </summary>
    private async Task ShowMethodMenuAsync(TestMethod method)
    {
        if (!method.IsTheory || method.TheoryData.Count == 0)
        {
            // Simple fact test or theory without data
            var filter = TestExecutionService.GenerateMethodFilter(method);
            await ExecuteTestWithResultAsync(filter);
            return;
        }

        var choices = new List<string>
        {
            $"Run All Theory Cases for {method.Name}"
        };
        choices.AddRange(method.TheoryData.Select(t => $"Theory: {t.DisplayName}"));
        choices.Add("Back");

        var choice = AnsiConsole.Prompt(
            new SelectionPrompt<string>()
                .Title($"[green]Theory cases for {method.Name}:[/]")
                .AddChoices(choices));

        if (choice == "Back")
        {
            return;
        }

        if (choice == $"Run All Theory Cases for {method.Name}")
        {
            var filter = TestExecutionService.GenerateMethodFilter(method);
            await ExecuteTestWithResultAsync(filter);
        }
        else if (choice.StartsWith("Theory: ", StringComparison.Ordinal))
        {
            var theoryDisplayName = choice.Substring("Theory: ".Length);
            var theoryCase = method.TheoryData.First(t => t.DisplayName == theoryDisplayName);
            var filter = TestExecutionService.GenerateTheoryFilter(method, theoryCase);
            await ExecuteTestWithResultAsync(filter);
        }
    }

    /// <summary>
    /// Executes a test and shows the result.
    /// </summary>
    private async Task ExecuteTestWithResultAsync(string filter)
    {
        var result = await _executionService.ExecuteTestAsync(filter, verbose: true);

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
                .Header("Test Output")
                .Border(BoxBorder.Rounded);
            AnsiConsole.Write(panel);
        }

        AnsiConsole.MarkupLine("[dim]Press any key to continue...[/]");
        Console.ReadKey();
    }

    /// <summary>
    /// Shows the current configuration.
    /// </summary>
    private void ShowConfiguration()
    {
        var status = _configurationManager.GetConfigurationStatus();

        var table = new Table();
        table.AddColumn("Configuration");
        table.AddColumn("Status");
        table.AddColumn("Value");

        // OpenAI configuration
        table.AddRow("OpenAI API Key",
            status.OpenAI.HasApiKey ? "[green]✓[/]" : "[red]✗[/]",
            status.OpenAI.ApiKey ?? "[dim]Not set[/]");
        table.AddRow("OpenAI Chat Model",
            status.OpenAI.HasChatModelId ? "[green]✓[/]" : "[red]✗[/]",
            status.OpenAI.ChatModelId ?? "[dim]Not set[/]");

        // Azure OpenAI configuration
        table.AddRow("Azure OpenAI Endpoint",
            status.AzureOpenAI.HasEndpoint ? "[green]✓[/]" : "[red]✗[/]",
            status.AzureOpenAI.Endpoint ?? "[dim]Not set[/]");
        table.AddRow("Azure OpenAI Deployment",
            status.AzureOpenAI.HasDeploymentName ? "[green]✓[/]" : "[red]✗[/]",
            status.AzureOpenAI.DeploymentName ?? "[dim]Not set[/]");
        table.AddRow("Azure OpenAI API Key",
            status.AzureOpenAI.HasApiKey ? "[green]✓[/]" : "[yellow]⚠ (Using Azure CLI)[/]",
            status.AzureOpenAI.ApiKey ?? "[dim]Using Azure CLI[/]");

        AnsiConsole.Write(table);

        AnsiConsole.MarkupLine("[dim]Press any key to continue...[/]");
        Console.ReadKey();
    }

    /// <summary>
    /// Handles configuration setup.
    /// </summary>
    private async Task ConfigureSecretsAsync()
    {
        await _configurationManager.ManageConfigurationAsync();
    }
}
