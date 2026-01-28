# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
from typing import cast

from agent_framework import (
    AgentRunUpdateEvent,
    ChatAgent,
    ChatMessage,
    GroupChatBuilder,
    Role,
    WorkflowOutputEvent,
    tool,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential

logging.basicConfig(level=logging.WARNING)

"""
Sample: Philosophical Debate with Agent-Based Manager

What it does:
- Creates a diverse group of agents representing different global perspectives
- Uses an agent-based manager to guide a philosophical discussion
- Demonstrates longer, multi-round discourse with natural conversation flow
- Manager decides when discussion has reached meaningful conclusion

Topic: "What does a good life mean to you personally?"

Participants represent:
- Farmer from Southeast Asia (tradition, sustainability, land connection)
- Software Developer from United States (innovation, technology, work-life balance)
- History Teacher from Eastern Europe (legacy, learning, cultural continuity)
- Activist from South America (social justice, environmental rights)
- Spiritual Leader from Middle East (morality, community service)
- Artist from Africa (creative expression, storytelling)
- Immigrant Entrepreneur from Asia in Canada (tradition + adaptation)
- Doctor from Scandinavia (public health, equity, societal support)

Prerequisites:
- OpenAI environment variables configured for OpenAIChatClient
"""


def _get_chat_client() -> AzureOpenAIChatClient:
    return AzureOpenAIChatClient(credential=AzureCliCredential())


async def main() -> None:
    # Create debate moderator with structured output for speaker selection
    # Note: Participant names and descriptions are automatically injected by the orchestrator
    moderator = ChatAgent(
        name="Moderator",
        description="Guides philosophical discussion by selecting next speaker",
        instructions="""
You are a thoughtful moderator guiding a philosophical discussion on the topic handed to you by the user.

Your participants bring diverse global perspectives. Select speakers strategically to:
- Create natural conversation flow and responses to previous points
- Ensure all voices are heard throughout the discussion
- Build on themes and contrasts that emerge
- Allow for respectful challenges and counterpoints
- Guide toward meaningful conclusions

Select speakers who can:
1. Respond directly to points just made
2. Introduce fresh perspectives when needed
3. Bridge or contrast different viewpoints
4. Deepen the philosophical exploration

Finish when:
- Multiple rounds have occurred (at least 6-8 exchanges)
- Key themes have been explored from different angles
- Natural conclusion or synthesis has emerged
- Diminishing returns in new insights

In your final_message, provide a brief synthesis highlighting key themes that emerged.
""",
        chat_client=_get_chat_client(),
    )

    farmer = ChatAgent(
        name="Farmer",
        description="A rural farmer from Southeast Asia",
        instructions="""
You're a farmer from Southeast Asia. Your life is deeply connected to land and family.
You value tradition and sustainability. You are in a philosophical debate.

Share your perspective authentically. Feel free to:
- Challenge other participants respectfully
- Build on points others have made
- Use concrete examples from your experience
- Keep responses thoughtful but concise (2-4 sentences)
""",
        chat_client=_get_chat_client(),
    )

    developer = ChatAgent(
        name="Developer",
        description="An urban software developer from the United States",
        instructions="""
You're a software developer from the United States. Your life is fast-paced and technology-driven.
You value innovation, freedom, and work-life balance. You are in a philosophical debate.

Share your perspective authentically. Feel free to:
- Challenge other participants respectfully
- Build on points others have made
- Use concrete examples from your experience
- Keep responses thoughtful but concise (2-4 sentences)
""",
        chat_client=_get_chat_client(),
    )

    teacher = ChatAgent(
        name="Teacher",
        description="A retired history teacher from Eastern Europe",
        instructions="""
You're a retired history teacher from Eastern Europe. You bring historical and philosophical
perspectives to discussions. You value legacy, learning, and cultural continuity.
You are in a philosophical debate.

Share your perspective authentically. Feel free to:
- Challenge other participants respectfully
- Build on points others have made
- Use concrete examples from history or your teaching experience
- Keep responses thoughtful but concise (2-4 sentences)
""",
        chat_client=_get_chat_client(),
    )

    activist = ChatAgent(
        name="Activist",
        description="A young activist from South America",
        instructions="""
You're a young activist from South America. You focus on social justice, environmental rights,
and generational change. You are in a philosophical debate.

Share your perspective authentically. Feel free to:
- Challenge other participants respectfully
- Build on points others have made
- Use concrete examples from your activism
- Keep responses thoughtful but concise (2-4 sentences)
""",
        chat_client=_get_chat_client(),
    )

    spiritual_leader = ChatAgent(
        name="SpiritualLeader",
        description="A spiritual leader from the Middle East",
        instructions="""
You're a spiritual leader from the Middle East. You provide insights grounded in religion,
morality, and community service. You are in a philosophical debate.

Share your perspective authentically. Feel free to:
- Challenge other participants respectfully
- Build on points others have made
- Use examples from spiritual teachings or community work
- Keep responses thoughtful but concise (2-4 sentences)
""",
        chat_client=_get_chat_client(),
    )

    artist = ChatAgent(
        name="Artist",
        description="An artist from Africa",
        instructions="""
You're an artist from Africa. You view life through creative expression, storytelling,
and collective memory. You are in a philosophical debate.

Share your perspective authentically. Feel free to:
- Challenge other participants respectfully
- Build on points others have made
- Use examples from your art or cultural traditions
- Keep responses thoughtful but concise (2-4 sentences)
""",
        chat_client=_get_chat_client(),
    )

    immigrant = ChatAgent(
        name="Immigrant",
        description="An immigrant entrepreneur from Asia living in Canada",
        instructions="""
You're an immigrant entrepreneur from Asia living in Canada. You balance tradition with adaptation.
You focus on family success, risk, and opportunity. You are in a philosophical debate.

Share your perspective authentically. Feel free to:
- Challenge other participants respectfully
- Build on points others have made
- Use examples from your immigrant and entrepreneurial journey
- Keep responses thoughtful but concise (2-4 sentences)
""",
        chat_client=_get_chat_client(),
    )

    doctor = ChatAgent(
        name="Doctor",
        description="A doctor from Scandinavia",
        instructions="""
You're a doctor from Scandinavia. Your perspective is shaped by public health, equity,
and structured societal support. You are in a philosophical debate.

Share your perspective authentically. Feel free to:
- Challenge other participants respectfully
- Build on points others have made
- Use examples from healthcare and societal systems
- Keep responses thoughtful but concise (2-4 sentences)
""",
        chat_client=_get_chat_client(),
    )

    workflow = (
        GroupChatBuilder()
        .with_orchestrator(agent=moderator)
        .participants([farmer, developer, teacher, activist, spiritual_leader, artist, immigrant, doctor])
        .with_termination_condition(lambda messages: sum(1 for msg in messages if msg.role == Role.ASSISTANT) >= 10)
        .build()
    )

    topic = "What does a good life mean to you personally?"

    print("\n" + "=" * 80)
    print("PHILOSOPHICAL DEBATE: Perspectives on a Good Life")
    print("=" * 80)
    print(f"\nTopic: {topic}")
    print("\nParticipants:")
    print("  - Farmer (Southeast Asia)")
    print("  - Developer (United States)")
    print("  - Teacher (Eastern Europe)")
    print("  - Activist (South America)")
    print("  - SpiritualLeader (Middle East)")
    print("  - Artist (Africa)")
    print("  - Immigrant (Asia → Canada)")
    print("  - Doctor (Scandinavia)")
    print("\n" + "=" * 80)
    print("DISCUSSION BEGINS")
    print("=" * 80 + "\n")

    final_conversation: list[ChatMessage] = []
    current_speaker: str | None = None

    async for event in workflow.run_stream(f"Please begin the discussion on: {topic}"):
        if isinstance(event, AgentRunUpdateEvent):
            if event.executor_id != current_speaker:
                if current_speaker is not None:
                    print("\n")
                print(f"[{event.executor_id}]", flush=True)
                current_speaker = event.executor_id

            print(event.data, end="", flush=True)

        elif isinstance(event, WorkflowOutputEvent):
            final_conversation = cast(list[ChatMessage], event.data)

    print("\n\n" + "=" * 80)
    print("DISCUSSION SUMMARY")
    print("=" * 80)

    if final_conversation and isinstance(final_conversation, list) and final_conversation:
        final_msg = final_conversation[-1]
        if hasattr(final_msg, "author_name") and final_msg.author_name == "Moderator":
            print(f"\n{final_msg.text}")

    """
    Sample Output:

    ================================================================================
    PHILOSOPHICAL DEBATE: Perspectives on a Good Life
    ================================================================================

    Topic: What does a good life mean to you personally?

    Participants:
    - Farmer (Southeast Asia)
    - Developer (United States)
    - Teacher (Eastern Europe)
    - Activist (South America)
    - SpiritualLeader (Middle East)
    - Artist (Africa)
    - Immigrant (Asia → Canada)
    - Doctor (Scandinavia)

    ================================================================================
    DISCUSSION BEGINS
    ================================================================================

    [Farmer]
    To me, a good life is deeply intertwined with the rhythm of the land and the nurturing of relationships with my
    family and community. It means cultivating crops that respect our environment, ensuring sustainability for future
    generations, and sharing meals made from our harvests around the dinner table. The joy found in everyday
    tasks—planting rice or tending to our livestock—creates a sense of fulfillment that cannot be measured by material
    wealth. It's the simple moments, like sharing stories with my children under the stars, that truly define a good
    life. What good is progress if it isolates us from those we love and the land that sustains us?

    [Developer]
    As a software developer in an urban environment, a good life for me hinges on the intersection of innovation,
    creativity, and balance. It's about having the freedom to explore new technologies that can solve real-world
    problems while ensuring that my work doesn't encroach on my personal life. For instance, I value remote work
    flexibility, which allows me to maintain connections with family and friends, similar to how the Farmer values
    community. While our lifestyles may differ markedly, both of us seek fulfillment—whether through meaningful work or
    rich personal experiences. The challenge is finding harmony between technological progress and preserving the
    intimate human connections that truly enrich our lives.

    [SpiritualLeader]
    From my spiritual perspective, a good life embodies a balance between personal fulfillment and service to others,
    rooted in compassion and community. In our teachings, we emphasize that true happiness comes from helping those in
    need and fostering strong connections with our families and neighbors. Whether it's the Farmer nurturing the earth
    or the Developer creating tools to enhance lives, both contribute to the greater good. The essence of a good life
    lies in our intentions and actions—finding ways to serve our communities, spread kindness, and live harmoniously
    with those around us. Ultimately, as we align our personal beliefs with our communal responsibilities, we cultivate
    a richness that transcends material wealth.

    [Activist]
    As a young activist in South America, a good life for me is about advocating for social justice and environmental
    sustainability. It means living in a society where everyone's rights are respected and where marginalized voices,
    particularly those of Indigenous communities, are amplified. I see a good life as one where we work collectively to
    dismantle oppressive systems—such as deforestation and inequality—while nurturing our planet. For instance, through
    my activism, I've witnessed the transformative power of community organizing, where collective efforts lead to real
    change, like resisting destructive mining practices that threaten our rivers and lands. A good life, therefore, is
    not just lived for oneself but is deeply tied to the well-being of our communities and the health of our
    environment. How can we, regardless of our backgrounds, collaborate to foster these essential changes?

    [Teacher]
    As a retired history teacher from Eastern Europe, my understanding of a good life is deeply rooted in the lessons
    drawn from history and the struggle for freedom and dignity. Historical events, such as the fall of the Iron
    Curtain, remind us of the profound importance of liberty and collective resilience. A good life, therefore, is about
    cherishing our freedoms and working towards a society where everyone has a voice, much as my students and I
    discussed the impacts of totalitarian regimes. Additionally, I believe it involves fostering cultural continuity,
    where we honor our heritage while embracing progressive values. We must learn from the past—especially the
    consequences of neglecting empathy and solidarity—so that we can cultivate a future that values every individual's
    contributions to the rich tapestry of our shared humanity. How can we ensure that the lessons of history inform a
    more compassionate and just society moving forward?

    [Artist]
    As an artist from Africa, I define a good life as one steeped in cultural expression, storytelling, and the
    celebration of our collective memories. Art is a powerful medium through which we capture our histories, struggles,
    and triumphs, creating a tapestry that connects generations. For instance, in my work, I often draw from folktales
    and traditional music, weaving narratives that reflect the human experience, much like how the retired teacher
    emphasizes learning from history. A good life involves not only personal fulfillment but also the responsibility to
    share our narratives and use our creativity to inspire change, whether addressing social injustices or environmental
    issues. It's in this interplay of art and activism that we can transcend individual existence and contribute to a
    collective good, fostering empathy and understanding among diverse communities. How can we harness art to bridge
    differences and amplify marginalized voices in our pursuit of a good life?

    ================================================================================
    DISCUSSION SUMMARY
    ================================================================================

    As our discussion unfolds, several key themes have gracefully emerged, reflecting the richness of diverse
    perspectives on what constitutes a good life. From the rural farmer's integration with the land to the developer's
    search for balance between technology and personal connection, each viewpoint validates that fulfillment, at its
    core, transcends material wealth. The spiritual leader and the activist highlight the importance of community and
    social justice, while the history teacher and the artist remind us of the lessons and narratives that shape our
    cultural and personal identities.

    Ultimately, the good life seems to revolve around meaningful relationships, honoring our legacies while striving for
    progress, and nurturing both our inner selves and external communities. This dialogue demonstrates that despite our
    varied backgrounds and experiences, the quest for a good life binds us together, urging cooperation and empathy in
    our shared human journey.
    """


if __name__ == "__main__":
    asyncio.run(main())
