// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Harness.Shared.Console.Observers;

/// <summary>
/// Displays token usage statistics (📊) from the response stream.
/// </summary>
internal sealed class UsageDisplayObserver : ConsoleObserver
{
    private readonly int? _maxContextWindowTokens;
    private readonly int? _maxOutputTokens;

    /// <summary>
    /// Initializes a new instance of the <see cref="UsageDisplayObserver"/> class.
    /// </summary>
    /// <param name="maxContextWindowTokens">Optional max context window size in tokens.</param>
    /// <param name="maxOutputTokens">Optional max output tokens.</param>
    public UsageDisplayObserver(int? maxContextWindowTokens, int? maxOutputTokens)
    {
        this._maxContextWindowTokens = maxContextWindowTokens;
        this._maxOutputTokens = maxOutputTokens;
    }

    /// <inheritdoc/>
    public override Task OnContentAsync(HarnessUXContainer ux, AIContent content)
    {
        if (content is UsageContent usage)
        {
            if (usage.Details is not null)
            {
                ux.SetUsageText(this.FormatUsageBreakdown(usage.Details));
            }
            else
            {
                ux.SetUsageText("📊 Tokens —");
            }
        }

        return Task.CompletedTask;
    }

    private string FormatUsageBreakdown(UsageDetails details)
    {
        int? inputBudget = (this._maxContextWindowTokens is not null && this._maxOutputTokens is not null)
            ? this._maxContextWindowTokens.Value - this._maxOutputTokens.Value
            : null;

        return $"📊 Tokens — input: {FormatTokenCount(details.InputTokenCount, inputBudget)}"
            + $" | output: {FormatTokenCount(details.OutputTokenCount, this._maxOutputTokens)}"
            + $" | total: {FormatTokenCount(details.TotalTokenCount, this._maxContextWindowTokens)}";
    }

    private static string FormatTokenCount(long? count, int? budget)
    {
        if (count is null)
        {
            return "—";
        }

        if (budget is not null && budget.Value > 0)
        {
            double pct = (double)count.Value / budget.Value * 100;
            return $"{count.Value:N0}/{budget.Value:N0} ({pct:F1}%)";
        }

        return $"{count.Value:N0}";
    }
}
