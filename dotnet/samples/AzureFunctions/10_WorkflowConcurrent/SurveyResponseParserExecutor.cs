//// Copyright (c) Microsoft. All rights reserved.

//using System.Text.Json;
//using System.Text.RegularExpressions;
//using Microsoft.Agents.AI.Workflows;

//namespace SingleAgent;

///// <summary>
///// This executor parses survey responses and produces structured output.
///// Example input: "Rating: 8. The app is good but checkout process is confusing."
///// </summary>
//[System.Diagnostics.CodeAnalysis.SuppressMessage("Performance", "CA1812:Avoid uninstantiated internal classes", Justification = "Instantiated by workflow framework")]
//internal sealed partial class SurveyResponseParserExecutor() : Executor<string, string>("SurveyResponseParserExecutor")
//{
//    private static readonly JsonSerializerOptions s_jsonOptions = new()
//    {
//        WriteIndented = true
//    };

//    [GeneratedRegex(@"Rating:\s*(\d+)", RegexOptions.IgnoreCase)]
//    private static partial Regex RatingRegex();

//    public override ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
//    {
//        SurveyResponse response = this.ParseSurveyResponse(message);
//        string jsonResult = JsonSerializer.Serialize(response, s_jsonOptions);
//        return ValueTask.FromResult(jsonResult);
//    }

//    private SurveyResponse ParseSurveyResponse(string message)
//    {
//        // Parse the message to extract rating and comment
//        int? rating = null;
//        string comment = message;

//        // Try to extract rating using pattern "Rating: {number}"
//        Match ratingMatch = RatingRegex().Match(message);
//        if (ratingMatch.Success && int.TryParse(ratingMatch.Groups[1].Value, out int parsedRating))
//        {
//            rating = parsedRating;

//            // Remove the rating part from the message to get the comment
//            // Find the position after the rating number
//            int ratingEndIndex = ratingMatch.Index + ratingMatch.Length;

//            // Skip any separators (period, comma, dash, etc.) and whitespace
//            while (ratingEndIndex < message.Length &&
//                   (char.IsWhiteSpace(message[ratingEndIndex]) ||
//                    message[ratingEndIndex] == '.' ||
//                    message[ratingEndIndex] == ',' ||
//                    message[ratingEndIndex] == '-'))
//            {
//                ratingEndIndex++;
//            }

//            if (ratingEndIndex < message.Length)
//            {
//                comment = message[ratingEndIndex..].Trim();
//            }
//            else
//            {
//                comment = string.Empty;
//            }
//        }

//        // Create and return the structured response
//        return new SurveyResponse
//        {
//            Rating = rating,
//            Comment = comment,
//            OriginalMessage = message
//        };
//    }

//    private sealed class SurveyResponse
//    {
//        public int? Rating { get; set; }
//        public string Comment { get; set; } = string.Empty;
//        public string OriginalMessage { get; set; } = string.Empty;
//    }
//}
