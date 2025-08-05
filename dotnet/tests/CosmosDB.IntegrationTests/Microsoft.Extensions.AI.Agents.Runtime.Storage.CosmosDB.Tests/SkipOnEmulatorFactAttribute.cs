// Copyright (c) Microsoft. All rights reserved.

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
        if (CosmosDBTestConstants.UseEmulatorForTesting)
        {
            this.Skip = "Skipping test on CosmosDB emulator.";
        }
    }
}
