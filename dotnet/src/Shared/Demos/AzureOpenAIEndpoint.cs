// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable IDE0005 // This file is shared by projects with and without implicit usings.

using System;

namespace SampleHelpers;

internal static class AzureOpenAIEndpoint
{
    public static Uri? From(string? endpoint)
    {
        if (string.IsNullOrWhiteSpace(endpoint))
        {
            return null;
        }

        Uri endpointUri = new(endpoint, UriKind.Absolute);
        if (endpointUri.AbsolutePath.TrimEnd('/').EndsWith("/openai/v1", StringComparison.OrdinalIgnoreCase))
        {
            return endpointUri;
        }

        var endpointBuilder = new UriBuilder(endpointUri)
        {
            Path = $"{endpointUri.AbsolutePath.TrimEnd('/')}/openai/v1/",
        };

        return endpointBuilder.Uri;
    }
}
