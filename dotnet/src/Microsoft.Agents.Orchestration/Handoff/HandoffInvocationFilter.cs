// Copyright (c) Microsoft. All rights reserved.

//using System;
//using System.Threading.Tasks;

//namespace Microsoft.Agents.Orchestration.Handoff;

//// %%% HACK
internal sealed class HandoffInvocationFilter() //: IAutoFunctionInvocationFilter
{
    public const string HandoffPlugin = nameof(HandoffPlugin);

    //public async Task OnAutoFunctionInvocationAsync(AutoFunctionInvocationContext context, Func<AutoFunctionInvocationContext, Task> next)
    //{
    //    // Execution the function
    //    await next(context).ConfigureAwait(false);

    //    // Signal termination if the function is part of the handoff plugin
    //    if (context.Function.PluginName == HandoffPlugin)
    //    {
    //        context.Terminate = true;
    //    }
    //}
}
