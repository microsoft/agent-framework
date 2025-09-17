// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.Workflows.Checkpointing;

/// <summary>
/// Defines methods for marshalling and unmarshalling objects to and from a wire format.
/// </summary>
/// <typeparam name="TWireContainer"></typeparam>
public interface IWireMarshaller<TWireContainer>
{
    /// <summary>
    /// Marshals the specified value of the given type into a wire format container.
    /// </summary>
    /// <param name="value"></param>
    /// <param name="type"></param>
    /// <returns></returns>
    TWireContainer Marshal(object value, Type type);

    /// <summary>
    /// Marshals the specified value into a wire format container.
    /// </summary>
    /// <typeparam name="TValue"></typeparam>
    /// <param name="value"></param>
    /// <returns></returns>
    TWireContainer Marshal<TValue>(TValue value);

    /// <summary>
    /// Unmarshals the specified wire format container into an object of the given type.
    /// </summary>
    /// <typeparam name="TValue"></typeparam>
    /// <param name="data"></param>
    /// <returns></returns>
    TValue Marshal<TValue>(TWireContainer data);

    /// <summary>
    /// Unmarshals the specified wire format container into an object of the specified target type.
    /// </summary>
    /// <param name="targetType"></param>
    /// <param name="data"></param>
    /// <returns></returns>
    object Marshal(Type targetType, TWireContainer data);
}
