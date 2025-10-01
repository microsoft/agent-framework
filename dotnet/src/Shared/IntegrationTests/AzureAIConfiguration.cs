// Copyright (c) Microsoft. All rights reserved.

namespace Shared.IntegrationTests;

#pragma warning disable CS8618 // Non-nullable field must contain a non-null value when exiting constructor. Consider adding the 'required' modifier or declaring as nullable.
#pragma warning disable CA1812 // Internal class that is apparently never instantiated.

internal sealed class AzureAIConfiguration
{
    public string Endpoint { get; set; }

    public string DeploymentName { get; set; }

    public string BingConnectionId { get; set; }
}
