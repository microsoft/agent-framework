// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal class InitLocked<T>() where T : class
{
    private int _writers;
    private T? _value;

    public T? Get()
    {
        return this._value;
    }

    public bool Init(Func<T> initializer)
    {
        if (Interlocked.Exchange(ref this._writers, 1) == 0)
        {
            try
            {
                if (this._value == null)
                {
                    this._value = initializer();
                    return true;
                }

                return false;
            }
            finally
            {
                this._writers = 0;
            }
        }

        return false;
    }

    public void Clear()
    {
        this._value = null;
    }
}
