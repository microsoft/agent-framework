// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.Extensions;

internal static class PropertyPathExtensions
{
    public static string Format(this PropertyPath path) => string.Join(".", path.Segments());
}
