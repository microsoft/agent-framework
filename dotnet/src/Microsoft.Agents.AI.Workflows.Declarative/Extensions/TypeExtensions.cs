// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Workflows.Declarative.Extensions;

internal static class TypeExtensions
{
    public static bool IsNullable(this Type type)
    {
        if (!type.IsValueType)
        {
            return true; // Reference types are nullable
        }

        return Nullable.GetUnderlyingType(type) != null;
    }
}
