// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable IDE0005 // This is required in some projects and not in others.
using System;
#pragma warning restore IDE0005
using Azure.Identity;

namespace Shared.IntegrationTests;

/// <summary>
/// Provides credential instances for integration tests with
/// increased timeouts to avoid CI pipeline authentication failures.
/// </summary>
internal static class TestAzureCliCredentials
{
    /// <summary>
    /// The default timeout for Azure CLI credential operations.
    /// Increased from the default (~13s) to accommodate CI pipeline latency.
    /// </summary>
    private static readonly TimeSpan s_processTimeout = TimeSpan.FromSeconds(60);

    /// <summary>
    /// Creates a new <see cref="AzureCliCredential"/> with an increased process timeout
    /// suitable for CI environments.
    /// </summary>
    public static AzureCliCredential CreateAzureCliCredential() =>
        new(new AzureCliCredentialOptions { ProcessTimeout = s_processTimeout });
}
