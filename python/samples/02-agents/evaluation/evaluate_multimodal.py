# Copyright (c) Microsoft. All rights reserved.

"""Evaluate multimodal (image) conversations locally.

Demonstrates that the evaluation pipeline preserves image content:
1. Build EvalItems with image content in conversations
2. Use @evaluator checks that inspect multimodal content
3. Verify images flow through the eval pipeline intact

Usage:
    uv run python samples/02-agents/evaluation/evaluate_multimodal.py
"""

import asyncio
import base64

from agent_framework import (
    Content,
    EvalItem,
    LocalEvaluator,
    Message,
    evaluator,
)

# -- Custom evaluators that inspect multimodal content --


@evaluator
def has_image_content(conversation: list) -> bool:
    """Check that the conversation contains at least one image."""
    return any(
        c.type in ("data", "uri") and c.media_type and c.media_type.startswith("image/")
        for m in conversation
        for c in (m.contents or [])
    )


@evaluator
def response_describes_image(response: str) -> bool:
    """Check that the assistant response acknowledges the image."""
    image_words = {"image", "picture", "photo", "shows", "depicts", "see"}
    return any(word in response.lower() for word in image_words)


@evaluator
def image_count(conversation: list) -> float:
    """Return the number of images in the conversation as a score."""
    count = sum(
        1
        for m in conversation
        for c in (m.contents or [])
        if c.type in ("data", "uri") and c.media_type and c.media_type.startswith("image/")
    )
    return float(count)


# A tiny 1x1 red PNG for demonstration (no external dependencies needed)
_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
)


async def main() -> None:
    # Build eval items with multimodal content (no agent run needed)
    items = [
        # Item 1: User sends an image URL with a question
        EvalItem(
            conversation=[
                Message(
                    "user",
                    [
                        Content.from_text("What do you see in this image?"),
                        Content.from_uri(
                            "https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/PNG_transparency_demonstration_1.png/300px-PNG_transparency_demonstration_1.png",
                            media_type="image/png",
                        ),
                    ],
                ),
                Message("assistant", ["The image shows two dice on a transparent background."]),
            ]
        ),
        # Item 2: User sends inline image bytes
        EvalItem(
            conversation=[
                Message(
                    "user",
                    [
                        Content.from_text("Describe this picture"),
                        Content.from_data(data=_TINY_PNG, media_type="image/png"),
                    ],
                ),
                Message("assistant", ["I see a small red image — it appears to be a single pixel."]),
            ]
        ),
        # Item 3: Text-only conversation (should fail has_image_content)
        EvalItem(
            conversation=[
                Message("user", ["Tell me about cats"]),
                Message("assistant", ["Cats are wonderful pets."]),
            ]
        ),
    ]

    local = LocalEvaluator(
        has_image_content,
        response_describes_image,
        image_count,
    )

    results = await local.evaluate(items)

    print(f"\n{results.provider}: {results.passed}/{results.total} passed")
    for item in results.items:
        print(f"\n  [{item.status}] Q: {item.input_text[:60]}...")
        for score in item.scores:
            symbol = "PASS" if score.passed else "FAIL"
            print(f"    {symbol} {score.name}: {score.score}")


if __name__ == "__main__":
    asyncio.run(main())
