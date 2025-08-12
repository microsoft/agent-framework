// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using Microsoft.Extensions.Configuration;
using Spectre.Console;

namespace GettingStarted.TestRunner;

/// <summary>
/// Manages configuration validation and user secrets setup.
/// </summary>
public class ConfigurationManager
{
    private IConfiguration _configuration;

    public ConfigurationManager(IConfiguration configuration)
    {
        _configuration = configuration;
    }

    /// <summary>
    /// Validates that all required configuration is present.
    /// </summary>
    public async Task<bool> ValidateConfigurationAsync()
    {
        var missingConfigs = new List<string>();

        // Check OpenAI configuration
        if (string.IsNullOrEmpty(_configuration["OpenAI:ApiKey"]))
        {
            missingConfigs.Add("OpenAI:ApiKey");
        }

        if (string.IsNullOrEmpty(_configuration["OpenAI:ChatModelId"]))
        {
            missingConfigs.Add("OpenAI:ChatModelId");
        }

        // Check Azure OpenAI configuration
        if (string.IsNullOrEmpty(_configuration["AzureOpenAI:Endpoint"]))
        {
            missingConfigs.Add("AzureOpenAI:Endpoint");
        }

        if (string.IsNullOrEmpty(_configuration["AzureOpenAI:DeploymentName"]))
        {
            missingConfigs.Add("AzureOpenAI:DeploymentName");
        }

        if (missingConfigs.Count == 0)
        {
            AnsiConsole.MarkupLine("[green]✓ All required configuration is present[/]");
            return true;
        }

        AnsiConsole.MarkupLine("[yellow]⚠ Missing configuration detected[/]");

        foreach (var config in missingConfigs)
        {
            AnsiConsole.MarkupLine($"[red]✗ Missing: {config}[/]");
        }

        var setupConfig = AnsiConsole.Confirm("Would you like to set up the missing configuration now?");

        if (setupConfig)
        {
            return await SetupConfigurationAsync(missingConfigs);
        }

        return false;
    }

    /// <summary>
    /// Interactively sets up missing configuration.
    /// </summary>
    private async Task<bool> SetupConfigurationAsync(List<string> missingConfigs)
    {
        AnsiConsole.MarkupLine("[blue]Setting up configuration using user secrets...[/]");

        var configValues = new Dictionary<string, string>();

        foreach (var configKey in missingConfigs)
        {
            var value = PromptForConfigValue(configKey);
            if (!string.IsNullOrEmpty(value))
            {
                configValues[configKey] = value;
            }
        }

        if (configValues.Count == 0)
        {
            AnsiConsole.MarkupLine("[red]No configuration values provided[/]");
            return false;
        }

        // Save to user secrets
        foreach (var kvp in configValues)
        {
            var success = await SetUserSecretAsync(kvp.Key, kvp.Value);
            if (!success)
            {
                AnsiConsole.MarkupLine($"[red]Failed to set {kvp.Key}[/]");
                return false;
            }
        }

        AnsiConsole.MarkupLine("[green]✓ Configuration saved successfully![/]");
        AnsiConsole.MarkupLine("[yellow]Note: You may need to restart the application for changes to take effect.[/]");

        return true;
    }

    /// <summary>
    /// Interactively manages all configuration settings (add/update/remove).
    /// </summary>
    public async Task<bool> ManageConfigurationAsync()
    {
        while (true)
        {
            var status = GetConfigurationStatus();

            AnsiConsole.MarkupLine("[blue]Configuration Management[/]");
            AnsiConsole.WriteLine();

            var allConfigKeys = new[]
            {
                "OpenAI:ApiKey",
                "OpenAI:ChatModelId",
                "AzureOpenAI:Endpoint",
                "AzureOpenAI:DeploymentName",
                "AzureOpenAI:ApiKey"
            };

            var choices = new List<string>();

            foreach (var key in allConfigKeys)
            {
                var hasValue = HasConfigurationValue(key);
                var statusIcon = hasValue ? "✓" : "✗";
                var currentValue = GetMaskedConfigValue(key);
                var displayValue = hasValue ? $" (Current: {currentValue})" : " (Not set)";

                choices.Add($"{statusIcon} {key}{displayValue}");
            }

            choices.Add("Back to Main Menu");

            var choice = AnsiConsole.Prompt(
                new SelectionPrompt<string>()
                    .Title("[green]Select a configuration to update:[/]")
                    .AddChoices(choices));

            if (choice == "Back to Main Menu")
            {
                return true;
            }

            // Extract the config key from the choice
            var configKey = choice.Split(' ')[1]; // Skip the status icon

            // Update the configuration and continue the loop regardless of result
            await UpdateSingleConfigurationAsync(configKey);

            // Clear the screen for the next iteration
            AnsiConsole.Clear();
        }
    }

