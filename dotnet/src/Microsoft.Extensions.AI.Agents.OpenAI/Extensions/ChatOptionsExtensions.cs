// Copyright (c) Microsoft. All rights reserved.
using Microsoft.Shared.Diagnostics;
using OpenAI.Responses;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Extension methods for <see cref="ChatOptions"/>
/// </summary>
public static class ChatOptionsExtensions
{
    /// <summary>
    /// Disables the storage of response output in the chat options.
    /// </summary>
    /// <param name="options">Instance of <see cref="ChatOptions"/></param>
    /// <exception cref="ArgumentNullException"></exception>
    public static ChatOptions WithResponseStoredOutputDisabled(this ChatOptions options)
    {
        Throw.IfNull(options);

        // We can use the RawRepresentationFactory to provide Response service specific
        // options. Here we can indicate that we do not want the service to store the
        // conversation in a service managed thread.
        options.RawRepresentationFactory = (_) => new ResponseCreationOptions() { StoredOutputEnabled = false };

        return options;
    }
}
