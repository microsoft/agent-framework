// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Azure;
using Azure.Storage.Blobs;
using Skip = Xunit.Skip;

namespace Microsoft.Agents.AI.Hosting.AzureStorage.Tests;

/// <summary>
/// Helper class to check if Azurite (Azure Storage Emulator) is available and running.
/// </summary>
internal static class AzureStorageEmulatorAvailabilityHelper
{
    private const string AzuriteConnectionString = "UseDevelopmentStorage=true";

    /// <summary>
    /// Checks if Azurite is running and accessible.
    /// </summary>
    /// <returns><see langword="true"/> if Azurite is available; otherwise, <see langword="false"/>.</returns>
    public static async Task<bool> IsAvailableAsync(CancellationToken cancellationToken)
    {
        try
        {
            BlobServiceClient serviceClient = new(AzuriteConnectionString);

            // Try to get service properties to verify connection
            await serviceClient.GetPropertiesAsync(cancellationToken);

            return true;
        }
        catch (RequestFailedException)
        {
            // Azurite is not running or not accessible
            return false;
        }
        catch (Exception)
        {
            // Any other exception means Azurite is not available
            return false;
        }
    }

    public static async Task SkipIfNotAvailableAsync()
    {
        var cts = new CancellationTokenSource(TimeSpan.FromSeconds(3));
        bool isAvailable = await IsAvailableAsync(cts.Token);
        Skip.IfNot(isAvailable, "Azurite / Azure Storage Emulator is not running. Start Azurite to run these tests.");
    }
}
