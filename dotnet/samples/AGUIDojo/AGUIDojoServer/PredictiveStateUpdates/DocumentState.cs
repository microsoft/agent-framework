<<<<<<< HEAD
<<<<<<< HEAD
﻿// Copyright (c) Microsoft. All rights reserved.
=======
// Copyright (c) Microsoft. All rights reserved.
>>>>>>> beabff3e (Update the dojo samples)
=======
﻿// Copyright (c) Microsoft. All rights reserved.
>>>>>>> 660dee85 (cleanups)

using System.Text.Json.Serialization;

namespace AGUIDojoServer.PredictiveStateUpdates;

internal sealed class DocumentState
{
    [JsonPropertyName("document")]
    public string Document { get; set; } = string.Empty;
}
