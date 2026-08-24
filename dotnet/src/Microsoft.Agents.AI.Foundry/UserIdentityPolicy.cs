// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Foundry;

/// <summary>
/// Pipeline policy that stamps <c>x-ms-user-identity</c> from <see cref="UserIdentityScope"/>
/// onto outbound OpenAI Responses requests.
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

        message.Request.Headers.Set("x-ms-user-identity", identity);
    }
}
