// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Represents the status of an asynchronous run.
/// </summary>
public readonly struct NewResponseStatus : IEquatable<NewResponseStatus>
{
    /// <summary>
    /// Gets the <see cref="NewResponseStatus"/> that represents an operation which has been queued.
    /// </summary>
    public static NewResponseStatus Queued { get; } = new("Queued");

    /// <summary>
    /// Gets the <see cref="NewResponseStatus"/> that represents an operation currently in progress.
    /// </summary>
    public static NewResponseStatus InProgress { get; } = new("InProgress");

    /// <summary>
    ///  Gets the <see cref="NewResponseStatus"/> that represents an operation that has completed successfully.
    /// </summary>
    public static NewResponseStatus Completed { get; } = new("Completed");

    /// <summary>
    ///  Gets the <see cref="NewResponseStatus"/> that represents an operation that is incomplete or not fully processed.
    /// </summary>
    public static NewResponseStatus Incomplete { get; } = new("Incomplete");

    /// <summary>
    /// Gets the <see cref="NewResponseStatus"/> that represents an operation that is currently being cancelled.
    /// </summary>
    public static NewResponseStatus Cancelling { get; } = new("Cancelling");

    /// <summary>
    ///  Gets the <see cref="NewResponseStatus"/> that represents an operation that has cancelled before completion.
    /// </summary>
    public static NewResponseStatus Canceled { get; } = new("Canceled");

    /// <summary>
    ///  Gets the <see cref="NewResponseStatus"/> that represents an operation that has failed to complete successfully.
    /// </summary>
    public static NewResponseStatus Failed { get; } = new("Failed");

    /// <summary>
    /// Gets the <see cref="NewResponseStatus"/> that represents an operation that requires further action before it can proceed.
    /// </summary>
    public static NewResponseStatus RequiresAction { get; } = new("RequiresAction");

    /// <summary>
    /// Gets the <see cref="NewResponseStatus"/> that represents an operation that has expired.
    /// </summary>
    public static NewResponseStatus Expired { get; } = new("Expired");

    /// <summary>
    /// Gets the <see cref="NewResponseStatus"/> that represents an operation that has been rejected.
    /// </summary>
    public static NewResponseStatus Rejected { get; } = new("Rejected");

    /// <summary>
    /// Gets the <see cref="NewResponseStatus"/> that represents an operation that requires authentication.
    /// </summary>
    public static NewResponseStatus AuthRequired { get; } = new("AuthRequired");

    /// <summary>
    /// Get the <see cref="NewResponseStatus"/> that represents an operation that requires user input.
    /// </summary>
    public static NewResponseStatus InputRequired { get; } = new("InputRequired");

    /// <summary>
    /// Get the <see cref="NewResponseStatus"/> that represents an operation that is unknown or not specified.
    /// </summary>
    public static NewResponseStatus Unknown { get; } = new("Unknown");

    /// <summary>
    /// Gets the label associated with this <see cref="NewResponseStatus"/>.
    /// </summary>
    public string Label { get; }

    /// <summary>
    /// Creates a new <see cref="NewResponseStatus"/> instance with the provided label.
    /// </summary>
    /// <param name="label">The label to associate with this <see cref="NewResponseStatus"/>.</param>
    public NewResponseStatus(string label)
    {
        if (string.IsNullOrWhiteSpace(label))
        {
            throw new ArgumentException("Label cannot be null or whitespace.", nameof(label));
        }

        this.Label = label;
    }

    /// <summary>
    /// Determines whether two <see cref="NewResponseStatus"/> instances are equal.
    /// </summary>
    /// <param name="left">The first <see cref="NewResponseStatus"/> to compare.</param>
    /// <param name="right">The second <see cref="NewResponseStatus"/> to compare.</param>
    /// <returns><c>true</c> if the instances are equal; otherwise, <c>false</c>.</returns>
    public static bool operator ==(NewResponseStatus left, NewResponseStatus right)
        => left.Equals(right);

    /// <summary>
    /// Determines whether two <see cref="NewResponseStatus"/> instances are not equal.
    /// </summary>
    /// <param name="left">The first <see cref="NewResponseStatus"/> to compare.</param>
    /// <param name="right">The second <see cref="NewResponseStatus"/> to compare.</param>
    /// <returns><c>true</c> if the instances are not equal; otherwise, <c>false</c>.</returns>
    public static bool operator !=(NewResponseStatus left, NewResponseStatus right)
        => !(left == right);

    /// <summary>
    /// Determines whether the specified object is equal to the current <see cref="NewResponseStatus"/>.
    /// </summary>
    /// <param name="obj">The object to compare with the current <see cref="NewResponseStatus"/>.</param>
    /// <returns><c>true</c> if the specified object is equal to the current <see cref="NewResponseStatus"/>; otherwise, <c>false</c>.</returns>
    public override bool Equals(object? obj)
        => obj is NewResponseStatus other && this == other;

    /// <summary>
    /// Determines whether the specified <see cref="NewResponseStatus"/> is equal to the current <see cref="NewResponseStatus"/>.
    /// </summary>
    /// <param name="other">The <see cref="NewResponseStatus"/> to compare with the current <see cref="NewResponseStatus"/>.</param>
    /// <returns><c>true</c> if the specified <see cref="NewResponseStatus"/> is equal to the current <see cref="NewResponseStatus"/>; otherwise, <c>false</c>.</returns>
    public bool Equals(NewResponseStatus other)
        => string.Equals(this.Label, other.Label, StringComparison.OrdinalIgnoreCase);

    /// <summary>
    /// Returns the hash code for this <see cref="NewResponseStatus"/>.
    /// </summary>
    /// <returns>A hash code for the current <see cref="NewResponseStatus"/>.</returns>
    public override int GetHashCode()
        => StringComparer.OrdinalIgnoreCase.GetHashCode(this.Label);

    /// <summary>
    /// Returns the string representation of this <see cref="NewResponseStatus"/>.
    /// </summary>
    /// <returns>The label of this <see cref="NewResponseStatus"/>.</returns>
    public override string ToString() => this.Label;
}
