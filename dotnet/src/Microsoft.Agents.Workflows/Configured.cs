// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Provides methods for creating <see cref="Configured{TSubject}"/> instances.
/// </summary>
public static class Configured
{
    /// <summary>
    /// Creates a <see cref="Configured{TSubject}"/> instance from an existing subject instance.
    /// </summary>
    /// <param name="subject">
    /// The subject instance. If the subject implements <see cref="IIdentified"/>, its ID will be used
    /// and checked against the provided ID (if any).
    /// </param>
    /// <param name="id">
    /// A unique identifier for the configured subject. This is required if the subject does not implement
    /// <see cref="IIdentified"/>
    /// </param>
    /// <param name="raw">
    /// The raw representation of the subject instance.
    /// </param>
    /// <returns></returns>
    public static Configured<TSubject> FromInstance<TSubject>(TSubject subject, string? id = null, object? raw = null)
    {
        if (subject is IIdentified identified)
        {
            if (id is not null && identified.Id != id)
            {
                throw new ArgumentException($"Provided ID '{id}' does not match subject's ID '{identified.Id}'.", nameof(id));
            }

            return new Configured<TSubject>(_ => new(subject), id: identified.Id, raw: raw ?? subject);
        }

        if (id is null)
        {
            throw new ArgumentNullException(nameof(id), "ID must be provided when the subject does not implement IIdentified.");
        }

        return new Configured<TSubject>(_ => new(subject), id, raw: raw ?? subject);
    }
}

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
    /// Gets the raw representation of the configured object, if any.
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

            if (this.Id is not null && subject is IIdentified identified && identified.Id != this.Id)
            {
                throw new InvalidOperationException($"Created instance ID '{identified.Id}' does not match configured ID '{this.Id}'.");
            }

            return subject;
        }
    }

    /// <summary>
    /// Memoizes and erases the typed configuration options for the subject.
    /// </summary>
    public Configured<TSubject> Memoize() => new(this.CreateValidatingMemoizedFactory(), this.Id);
}
