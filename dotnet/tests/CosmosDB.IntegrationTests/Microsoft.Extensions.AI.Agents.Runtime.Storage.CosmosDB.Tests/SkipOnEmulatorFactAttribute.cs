// Copyright (c) Microsoft. All rights reserved.

using CosmosDB.Testing.AppHost;

namespace Microsoft.Extensions.AI.Agents.Runtime.Storage.CosmosDB.Tests;

/// <summary>
/// Skip test if running on CosmosDB emulator.
/// </summary>
[AttributeUsage(AttributeTargets.Method | AttributeTargets.Class, AllowMultiple = false)]
public sealed class SkipOnEmulatorFactAttribute : FactAttribute
{
    /// <summary>
    /// Initializes a new instance of the <see cref="SkipOnEmulatorFactAttribute"/> class.
    /// </summary>
    public SkipOnEmulatorFactAttribute()
    {
        if (CosmosDBTestConstants.UseAspireEmulatorForTesting)
        {
            this.Skip = "Skipping test on Aspire-configured CosmosDB emulator.";
        }

        if (CosmosDBTestConstants.UseEmulatorInCICD)
        {
            this.Skip = "Skipping test on CICD-configured CosmosDB emulator.";
        }
    }
}
