# Copyright (c) Microsoft. All rights reserved.

# ruff:file-ignore[implicit-namespace-package, undocumented-public-class, undocumented-public-method]

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from validate_agent_skill_links import validate_agent_skill_links


class ValidateAgentSkillLinksTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.skills = self.root / "skills"
        self.skill = self.skills / "example-skill"
        self.skill.mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_skill(self, body: str) -> None:
        (self.skill / "SKILL.md").write_text(body, encoding="utf-8")

    def test_accepts_regular_file_inside_skill(self) -> None:
        (self.skill / "references").mkdir()
        (self.skill / "references" / "details.md").write_text("# Details\n", encoding="utf-8")
        self.write_skill("[Details](references/details.md)\n")

        self.assertEqual([], validate_agent_skill_links(self.skills))

    def test_accepts_reference_style_file_inside_skill(self) -> None:
        (self.skill / "references").mkdir()
        (self.skill / "references" / "details.md").write_text("# Details\n", encoding="utf-8")
        self.write_skill("[Details][resource]\n\n[resource]: references/details.md\n")

        self.assertEqual([], validate_agent_skill_links(self.skills))

    def test_accepts_remote_links_mailto_and_anchors(self) -> None:
        self.write_skill(
            "[HTTP](http://example.com)\n"
            "[HTTPS][secure]\n"
            "[Email](mailto:agent@example.com)\n"
            "[Section](#section)\n"
            "\n"
            "[secure]: https://example.com\n"
        )

        self.assertEqual([], validate_agent_skill_links(self.skills))

    def test_rejects_parent_traversal(self) -> None:
        (self.skills / "outside.md").write_text("# Outside\n", encoding="utf-8")
        self.write_skill("[Outside](../outside.md)\n")

        errors = validate_agent_skill_links(self.skills)

        self.assertTrue(any("escapes skill root" in error for error in errors))

    def test_rejects_reference_style_parent_traversal(self) -> None:
        (self.skills / "outside.md").write_text("# Outside\n", encoding="utf-8")
        self.write_skill("[Outside][resource]\n\n[resource]: ../outside.md\n")

        errors = validate_agent_skill_links(self.skills)

        self.assertTrue(any("escapes skill root" in error for error in errors))

    def test_rejects_absolute_path(self) -> None:
        absolute_file = self.root / "outside.md"
        absolute_file.write_text("# Outside\n", encoding="utf-8")
        self.write_skill(f"[Outside]({absolute_file})\n")

        errors = validate_agent_skill_links(self.skills)

        self.assertTrue(any("absolute local link" in error for error in errors))

    def test_rejects_directory_target(self) -> None:
        (self.skill / "references").mkdir()
        self.write_skill("[References](references)\n")

        errors = validate_agent_skill_links(self.skills)

        self.assertTrue(any("not a regular file" in error for error in errors))

    def test_rejects_symlink_target(self) -> None:
        target = self.skill / "details.md"
        target.write_text("# Details\n", encoding="utf-8")
        (self.skill / "linked.md").symlink_to(target)
        self.write_skill("[Details](linked.md)\n")

        errors = validate_agent_skill_links(self.skills)

        self.assertTrue(any("not a regular file" in error for error in errors))

    def test_rejects_file_uri(self) -> None:
        self.write_skill("[Outside](file:///tmp/outside.md)\n")

        errors = validate_agent_skill_links(self.skills)

        self.assertTrue(any("unsupported URI scheme" in error for error in errors))

    def test_rejects_unknown_uri_scheme(self) -> None:
        self.write_skill("[Outside](custom://example/resource)\n")

        errors = validate_agent_skill_links(self.skills)

        self.assertTrue(any("unsupported URI scheme" in error for error in errors))

    def test_rejects_missing_target(self) -> None:
        self.write_skill("[Missing](references/missing.md)\n")

        errors = validate_agent_skill_links(self.skills)

        self.assertTrue(any("missing local resource" in error for error in errors))

    def test_accepts_percent_encoded_space_like_angle_bracket_path(self) -> None:
        references = self.skill / "references"
        references.mkdir()
        (references / "guide file.md").write_text("# Details\n", encoding="utf-8")
        self.write_skill(
            "[Angle](<references/guide file.md>)\n"
            "[Encoded](references/guide%20file.md)\n"
        )

        self.assertEqual([], validate_agent_skill_links(self.skills))

    def test_accepts_percent_encoded_space_in_reference_definition(self) -> None:
        references = self.skill / "references"
        references.mkdir()
        (references / "guide file.md").write_text("# Details\n", encoding="utf-8")
        self.write_skill("[Details][resource]\n\n[resource]: references/guide%20file.md\n")

        self.assertEqual([], validate_agent_skill_links(self.skills))

    def test_accepts_percent_encoded_hash_in_filename(self) -> None:
        references = self.skill / "references"
        references.mkdir()
        (references / "guide#file.md").write_text("# Details\n", encoding="utf-8")
        self.write_skill("[Details](references/guide%23file.md)\n")

        self.assertEqual([], validate_agent_skill_links(self.skills))

    def test_rejects_missing_percent_encoded_resource(self) -> None:
        self.write_skill("[Missing](references/guide%20missing.md)\n")

        errors = validate_agent_skill_links(self.skills)

        self.assertTrue(
            any("missing local resource: references/guide%20missing.md" in error for error in errors)
        )

    def test_rejects_percent_encoded_absolute_path_inside_skill(self) -> None:
        details = self.skill / "references" / "details.md"
        details.parent.mkdir()
        details.write_text("# Details\n", encoding="utf-8")
        encoded = quote(str(details.resolve()), safe="")
        self.write_skill(f"[Details]({encoded})\n")

        errors = validate_agent_skill_links(self.skills)

        self.assertTrue(
            any(f"absolute local link is not allowed: {encoded}" in error for error in errors)
        )


if __name__ == "__main__":
    unittest.main()
