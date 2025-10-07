// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Reflection;
using Microsoft.Shared.Diagnostics;
using OpenAI.Responses;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Utils;

[System.Diagnostics.CodeAnalysis.SuppressMessage("Performance", "CA1810:Initialize reference type static fields inline", Justification = "Specifically for accessing hidden members")]
[System.Diagnostics.CodeAnalysis.SuppressMessage("Design", "CA1065:Do not raise exceptions in unexpected locations", Justification = "Specifically for accessing hidden members")]
internal static class ResponseItemExtensions
{
    private static readonly Action<ResponseItem, string> _setId;

    static ResponseItemExtensions()
    {
        // OpenAI SDK ResponseItem has an internal setter for Id property.
        // We need to access it via reflection to set the Id when creating response items.

        // --- Id (public string Id { get; internal set; }) ---
        const string idPropName = "Id";
        var idProp = typeof(ResponseItem).GetProperty(idPropName, BindingFlags.Instance | BindingFlags.Public)
            ?? throw new MissingMemberException(typeof(ResponseItem).FullName!, idPropName);
        var idSetter = idProp.GetSetMethod(nonPublic: true) ?? throw new MissingMethodException($"{idPropName} setter not found.");

        _setId = idSetter.CreateDelegate<Action<ResponseItem, string>>();
    }

    /// <summary>
    /// Sets the Id property on a ResponseItem using reflection to access the internal setter.
    /// </summary>
    /// <param name="responseItem">The ResponseItem to set the Id on.</param>
    /// <param name="id">The Id value to set.</param>
    public static void SetId(this ResponseItem responseItem, string id)
    {
        Throw.IfNull(responseItem);
        _setId(responseItem, id);
    }
}