    /// <summary>
    /// Updates a single configuration value.
    /// </summary>
    private async Task<bool> UpdateSingleConfigurationAsync(string configKey)
    {
        var currentValue = GetMaskedConfigValue(configKey);
        var hasCurrentValue = HasConfigurationValue(configKey);

        AnsiConsole.MarkupLine($"[blue]Updating: {configKey}[/]");

        if (hasCurrentValue)
        {
            AnsiConsole.MarkupLine($"[dim]Current value: {currentValue}[/]");
        }
        else
        {
            AnsiConsole.MarkupLine("[dim]No current value set[/]");
        }

        var actions = new List<string> { "Set new value" };

        if (hasCurrentValue)
        {
            actions.Add("Remove current value");
        }

        actions.Add("Cancel");

        var action = AnsiConsole.Prompt(
            new SelectionPrompt<string>()
                .Title("[green]What would you like to do?[/]")
                .AddChoices(actions));

        switch (action)
        {
            case "Set new value":
                var newValue = PromptForConfigValue(configKey);
                if (!string.IsNullOrEmpty(newValue))
                {
                    var success = await SetUserSecretAsync(configKey, newValue);
                    if (success)
                    {
                        RefreshConfiguration();
                        AnsiConsole.MarkupLine("[green]✓ Configuration updated successfully![/]");
                        return true;
                    }
                }
                return false;

            case "Remove current value":
                var removed = await RemoveUserSecretAsync(configKey);
                if (removed)
                {
                    RefreshConfiguration();
                    AnsiConsole.MarkupLine("[green]✓ Configuration removed successfully![/]");
                    return true;
                }
                return false;

            case "Cancel":
                return true;

            default:
                return false;
        }
    }

    /// <summary>
    /// Prompts the user for a configuration value.
    /// </summary>
    private string PromptForConfigValue(string configKey)
    {
        return configKey switch
        {
            "OpenAI:ApiKey" => AnsiConsole.Prompt(
                new TextPrompt<string>("[blue]Enter your OpenAI API Key:[/]")
                    .PromptStyle("red")
                    .Secret()),

            "OpenAI:ChatModelId" => AnsiConsole.Prompt(
                new TextPrompt<string>("[blue]Enter OpenAI Chat Model ID:[/]")
                    .DefaultValue("gpt-4o-mini")),

            "AzureOpenAI:Endpoint" => AnsiConsole.Prompt(
                new TextPrompt<string>("[blue]Enter your Azure OpenAI Endpoint (e.g., https://your-resource.openai.azure.com/):[/]")
                    .ValidationErrorMessage("[red]Please enter a valid HTTPS URL[/]")
                    .Validate(url => Uri.TryCreate(url, UriKind.Absolute, out var uri) && uri.Scheme == "https")),

            "AzureOpenAI:DeploymentName" => AnsiConsole.Prompt(
                new TextPrompt<string>("[blue]Enter your Azure OpenAI Deployment Name:[/]")
                    .DefaultValue("gpt-4o-mini")),

            "AzureOpenAI:ApiKey" => AnsiConsole.Prompt(
                new TextPrompt<string>("[blue]Enter your Azure OpenAI API Key (leave empty to use Azure CLI authentication):[/]")
                    .PromptStyle("red")
                    .Secret()
                    .AllowEmpty()),

            _ => AnsiConsole.Prompt(new TextPrompt<string>($"[blue]Enter value for {configKey}:[/]"))
        };
    }

    /// <summary>
    /// Sets a user secret using dotnet CLI.
    /// </summary>
    private async Task<bool> SetUserSecretAsync(string key, string value)
    {
        try
        {
            var startInfo = new ProcessStartInfo
            {
                FileName = "dotnet",
                Arguments = $"user-secrets set \"{key}\" \"{value}\"",
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true
            };

            using var process = Process.Start(startInfo);
            if (process == null)
            {
                AnsiConsole.MarkupLine("[red]Failed to start dotnet process[/]");
                return false;
            }

#if NET472
            process.WaitForExit();
#else
            await process.WaitForExitAsync();
#endif

            if (process.ExitCode == 0)
            {
                AnsiConsole.MarkupLine($"[green]✓ Set {key}[/]");
                return true;
            }

            var error = await process.StandardError.ReadToEndAsync();
            AnsiConsole.MarkupLine($"[red]Failed to set {key}: {error}[/]");
            return false;
        }
        catch (Exception ex)
        {
            AnsiConsole.MarkupLine($"[red]Error setting {key}: {ex.Message}[/]");
            return false;
        }
    }

