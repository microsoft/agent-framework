// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Checkpointing;

internal class TypeId(Type type)
{
    public string AssemblyName => Throw.IfNull(type.Assembly.FullName);
    public string TypeName => Throw.IfNull(type.FullName);

    public bool IsMatch(Type type)
    {
        return this.AssemblyName == type.Assembly.FullName
            && this.TypeName == type.FullName;
    }

    public bool IsMatch<T>() => this.IsMatch(typeof(T));
}
