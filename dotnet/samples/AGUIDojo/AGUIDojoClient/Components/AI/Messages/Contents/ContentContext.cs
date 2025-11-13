// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.AspNetCore.Components.AI;

public class ContentContext(AIContent content)
{
    public AIContent Content { get; init; } = content;
}
