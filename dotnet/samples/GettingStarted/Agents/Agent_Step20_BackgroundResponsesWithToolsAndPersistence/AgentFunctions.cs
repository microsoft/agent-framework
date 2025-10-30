// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using Microsoft.Extensions.AI;

internal sealed class AgentFunctions
{
    /// <summary>
    /// Researches relevant space facts.
    /// </summary>
    /// <param name="topic">The specific space-related topic to research (e.g., "galaxy formation", "space travel", "astronaut training").</param>
    /// <returns>Research findings about the specified space topic.</returns>
    [Description("Researches relevant space facts and scientific information for writing a science fiction novel")]
    public string ResearchSpaceFacts(string topic)
    {
        Console.WriteLine($"[ResearchSpaceFacts] Researching topic: {topic}");

        // Simulate a research operation
        Thread.Sleep(TimeSpan.FromSeconds(10));

        string result = topic.ToUpperInvariant() switch
        {
            var t when t.Contains("GALAXY") => "Research findings: Galaxies contain billions of stars. Uncharted galaxies may have unique stellar formations, exotic matter, and unexplored phenomena like dark energy concentrations.",
            var t when t.Contains("SPACE") || t.Contains("TRAVEL") => "Research findings: Interstellar travel requires advanced propulsion systems. Challenges include radiation exposure, life support, and navigation through unknown space.",
            var t when t.Contains("ASTRONAUT") => "Research findings: Astronauts undergo rigorous training in zero-gravity environments, emergency protocols, spacecraft systems, and team dynamics for long-duration missions.",
            _ => $"Research findings: General space exploration facts related to {topic}. Deep space missions require advanced technology, crew resilience, and contingency planning for unknown scenarios."
        };

        Console.WriteLine("[ResearchSpaceFacts] Research complete");
        return result;
    }

    /// <summary>
    /// Generates detailed character profiles for the main characters.
    /// </summary>
    /// <returns>Detailed character profiles including background, personality traits, and role in the story.</returns>
    [Description("Generates character profiles for the main astronaut characters in the novel")]
    public IEnumerable<string> GenerateCharacterProfiles()
    {
        Console.WriteLine("[GenerateCharacterProfiles] Generating character profiles...");

        // Simulate a character generation operation
        Thread.Sleep(TimeSpan.FromSeconds(10));

        string[] profiles = [
            "Captain Elena Voss: A seasoned mission commander with 15 years of experience. Strong-willed and decisive, she struggles with the weight of responsibility for her crew. Former military pilot turned astronaut.",
            "Dr. James Chen: Chief science officer and astrophysicist. Brilliant but socially awkward, he finds solace in data and discovery. His curiosity often pushes the mission into uncharted territory.",
            "Lieutenant Maya Torres: Navigation specialist and youngest crew member. Optimistic and tech-savvy, she brings fresh perspective and innovative problem-solving to challenges.",
            "Commander Marcus Rivera: Chief engineer with expertise in spacecraft systems. Pragmatic and resourceful, he can fix almost anything with limited resources. Values crew safety above all.",
            "Dr. Amara Okafor: Medical officer and psychologist. Empathetic and observant, she helps maintain crew morale and mental health during the long journey. Expert in space medicine."
        ];

        Console.WriteLine($"[GenerateCharacterProfiles] Generated {profiles.Length} character profiles");
        return profiles;
    }

    /// <summary>
    /// Returns the functions as AI tools.
    /// </summary>
    public IEnumerable<AITool> AsAITools()
    {
        yield return AIFunctionFactory.Create(this.ResearchSpaceFacts);
        yield return AIFunctionFactory.Create(this.GenerateCharacterProfiles);
    }
}
