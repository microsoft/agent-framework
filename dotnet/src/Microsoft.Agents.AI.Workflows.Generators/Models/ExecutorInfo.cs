// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows.Generators.Models;

/// <summary>
/// Contains all information needed to generate code for an executor class.
/// Uses record for automatic value equality, which is required for incremental generator caching.
/// </summary>
/// <param name="Namespace">The namespace of the executor class.</param>
/// <param name="ClassName">The name of the executor class.</param>
/// <param name="GenericParameters">The generic type parameters of the class (e.g., "&lt;T, U&gt;"), or null if not generic.</param>
/// <param name="IsNested">Whether the class is nested inside another class.</param>
/// <param name="ContainingTypeChain">The chain of containing types for nested classes (e.g., "OuterClass.InnerClass"). Empty string if not nested.</param>
/// <param name="BaseHasConfigureProtocol">Whether the base class has a ConfigureRoutes method that should be called.</param>
/// <param name="Handlers">The list of handler methods to register.</param>
/// <param name="ClassSendTypes">The types declared via class-level [SendsMessage] attributes.</param>
/// <param name="ClassYieldTypes">The types declared via class-level [YieldsOutput] attributes.</param>
internal sealed record ExecutorInfo(
    string? Namespace,
    string ClassName,
    string? GenericParameters,
    bool IsNested,
    string ContainingTypeChain,
    bool BaseHasConfigureProtocol,
    ImmutableEquatableArray<HandlerInfo> Handlers,
    ImmutableEquatableArray<string> ClassSendTypes,
    ImmutableEquatableArray<string> ClassYieldTypes)
{
    /// <summary>
    /// Gets whether any "Sent" message type registrations should be generated.
    /// </summary>
    public bool ShouldGenerateSentMessageRegistrations => !this.ClassSendTypes.IsEmpty || this.HasHandlerWithSendTypes;

    /// <summary>
    /// Gets whether any "Yielded" output type registrations should be generated.
    /// </summary>
    public bool ShouldGenerateYieldedOutputRegistrations => !this.ClassYieldTypes.IsEmpty || this.HasHandlerWithYieldTypes;

    /// <summary>
    /// Gets whether any handler has explicit Send types.
    /// </summary>
    public bool HasHandlerWithSendTypes
    {
        get
        {
            foreach (var handler in this.Handlers)
            {
                if (!handler.SendTypes.IsEmpty)
                {
                    return true;
                }
            }

            return false;
        }
    }

    /// <summary>
    /// Gets whether any handler has explicit Yield types or output types.
    /// </summary>
    public bool HasHandlerWithYieldTypes
    {
        get
        {
            foreach (var handler in this.Handlers)
            {
                if (!handler.YieldTypes.IsEmpty)
                {
                    return true;
                }

                if (handler.HasOutput)
                {
                    return true;
                }
            }

            return false;
        }
    }
}
