// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Configuration options for Executor behavior.
/// </summary>
public class ExecutorOptions
{
    /// <summary>
    /// The default runner configuration.
    /// </summary>
    public static ExecutorOptions Default { get; } = new();

    internal ExecutorOptions() { }

    /// <summary>
    /// If <see langword="true"/>, the result of a message handler that returns a value will be sent as a message from the executor.
    /// </summary>
    /// <remarks>
    /// <para>Default: <see langword="true"/>. When enabled, handler return types are automatically registered
    /// as sent message types in the protocol. At runtime, <see cref="ProtocolBuilder.Build(ExecutorOptions)"/>
    /// unions <c>router.DefaultOutputTypes</c> into the send type set.</para>
    /// <para>Specialized base classes may override this default. For example, <c>ChatProtocolExecutor</c> and
    /// <c>RequestInfoExecutor</c> set this to <see langword="false"/>.</para>
    /// <para>Users migrating from <c>ReflectingExecutor&lt;T&gt;</c> who rely on explicit type registration
    /// should be aware that this automatic registration may add unexpected types to the protocol.</para>
    /// </remarks>
    public bool AutoSendMessageHandlerResultObject { get; set; } = true;

    /// <summary>
    /// If <see langword="true"/>, the result of a message handler that returns a value will be yielded as an output of the executor.
    /// </summary>
    /// <remarks>
    /// <para>Default: <see langword="true"/>. When enabled, handler return types are automatically registered
    /// as yielded output types in the protocol. At runtime, <see cref="ProtocolBuilder.Build(ExecutorOptions)"/>
    /// unions <c>router.DefaultOutputTypes</c> into the yield type set.</para>
    /// <para>If set to <see langword="false"/>, only types explicitly declared via <see cref="YieldsOutputAttribute"/>
    /// or the <see cref="MessageHandlerAttribute.Yield"/> property will be registered as yield types.
    /// Handler return values will not be automatically included.</para>
    /// </remarks>
    public bool AutoYieldOutputHandlerResultObject { get; set; } = true;
}