    /// <summary>
    /// Removes a user secret using dotnet CLI.
    /// </summary>
    private async Task<bool> RemoveUserSecretAsync(string key)
    {
        try
        {
            var startInfo = new ProcessStartInfo
            {
                FileName = "dotnet",
                Arguments = $"user-secrets remove \"{key}\"",
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true
            };

            using var process = Process.Start(startInfo);
            if (process == null)
            {
                AnsiConsole.MarkupLine("[red]Failed to start dotnet process[/]");
                return false;
            }

#if NET472
            process.WaitForExit();
#else
            await process.WaitForExitAsync();
#endif

            if (process.ExitCode == 0)
            {
                AnsiConsole.MarkupLine($"[green]✓ Removed {key}[/]");
                return true;
            }

            var error = await process.StandardError.ReadToEndAsync();
            AnsiConsole.MarkupLine($"[red]Failed to remove {key}: {error}[/]");
            return false;
        }
        catch (Exception ex)
        {
            AnsiConsole.MarkupLine($"[red]Error removing {key}: {ex.Message}[/]");
            return false;
        }
    }

    /// <summary>
    /// Checks if a configuration value exists.
    /// </summary>
    private bool HasConfigurationValue(string key)
    {
        return !string.IsNullOrEmpty(_configuration[key]);
    }

    /// <summary>
    /// Gets a configuration value for display, masking secrets but showing non-secrets.
    /// </summary>
    private string GetMaskedConfigValue(string key)
    {
        var value = _configuration[key];
        if (string.IsNullOrEmpty(value))
        {
            return "[dim]Not set[/]";
        }

        // Only mask actual secrets (API keys), show other values as-is
        if (IsSecretKey(key))
        {
            var masked = MaskSecret(value);
            return masked ?? "[dim]Not set[/]";
        }

        return value ?? "[dim]Not set[/]";
    }

    /// <summary>
    /// Determines if a configuration key represents a secret that should be masked.
    /// </summary>
    private static bool IsSecretKey(string key)
    {
        return key.EndsWith(":ApiKey", StringComparison.OrdinalIgnoreCase);
    }

    /// <summary>
    /// Refreshes the configuration to pick up any changes made through user secrets.
    /// </summary>
    private void RefreshConfiguration()
    {
        // Rebuild the configuration to pick up changes from user secrets
        var builder = new ConfigurationBuilder()
            .AddUserSecrets(typeof(Program).Assembly)
            .AddEnvironmentVariables();

        _configuration = builder.Build();
    }

    /// <summary>
    /// Gets the current configuration status.
    /// </summary>
    public ConfigurationStatus GetConfigurationStatus()
    {
        var status = new ConfigurationStatus();

        // Check OpenAI
        status.OpenAI.HasApiKey = !string.IsNullOrEmpty(_configuration["OpenAI:ApiKey"]);
        status.OpenAI.HasChatModelId = !string.IsNullOrEmpty(_configuration["OpenAI:ChatModelId"]);
        status.OpenAI.ApiKey = MaskSecret(_configuration["OpenAI:ApiKey"]);
        status.OpenAI.ChatModelId = _configuration["OpenAI:ChatModelId"];

        // Check Azure OpenAI
        status.AzureOpenAI.HasEndpoint = !string.IsNullOrEmpty(_configuration["AzureOpenAI:Endpoint"]);
        status.AzureOpenAI.HasDeploymentName = !string.IsNullOrEmpty(_configuration["AzureOpenAI:DeploymentName"]);
        status.AzureOpenAI.HasApiKey = !string.IsNullOrEmpty(_configuration["AzureOpenAI:ApiKey"]);
        status.AzureOpenAI.Endpoint = _configuration["AzureOpenAI:Endpoint"];
        status.AzureOpenAI.DeploymentName = _configuration["AzureOpenAI:DeploymentName"];
        status.AzureOpenAI.ApiKey = MaskSecret(_configuration["AzureOpenAI:ApiKey"]);

        return status;
    }

    /// <summary>
    /// Masks a secret value for display.
    /// </summary>
    private static string? MaskSecret(string? secret)
    {
        if (string.IsNullOrEmpty(secret))
        {
            return null;
        }

        if (secret.Length <= 8)
        {
            return "***";
        }

#if NET9_0_OR_GREATER
        return string.Concat(secret.AsSpan(0, 4), "***", secret.AsSpan(secret.Length - 4));
#else
        return secret.Substring(0, 4) + "***" + secret.Substring(secret.Length - 4);
#endif
    }
}

/// <summary>
/// Represents the current configuration status.
/// </summary>
public class ConfigurationStatus
{
    public OpenAIStatus OpenAI { get; set; } = new();
    public AzureOpenAIStatus AzureOpenAI { get; set; } = new();
}

public class OpenAIStatus
{
    public bool HasApiKey { get; set; }
    public bool HasChatModelId { get; set; }
    public string? ApiKey { get; set; }
    public string? ChatModelId { get; set; }
}

public class AzureOpenAIStatus
{
    public bool HasEndpoint { get; set; }
    public bool HasDeploymentName { get; set; }
    public bool HasApiKey { get; set; }
    public string? Endpoint { get; set; }
    public string? DeploymentName { get; set; }
    public string? ApiKey { get; set; }
}
