from __future__ import annotations

import copy
import json
import re
import tempfile
import textwrap
import unittest

from scripts import validate


class SelectorParameterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        expected = validate.ROOT / "examples/minimal/expected"
        cls.definitions = json.loads((expected / "definitions.json").read_text())
        cls.ruleset = json.loads((expected / "ruleset.json").read_text())

    def candidate(self) -> tuple[dict, dict]:
        ruleset = copy.deepcopy(self.ruleset)
        definitions = copy.deepcopy(self.definitions)
        for document in (ruleset, definitions):
            package = document["package"]
            if isinstance(package["name"], str):
                package["name"] = {"default": package["name"], "translations": {}}
                package["description"] = {
                    "default": package["description"],
                    "translations": {},
                }
            document.setdefault("sources", {})
        definition = definitions["definitions"]["axioval:example.property-exists"]
        definition["parameters"]["compared"] = {
            "id": "compared",
            "name": {"default": "Compared objects", "translations": {}},
            "kind": "selector",
            "required": True,
            "allowedValues": [],
        }
        ruleset["root"]["rules"][0]["parameters"]["compared"] = {
            "type": "selector",
            "value": {
                "kind": "entityType",
                "objectType": "axioval:example.ifc.wall",
                "includeSubtypes": True,
            },
        }
        return ruleset, definitions

    def test_pkl_selector_value_emits_normalized_selector(self) -> None:
        evaluated = validate.evaluate(
            validate.ROOT / "tests/fixtures/selector-value.pkl"
        )
        self.assertEqual(evaluated["value"]["type"], "selector")
        self.assertEqual(evaluated["value"]["value"]["kind"], "allOf")
        meets = evaluated["value"]["value"]["operands"][1]
        self.assertEqual(meets["kind"], "meets")
        self.assertEqual(
            meets["parameters"]["patterns"], {"type": "stringList", "value": ["W-.*"]}
        )

    def test_documented_selector_examples_are_executable(self) -> None:
        for relative in ("docs/package-contract.md", "docs/package-contract.de.md"):
            document = (validate.ROOT / relative).read_text()
            blocks = [
                textwrap.dedent(block)
                for block in re.findall(
                    r"    ```pkl\n(.*?)\n    ```", document, re.DOTALL
                )
                if "SelectorValues.SelectorValue" in block
            ]
            self.assertEqual(len(blocks), 1, relative)
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".pkl", dir=validate.ROOT / "schema"
            ) as source:
                source.write(blocks[0])
                source.flush()
                evaluated = validate.evaluate(validate.Path(source.name))
            self.assertEqual(
                evaluated["parameters"]["compared"]["type"], "selector", relative
            )

    def test_accepts_bound_selector_parameter(self) -> None:
        ruleset, definitions = self.candidate()
        validate.bind_ruleset(
            ruleset,
            [definitions],
            "test",
            asset_root=validate.ROOT / "examples/minimal",
        )

    def test_selector_defaults_and_allowed_values_bind_concepts(self) -> None:
        invalid = {
            "type": "selector",
            "value": {
                "kind": "entityType",
                "objectType": "axioval:unknown.object-type",
                "includeSubtypes": True,
            },
        }
        for field, value in (
            ("defaultValue", invalid),
            ("allowedValues", [invalid]),
        ):
            ruleset, definitions = self.candidate()
            parameter = definitions["definitions"]["axioval:example.property-exists"][
                "parameters"
            ]["compared"]
            parameter[field] = value
            with self.subTest(field=field), self.assertRaises(SystemExit):
                validate.bind_ruleset(
                    ruleset,
                    [definitions],
                    "test",
                    asset_root=validate.ROOT / "examples/minimal",
                )

    def test_accepts_meets_selector(self) -> None:
        ruleset, definitions = self.candidate()
        ruleset["root"]["rules"][0]["parameters"]["compared"]["value"] = self.meets(
            {"type": "propertyReference", "property": "axioval:example.ifc.reference"}
        )
        validate.bind_ruleset(
            ruleset,
            [definitions],
            "test",
            asset_root=validate.ROOT / "examples/minimal",
        )

    @staticmethod
    def meets(reference: dict) -> dict:
        return {
            "kind": "meets",
            "capability": "axioval:capability.property-value",
            "parameters": {
                "property": reference,
                "min_inclusive": {"type": "number", "value": 1.5},
            },
        }

    def test_rejects_malformed_or_unbound_nested_selector(self) -> None:
        for selector in (
            self.meets(
                {"type": "propertyReference", "property": "axioval:unknown.property"}
            ),
            self.meets({"type": "string"}),
            {**self.meets({"type": "boolean", "value": True}), "capability": "bare"},
            {"kind": "meets", "capability": "axioval:capability.entity"},
            {"kind": "unknown"},
            {
                "kind": "entityType",
                "objectType": "axioval:unknown.object-type",
                "includeSubtypes": True,
            },
        ):
            ruleset, definitions = self.candidate()
            ruleset["root"]["rules"][0]["parameters"]["compared"]["value"] = selector
            with self.subTest(selector=selector), self.assertRaises(SystemExit):
                validate.bind_ruleset(
                    ruleset,
                    [definitions],
                    "test",
                    asset_root=validate.ROOT / "examples/minimal",
                )
