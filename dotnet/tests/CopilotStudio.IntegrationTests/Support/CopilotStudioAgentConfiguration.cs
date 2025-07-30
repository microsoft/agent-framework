// Copyright (c) Microsoft. All rights reserved.

namespace CopilotStudio.IntegrationTests.Support;

#pragma warning disable CS8618 // Non-nullable field must contain a non-null value when exiting constructor. Consider adding the 'required' modifier or declaring as nullable.
#pragma warning disable CA1812 // Internal class that is apparently never instantiated.

internal sealed class CopilotStudioAgentConfiguration
{
    public string DirectConnectUrl { get; set; }

    public string TenantId { get; set; }

    public string AppClientId { get; set; }
}
