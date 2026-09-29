// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Foundry;

/// <summary>
/// Pipeline policy that stamps the current session's <c>x-ms-user-identity</c> from
/// <see cref="UserIdentityScope"/> onto outbound OpenAI Responses requests.
/// </summary>
internal sealed class UserIdentityPolicy : PipelinePolicy
{
    public static UserIdentityPolicy Instance { get; } = new UserIdentityPolicy();

    private UserIdentityPolicy()
    {
    }

    public override void Process(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
    {
        Stamp(message);
        ProcessNext(message, pipeline, currentIndex);
    }

    public override ValueTask ProcessAsync(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
    {
        Stamp(message);
        return ProcessNextAsync(message, pipeline, currentIndex);
    }

    private static void Stamp(PipelineMessage message)
    {
        var identity = UserIdentityScope.Current;
        if (string.IsNullOrWhiteSpace(identity))
        {
            return;
        }

        // Session state can be restored without using the binding API, so validate again at the
        // final transport boundary before the value reaches the header collection.
        HttpHeaderValidation.ValidateNoProhibitedCharacters(
            identity,
            "userIdentity",
            "User identity must not contain NUL, carriage-return, or line-feed characters.");
        message.Request.Headers.Set("x-ms-user-identity", identity);
    }
}
