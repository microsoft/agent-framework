// Copyright (c) Microsoft. All rights reserved.

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

internal sealed class AGUIDeveloperMessage : AGUIMessage
{
    public AGUIDeveloperMessage()
    {
        this.Role = AGUIRoles.Developer;
    }
}
