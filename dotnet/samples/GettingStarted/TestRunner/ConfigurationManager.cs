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
        this._configuration = configuration;
    }

    /// <summary>
    /// Validates that all required configuration is present.
    /// </summary>
    public async Task<bool> ValidateConfigurationAsync()
    {
        var missingConfigs = new List<string>();
        var allConfigKeys = ConfigurationKeyExtractor.GetConfigurationKeys();

        // Check all required configuration keys dynamically
        foreach (var key in allConfigKeys)
        {
            if (ConfigurationKeyExtractor.IsRequiredKey(key) && string.IsNullOrEmpty(this._configuration[key]))
            {
                missingConfigs.Add(key);
            }
        }

        if (missingConfigs.Count == 0)
        {
            AnsiConsole.MarkupLine("[green]✓ All required configuration is present[/]");
            return true;
        }

        AnsiConsole.MarkupLine("[yellow]⚠ Missing configuration detected[/]");

        foreach (var config in missingConfigs)
        {
            var friendlyName = ConfigurationKeyExtractor.GetFriendlyDescription(config);
            AnsiConsole.MarkupLine($"[red]✗ Missing: {friendlyName} ({config})[/]");
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
        AnsiConsole.MarkupLine(NavigationConstants.ConfigurationMessages.SettingUpConfiguration);

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
            AnsiConsole.MarkupLine(NavigationConstants.ConfigurationMessages.NoValuesProvided);
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

        AnsiConsole.MarkupLine(NavigationConstants.ConfigurationMessages.SavedSuccessfully);
        AnsiConsole.MarkupLine(NavigationConstants.ConfigurationMessages.RestartNote);

        return true;
    }

    /// <summary>
    /// Interactively manages all configuration settings (add/update/remove).
    /// </summary>
    public async Task<bool> ManageConfigurationAsync()
    {
        while (true)
        {
            AnsiConsole.MarkupLine(NavigationConstants.ConfigurationMenu.Title);
            AnsiConsole.WriteLine();

            var allConfigKeys = ConfigurationKeyExtractor.GetConfigurationKeys();

            var choices = new List<string>();

            foreach (var key in allConfigKeys)
            {
                var hasValue = HasCurrentConfigurationValue(key);
                var isRequired = ConfigurationKeyExtractor.IsRequiredKey(key);

                // Converted to switch expression
                string statusIcon = (hasValue, isRequired) switch
                {
                    (true, _) => NavigationConstants.ConfigurationDisplay.SetStatusIcon,
                    (false, true) => NavigationConstants.ConfigurationDisplay.NotSetStatusIcon,
                    _ => NavigationConstants.ConfigurationDisplay.OptionalFieldIndicator
                };

                var currentValue = GetCurrentConfigurationValue(key);
                var displayValue = hasValue
                    ? $"{NavigationConstants.ConfigurationDisplay.CurrentValuePrefix}{currentValue}{NavigationConstants.ConfigurationDisplay.ClosingParenthesis}"
                    : (isRequired ? NavigationConstants.ConfigurationDisplay.NotSetSuffix : NavigationConstants.ConfigurationDisplay.OptionalSuffix);

                choices.Add($"{statusIcon} {key}{displayValue}");
            }

            choices.Add(NavigationConstants.CommonUI.Back);

            var choice = AnsiConsole.Prompt(
                new SelectionPrompt<string>()
                    .Title(NavigationConstants.ConfigurationMenu.SelectPrompt)
                    .AddChoices(choices));

            if (choice == NavigationConstants.CommonUI.Back)
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
            AnsiConsole.MarkupLine(NavigationConstants.ConfigurationMessages.NoCurrentValue);
        }

        var actions = new List<string> { NavigationConstants.ConfigurationActions.SetNewValue };

        if (hasCurrentValue)
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
                var existingValue = this._configuration[configKey];
                var newValue = PromptForConfigValue(configKey, existingValue);
                if (!string.IsNullOrEmpty(newValue))
                {
                    var success = await SetUserSecretAsync(configKey, newValue);
                    if (success)
                    {
                        RefreshConfiguration();
                        AnsiConsole.MarkupLine(NavigationConstants.ConfigurationMessages.UpdatedSuccessfully);
                        return true;
                    }
                }
                return false;

            case var _ when action == NavigationConstants.ConfigurationActions.RemoveCurrentValue:
                var removed = await RemoveUserSecretAsync(configKey);
                if (removed)
                {
                    RefreshConfiguration();
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
        var friendlyName = ConfigurationKeyExtractor.GetFriendlyDescription(configKey);
        var isSecret = ConfigurationKeyExtractor.IsSecretKey(configKey);
        var isOptional = !ConfigurationKeyExtractor.IsRequiredKey(configKey);

        // Build prompt text with current value display
        string promptText;
        string? formatedValue = (isSecret) ? MaskSecret(currentValue) : currentValue;

        promptText = $"[blue]Enter {friendlyName}:[/]";
        var prompt = new TextPrompt<string?>(promptText);

        // Configure prompt based on attributes
        if (isSecret)
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
        if (isSecret && string.IsNullOrWhiteSpace(userInput) && !string.IsNullOrEmpty(currentValue))
        {
            return currentValue!;
        }

        return userInput ?? string.Empty;
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

#if !NET8_0_OR_GREATER
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

#if !NET8_0_OR_GREATER
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
        return !string.IsNullOrEmpty(this._configuration[key]);
    }

    /// <summary>
    /// Gets a configuration value for display, masking secrets but showing non-secrets.
    /// </summary>
    private string GetMaskedConfigValue(string key)
    {
        var value = this._configuration[key];
        if (string.IsNullOrEmpty(value))
        {
            return NavigationConstants.ConfigurationMessages.NotSet;
        }

        // Only mask actual secrets (API keys), show other values as-is
        if (ConfigurationKeyExtractor.IsSecretKey(key))
        {
            var masked = MaskSecret(value);
            return masked ?? NavigationConstants.ConfigurationMessages.NotSet;
        }

        return value ?? NavigationConstants.ConfigurationMessages.NotSet;
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

        this._configuration = builder.Build();
    }

    /// <summary>
    /// Gets the current configuration value for display, with secrets masked.
    /// Always reads the latest configuration without caching.
    /// </summary>
    public string GetCurrentConfigurationValue(string key)
    {
        // Always refresh configuration to get the latest values
        RefreshConfiguration();

        var value = this._configuration[key];

        if (string.IsNullOrEmpty(value))
        {
            return NavigationConstants.ConfigurationMessages.NotSet;
        }

        // Only mask actual secrets (API keys), show other values as-is
        if (ConfigurationKeyExtractor.IsSecretKey(key))
        {
            var masked = MaskSecret(value);
            return masked ?? NavigationConstants.ConfigurationMessages.NotSet;
        }

        return value ?? NavigationConstants.ConfigurationMessages.NotSet;
    }

    /// <summary>
    /// Checks if a configuration key has a value.
    /// Always reads the latest configuration without caching.
    /// </summary>
    public bool HasCurrentConfigurationValue(string key)
    {
        // Always refresh configuration to get the latest values
        RefreshConfiguration();

        return !string.IsNullOrEmpty(this._configuration[key]);
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

#if NET8_0_OR_GREATER
        return string.Concat(secret.AsSpan(0, 4), "***", secret.AsSpan(secret.Length - 4));
#else
        return secret.Substring(0, 4) + "***" + secret.Substring(secret.Length - 4);
#endif
    }
}
