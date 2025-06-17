﻿// Copyright (c) Microsoft. All rights reserved.

using Shared.IntegrationTests;

#pragma warning disable CS8618 // Non-nullable field must contain a non-null value when exiting constructor. Consider adding the 'required' modifier or declaring as nullable.
#pragma warning disable CA1812 // Internal class that is apparently never instantiated.

internal sealed class AzureConfiguration
{
    public string Endpoint { get; set; }

    public string DeploymentName { get; set; }
}
