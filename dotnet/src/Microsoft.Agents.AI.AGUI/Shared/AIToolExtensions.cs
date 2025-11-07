// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

internal static class AIToolExtensions
{
    public static IEnumerable<AGUITool> AsAGUITools(this IEnumerable<AITool> tools)
    {
        if (tools is null)
        {
            yield break;
        }

        foreach (var tool in tools)
        {
            // Convert both AIFunctionDeclaration and AIFunction (which extends it) to AGUITool
            // For AIFunction, we send only the metadata (Name, Description, JsonSchema)
            // The actual executable implementation stays on the client side
            if (tool is AIFunctionDeclaration function)
            {
                yield return new AGUITool
                {
                    Name = function.Name,
                    Description = function.Description,
                    Parameters = function.JsonSchema
                };
            }
        }
    }

    public static IEnumerable<AITool> AsAITools(this IEnumerable<AGUITool> tools)
    {
        if (tools is null)
        {
            yield break;
        }

        foreach (var tool in tools)
        {
            // Create a function declaration from the AG-UI tool definition
            // Note: These are declaration-only and cannot be invoked, as the actual
            // implementation exists on the client side
            yield return AIFunctionFactory.CreateDeclaration(
                name: tool.Name,
                description: tool.Description,
                jsonSchema: tool.Parameters);
        }
    }
}
