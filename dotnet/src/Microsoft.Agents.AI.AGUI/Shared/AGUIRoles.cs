// Copyright (c) Microsoft. All rights reserved.

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

internal static class AGUIRoles
{
    public const string System = "system";

    public const string User = "user";

    public const string Assistant = "assistant";

    public const string Developer = "developer";

    public const string Tool = "tool";
}
