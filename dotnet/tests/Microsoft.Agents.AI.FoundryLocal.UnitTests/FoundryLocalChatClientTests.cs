// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.FoundryLocal.UnitTests;

public class FoundryLocalChatClientTests
{
    [Fact]
    public async Task CreateAsync_WithNullOptions_Throws()
    {
        await Assert.ThrowsAsync<ArgumentNullException>(() =>
            FoundryLocalChatClient.CreateAsync(null!));
    }

    [Fact]
    public async Task CreateAsync_WithNoModel_ThrowsInvalidOperation()
    {
        var previousValue = Environment.GetEnvironmentVariable("FOUNDRY_LOCAL_MODEL");
        try
        {
            Environment.SetEnvironmentVariable("FOUNDRY_LOCAL_MODEL", null);
            var options = new FoundryLocalClientOptions { Bootstrap = false };

            await Assert.ThrowsAsync<InvalidOperationException>(() =>
                FoundryLocalChatClient.CreateAsync(options));
        }
        finally
        {
            Environment.SetEnvironmentVariable("FOUNDRY_LOCAL_MODEL", previousValue);
        }
    }
}
