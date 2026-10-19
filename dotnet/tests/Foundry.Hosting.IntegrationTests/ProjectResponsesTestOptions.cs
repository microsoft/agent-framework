// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel.Primitives;
using OpenAI.Responses;

namespace Foundry.Hosting.IntegrationTests;

internal static class ProjectResponsesTestOptions
{
    internal static CreateResponseOptions Create()
    {
        CreateResponseOptions options = new();
#pragma warning disable SCME0001 // Type is for evaluation purposes only and is subject to change or removal in future updates.
        // ProjectResponsesClient reads extension properties from Patch before sending.
        // OpenAI 2.13.0 leaves Patch propagators uninitialized until a raw JSON value is assigned.
        options.Patch = new JsonPatch("{}"u8.ToArray());
#pragma warning restore SCME0001
        return options;
    }
}
