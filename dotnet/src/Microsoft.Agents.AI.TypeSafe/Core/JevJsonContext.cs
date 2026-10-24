// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Source-generated serialization metadata for the Jev contract types.
/// </summary>
/// <remarks>
/// Models often write the <c>type</c> discriminator after other properties of a question, so out-of-order metadata
/// is allowed; without it, a valid question such as <c>{"instructions": "...", "type": "noul"}</c> would be rejected.
/// </remarks>
[JsonSourceGenerationOptions(AllowOutOfOrderMetadataProperties = true)]
[JsonSerializable(typeof(JevRequest))]
[JsonSerializable(typeof(JevResult))]
[JsonSerializable(typeof(JevApiRequest))]
[JsonSerializable(typeof(Dictionary<string, JevQuestion>))]
[JsonSerializable(typeof(string))]
internal sealed partial class JevJsonContext : JsonSerializerContext;
