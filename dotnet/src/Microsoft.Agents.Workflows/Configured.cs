// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// A representation of a preconfigured, lazy-instantiatable instance of <typeparamref name="TSubject"/>.
/// </summary>
/// <typeparam name="TSubject">The type of the preconfigured subject.</typeparam>
/// <param name="factoryAsync">A factory to intantiate the subject when desired.</param>
/// <param name="id">The unique identifier for the configured subject.</param>
/// <param name="raw"></param>
public class Configured<TSubject>(Func<Config, ValueTask<TSubject>> factoryAsync, string id, object? raw = null)
{
    /// <summary>
    /// The raw representation of the configured object, if any.
    /// </summary>
    public object? Raw => raw;

    /// <summary>
    /// Gets the configured identifier for the subject.
    /// </summary>
    public string Id => id;

    /// <summary>
    /// Gets the factory function to create an instance of <typeparamref name="TSubject"/> given a <see cref="Config"/>.
    /// </summary>
    public Func<Config, ValueTask<TSubject>> FactoryAsync => factoryAsync;

    /// <summary>
    /// The configuration for this configured instance.
    /// </summary>
    public Config Configuration => new(this.Id);

    /// <summary>
    /// Gets a "partially" applied factory function that only requires no parameters to create an instance of
    /// <typeparamref name="TSubject"/> with the provided <see cref="Configuration"/> instance.
    /// </summary>
    internal Func<ValueTask<TSubject>> BoundFactoryAsync => () => this.FactoryAsync(this.Configuration);
}

/// <summary>
/// A representation of a preconfigured, lazy-instantiatable instance of <typeparamref name="TSubject"/>.
/// </summary>
/// <typeparam name="TSubject">The type of the preconfigured subject.</typeparam>
/// <typeparam name="TOptions">The type of configuration options for the preconfigured subject.</typeparam>
/// <param name="factoryAsync">A factory to intantiate the subject when desired.</param>
/// <param name="id">The unique identifier for the configured subject.</param>
/// <param name="options">Additional configuration options for the subject.</param>
/// <param name="raw"></param>
public class Configured<TSubject, TOptions>(Func<Config<TOptions>, ValueTask<TSubject>> factoryAsync, string id, TOptions? options = default, object? raw = null)
{
    /// <summary>
    /// The raw representation of the configured object, if any.
    /// </summary>
    public object? Raw => raw;

    /// <summary>
    /// Gets the configured identifier for the subject.
    /// </summary>
    public string Id => id;

    /// <summary>
    /// Gets the options associated with this instance.
    /// </summary>
    public TOptions? Options => options;

    /// <summary>
    /// Gets the factory function to create an instance of <typeparamref name="TSubject"/> given a <see cref="Config{TOptions}"/>.
    /// </summary>
    public Func<Config<TOptions>, ValueTask<TSubject>> FactoryAsync => factoryAsync;

    /// <summary>
    /// The configuration for this configured instance.
    /// </summary>
    public Config<TOptions> Configuration => new(this.Options, this.Id);

    /// <summary>
    /// Gets a "partially" applied factory function that only requires no parameters to create an instance of
    /// <typeparamref name="TSubject"/> with the provided <see cref="Configuration"/> instance.
    /// </summary>
    internal Func<ValueTask<TSubject>> BoundFactoryAsync => () => this.CreateValidatingMemoizedFactory()(this.Configuration);

    private Func<Config, ValueTask<TSubject>> CreateValidatingMemoizedFactory()
    {
        return FactoryAsync;

        async ValueTask<TSubject> FactoryAsync(Config configuration)
        {
            if (this.Id != configuration.Id)
            {
                throw new InvalidOperationException($"Requested instance ID '{configuration.Id}' does not match configured ID '{this.Id}'.");
            }

            TSubject subject = await this.FactoryAsync(this.Configuration).ConfigureAwait(false);

            if (this.Id != null && subject is IIdentified identified && identified.Id != this.Id)
            {
                throw new InvalidOperationException($"Created instance ID '{identified.Id}' does not match configured ID '{this.Id}'.");
            }

            return subject;
        }
    }

    /// <summary>
    /// Memoizes erases the typed configuration options for the subject.
    /// </summary>
    public Configured<TSubject> Memoize() => new(this.CreateValidatingMemoizedFactory(), this.Id);
}
