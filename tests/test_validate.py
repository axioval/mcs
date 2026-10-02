from __future__ import annotations

import copy
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import validate


class LocalModuleTests(unittest.TestCase):
    def test_accepts_existing_local_pkl_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            module = base / "rules.pkl"
            module.write_text("value = 1\n")
            self.assertEqual(validate.local_module(base, "rules.pkl"), module.resolve())

    def test_rejects_traversal_absolute_missing_and_wrong_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for value in ("../rules.pkl", "/rules.pkl", "missing.pkl", "rules.json"):
                with self.subTest(value=value), self.assertRaises(SystemExit):
                    validate.local_module(base, value)

    def test_rejects_symlink_escaping_package_root(self) -> None:
        with (
            tempfile.TemporaryDirectory() as package,
            tempfile.TemporaryDirectory() as outside,
        ):
            base = Path(package)
            target = Path(outside) / "rules.pkl"
            target.write_text("value = 1\n")
            (base / "rules.pkl").symlink_to(target)
            with self.assertRaises(SystemExit):
                validate.local_module(base, "rules.pkl")


class EvaluateTests(unittest.TestCase):
    def test_uses_explicit_root_for_sandbox_and_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            module = root / "package/rules.pkl"
            module.parent.mkdir()
            module.write_text("value = 1\n")
            completed = Mock(returncode=0, stdout="{}", stderr="")
            with patch.object(
                validate.subprocess, "run", return_value=completed
            ) as run:
                self.assertEqual(validate.evaluate(module, root), {})
            command = run.call_args.args[0]
            self.assertEqual(command[command.index("--root-dir") + 1], str(root))
            self.assertEqual(
                command[command.index("--allowed-modules") + 1],
                "file:,pkl:,package:,projectpackage:",
            )
            self.assertEqual(
                command[command.index("--allowed-resources") + 1],
                (
                    r"https://openbimrs\.github\.io/pkl/.*,"
                    r"https://github\.com/openbimrs/pkl/releases/download/.*,"
                    r"https://release-assets\.githubusercontent\.com/.*,"
                    "prop:pkl.outputFormat"
                ),
            )

    def test_denies_unrelated_https_resources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            module = root / "rules.pkl"
            module.write_text(
                'value = read("https://example.com/")\n', encoding="utf-8"
            )
            with self.assertRaises(SystemExit) as failure:
                validate.evaluate(module, root=root)
            self.assertIn("Pkl evaluation failed", str(failure.exception))

    def test_denies_file_resources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "secret.txt").write_text("secret", encoding="utf-8")
            module = root / "rules.pkl"
            module.write_text('value = read("secret.txt")\n', encoding="utf-8")
            with self.assertRaises(SystemExit):
                validate.evaluate(module, root)

    def test_project_evaluation_uses_explicit_sandbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "PklProject").write_text("amends `pkl:Project`\n")
            completed = Mock(returncode=0, stdout="", stderr="")
            with patch.object(
                validate.subprocess, "run", return_value=completed
            ) as run:
                validate.evaluate_project(root)
            command = run.call_args.args[0]
            self.assertEqual(command[command.index("--root-dir") + 1], str(root))
            self.assertEqual(
                command[command.index("--allowed-modules") + 1], "file:,pkl:"
            )
            self.assertEqual(
                command[command.index("--allowed-resources") + 1],
                "prop:pkl.outputFormat",
            )


class IdentityTests(unittest.TestCase):
    def test_qualified_ids_and_semver_are_fail_closed(self) -> None:
        self.assertIsNotNone(validate.QUALIFIED_ID.fullmatch("axioval:example.rules"))
        self.assertIsNone(validate.QUALIFIED_ID.fullmatch("example.rules"))
        self.assertIsNotNone(validate.SEMVER.fullmatch("1.2.3-beta.1+build.5"))
        self.assertIsNone(validate.SEMVER.fullmatch("01.2.3"))


class BindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        expected = validate.ROOT / "examples/minimal/expected"
        cls.definitions = json.loads((expected / "definitions.json").read_text())
        cls.ruleset = json.loads((expected / "ruleset.json").read_text())
        din_expected = validate.ROOT / "examples/din-276-331/expected"
        cls.din_definitions = json.loads(
            (din_expected / "definitions.json").read_text()
        )
        cls.din_ruleset = json.loads((din_expected / "ruleset.json").read_text())

    def copies(self) -> tuple[dict, dict]:
        ruleset = copy.deepcopy(self.ruleset)
        definitions = copy.deepcopy(self.definitions)
        for rule in ruleset["root"]["rules"]:
            rule.pop("explanatoryImages", None)
        return ruleset, definitions

    def cited_documents(self) -> tuple[dict, dict]:
        ruleset, definitions = self.copies()
        source_id = "https://example.com/standards/example-1"
        ruleset["sources"][source_id] = {
            "id": source_id,
            "kind": "standard",
            "designation": "EXAMPLE 1:2026",
            "title": {"default": "Example standard", "translations": {}},
            "publisher": "Example Standards Body",
            "edition": "2026",
            "publicationDate": "2026-01",
            "url": source_id,
        }
        rule = ruleset["root"]["rules"][0]
        rule["parameterCitations"] = [
            {
                "parameterIds": ["property"],
                "citation": {
                    "id": "property-source",
                    "sourceId": source_id,
                    "locators": [
                        {"kind": "clause", "value": "4.3.2"},
                        {"kind": "paragraph", "value": "2"},
                    ],
                    "note": {"default": "Parameter provenance.", "translations": {}},
                },
            }
        ]
        rule["requirements"][0]["citations"] = [
            {
                "id": "requirement-source",
                "sourceId": source_id,
                "locators": [{"kind": "clause", "value": "4.3.2"}],
            }
        ]
        return ruleset, definitions

    def test_accepts_fully_bound_ruleset(self) -> None:
        ruleset, definitions = self.cited_documents()
        validate.bind_ruleset(ruleset, [definitions], "test")

    def test_rejects_invalid_source_and_citation_contracts(self) -> None:
        cases = []

        ruleset, definitions = self.cited_documents()
        ruleset["root"]["rules"][0]["parameterCitations"][0]["citation"]["sourceId"] = (
            "axioval:missing.source"
        )
        cases.append(("unknown source", ruleset, definitions))

        ruleset, definitions = self.cited_documents()
        ruleset["root"]["rules"][0]["parameterCitations"][0]["parameterIds"] = [
            "missing"
        ]
        cases.append(("unknown parameter", ruleset, definitions))

        ruleset, definitions = self.cited_documents()
        citation = ruleset["root"]["rules"][0]["requirements"][0]["citations"][0]
        citation["id"] = "property-source"
        cases.append(("duplicate citation id", ruleset, definitions))

        ruleset, definitions = self.cited_documents()
        citation = ruleset["root"]["rules"][0]["parameterCitations"][0]["citation"]
        citation["locators"].append(copy.deepcopy(citation["locators"][0]))
        cases.append(("duplicate locator", ruleset, definitions))

        ruleset, definitions = self.cited_documents()
        _source_id, source = ruleset["sources"].popitem()
        ruleset["sources"]["axioval:wrong-key"] = source
        cases.append(("source key mismatch", ruleset, definitions))

        for unsafe_url in (
            "javascript:x",
            "https://exa mple.com",
            "https://example.com:bad",
            "https://example.com\\x",
            "https://[bad",
        ):
            ruleset, definitions = self.cited_documents()
            next(iter(ruleset["sources"].values()))["url"] = unsafe_url
            cases.append((f"unsafe URL {unsafe_url}", ruleset, definitions))
        ruleset, definitions = self.cited_documents()
        source = next(iter(ruleset["sources"].values()))
        source["publicationDate"] = "2026-99"
        cases.append(("invalid date", ruleset, definitions))

        ruleset, definitions = self.cited_documents()
        next(iter(ruleset["sources"].values()))["publicationDate"] = "0000"
        cases.append(("year zero", ruleset, definitions))

        for label, ruleset, definitions in cases:
            with self.subTest(label=label), self.assertRaises(SystemExit):
                validate.bind_ruleset(ruleset, [definitions], "test")

    def test_rejects_unlocalized_package_metadata(self) -> None:
        ruleset, definitions = self.cited_documents()
        ruleset["package"]["name"] = "Not localized"
        with self.assertRaises(SystemExit):
            validate.bind_ruleset(ruleset, [definitions], "test")

    def test_rejects_unknown_definition(self) -> None:
        ruleset, definitions = self.copies()
        ruleset["root"]["rules"][0]["definitionId"] = "axioval:missing"
        with self.assertRaises(SystemExit):
            validate.bind_ruleset(ruleset, [definitions], "test")

    def test_rejects_undeclared_definition_package(self) -> None:
        ruleset, definitions = self.copies()
        ruleset["definitionPackages"] = ["axioval:other"]
        with self.assertRaises(SystemExit):
            validate.bind_ruleset(ruleset, [definitions], "test")

    def test_rejects_unknown_and_missing_parameters(self) -> None:
        ruleset, definitions = self.copies()
        params = ruleset["root"]["rules"][0]["parameters"]
        params["surprise"] = {"type": "string", "value": "x"}
        with self.assertRaises(SystemExit):
            validate.bind_ruleset(ruleset, [definitions], "test")
        ruleset, definitions = self.copies()
        definitions["definitions"]["axioval:example.property-exists"]["parameters"][
            "property"
        ]["defaultValue"] = {
            "type": "propertyReference",
            "property": "axioval:example.ifc.reference",
        }
        del ruleset["root"]["rules"][0]["parameters"]["property"]
        with self.assertRaises(SystemExit):
            validate.bind_ruleset(ruleset, [definitions], "test")

    def test_rejects_wrong_value_variant(self) -> None:
        ruleset, definitions = self.copies()
        ruleset["root"]["rules"][0]["parameters"]["property"] = {
            "type": "boolean",
            "value": True,
        }
        with self.assertRaises(SystemExit):
            validate.bind_ruleset(ruleset, [definitions], "test")

    def test_quantity_property_requires_unit_dimension(self) -> None:
        ruleset, definitions = self.copies()
        property_definition = definitions["properties"]["axioval:example.ifc.reference"]
        property_definition["valueKind"] = "quantity"
        with self.assertRaises(SystemExit):
            validate.bind_ruleset(ruleset, [definitions], "test")
        property_definition["unitDimension"] = "axioval:dimension.length"
        validate.bind_ruleset(ruleset, [definitions], "test")

    def test_rejects_component_id_reused_across_kinds(self) -> None:
        ruleset, definitions = self.copies()
        property_definition = definitions["properties"].pop(
            "axioval:example.ifc.reference"
        )
        property_definition["id"] = "axioval:example.ifc.wall"
        definitions["properties"]["axioval:example.ifc.wall"] = property_definition
        with self.assertRaises(SystemExit):
            validate.bind_ruleset(ruleset, [definitions], "test")

    def test_din_fixture_encodes_all_three_requirements(self) -> None:
        rules = self.din_ruleset["root"]["rules"]
        self.assertEqual(
            [rule["id"] for rule in rules],
            ["kg331-is-wall", "kg331-load-bearing", "kg331-is-external"],
        )
        self.assertTrue(
            all(rule["applicability"]["kind"] == "classification" for rule in rules)
        )
        self.assertTrue(all(rule["applicability"]["code"] == "331" for rule in rules))
        self.assertEqual(
            rules[0]["parameters"]["objectType"]["objectType"],
            "axioval:example.ifc.wall",
        )
        strict = rules[1]["parameters"]["property"]
        loose = rules[2]["parameters"]["property"]
        self.assertEqual(strict["propertySet"], "axioval:example.ifc.pset-wall-common")
        self.assertNotIn("propertySet", loose)
        self.assertTrue(
            all(rule["parameters"]["expected"]["value"] for rule in rules[1:])
        )

    def test_rejects_unknown_object_type_reference(self) -> None:
        ruleset = copy.deepcopy(self.din_ruleset)
        definitions = copy.deepcopy(self.din_definitions)
        ruleset["root"]["rules"][0]["parameters"]["objectType"]["objectType"] = (
            "axioval:unknown.object-type"
        )
        with self.assertRaises(SystemExit):
            validate.bind_ruleset(ruleset, [definitions], "test")

    def test_rejects_unknown_object_type_concept(self) -> None:
        ruleset, definitions = self.copies()
        ruleset["root"]["rules"][0]["applicability"]["groups"]["walls"]["selector"][
            "objectType"
        ] = "axioval:unknown.object-type"
        with self.assertRaises(SystemExit):
            validate.bind_ruleset(ruleset, [definitions], "test")

    def test_property_set_qualifier_is_optional_but_exact_when_present(self) -> None:
        ruleset, definitions = self.copies()
        strict = ruleset["root"]["rules"][0]["parameters"]["property"]
        self.assertIn("propertySet", strict)
        validate.bind_ruleset(ruleset, [definitions], "test")

        loose_ruleset, loose_definitions = self.copies()
        del loose_ruleset["root"]["rules"][0]["parameters"]["property"]["propertySet"]
        validate.bind_ruleset(loose_ruleset, [loose_definitions], "test")

    def test_rejects_unknown_property_and_property_set_concepts(self) -> None:
        for field in ("property", "propertySet"):
            ruleset, definitions = self.copies()
            ruleset["root"]["rules"][0]["parameters"]["property"][field] = (
                f"axioval:unknown.{field}"
            )
            with self.subTest(field=field), self.assertRaises(SystemExit):
                validate.bind_ruleset(ruleset, [definitions], "test")

    def test_referenced_value_kind_is_enforced(self) -> None:
        ruleset, definitions = self.copies()
        definitions["definitions"]["axioval:example.property-exists"]["parameters"][
            "property"
        ]["referencedValueKind"] = "boolean"
        with self.assertRaises(SystemExit):
            validate.bind_ruleset(ruleset, [definitions], "test")

    def test_accepts_schema_optional_descriptions_and_messages(self) -> None:
        ruleset, definitions = self.copies()
        text = {"default": "Optional", "translations": {}}
        definition = definitions["definitions"]["axioval:example.property-exists"]
        definition.pop("description")
        definition["parameters"]["property"]["description"] = text
        ruleset["root"]["description"] = text
        rule = ruleset["root"]["rules"][0]
        rule["description"] = text
        rule["message"] = text
        validate.bind_ruleset(ruleset, [definitions], "test")

    def rich_rule(self, ruleset: dict) -> dict:
        rule = ruleset["root"]["rules"][0]
        selector = {
            "kind": "entityType",
            "objectType": "axioval:example.ifc.wall",
            "includeSubtypes": True,
        }
        text = {"default": "Subjects", "translations": {"de": "Prüfobjekte"}}
        rule["applicability"] = {
            "groups": {
                "subjects": {
                    "id": "subjects",
                    "name": text,
                    "selector": selector,
                }
            }
        }
        rule["requirements"] = [
            {
                "id": "has-reference",
                "statement": {
                    "default": "Subjects have a reference.",
                    "translations": {"de": "Prüfobjekte haben eine Referenz."},
                },
                "targetGroups": ["subjects"],
            }
        ]
        rule["explanatoryImages"] = [
            {
                "id": "target-groups",
                "path": "assets/target-groups.svg",
                "mediaType": "image/svg+xml",
                "alternativeText": {
                    "default": "Subjects selected by the rule.",
                    "translations": {"de": "Von der Regel ausgewählte Prüfobjekte."},
                },
                "caption": text,
            }
        ]
        return rule

    def test_accepts_target_groups_requirements_and_existing_image(self) -> None:
        ruleset, definitions = self.copies()
        self.rich_rule(ruleset)
        with tempfile.TemporaryDirectory() as tmp:
            root = validate.Path(tmp)
            (root / "assets").mkdir()
            (root / "assets/target-groups.svg").write_text("<svg/>")
            validate.bind_ruleset(ruleset, [definitions], "test", asset_root=root)

    def test_rejects_requirement_for_unknown_or_duplicate_target_group(self) -> None:
        for target_groups in (["missing"], ["subjects", "subjects"], []):
            ruleset, definitions = self.copies()
            rule = self.rich_rule(ruleset)
            rule["requirements"][0]["targetGroups"] = target_groups
            with (
                self.subTest(target_groups=target_groups),
                self.assertRaises(SystemExit),
            ):
                validate.bind_ruleset(ruleset, [definitions], "test")

    def test_rejects_invalid_target_group_map_or_selector(self) -> None:
        mutations = (
            lambda group: group.update(id="different"),
            lambda group: group["selector"].update(objectType="axioval:unknown"),
        )
        for mutate in mutations:
            ruleset, definitions = self.copies()
            rule = self.rich_rule(ruleset)
            mutate(rule["applicability"]["groups"]["subjects"])
            with self.subTest(mutate=mutate), self.assertRaises(SystemExit):
                validate.bind_ruleset(ruleset, [definitions], "test")

    def test_rejects_image_without_asset_root(self) -> None:
        ruleset, definitions = self.copies()
        self.rich_rule(ruleset)
        with self.assertRaisesRegex(SystemExit, "asset root is required"):
            validate.bind_ruleset(ruleset, [definitions], "test")

    def test_rejects_svg_external_loading_vectors(self) -> None:
        cases = (
            (
                '<svg xmlns="http://www.w3.org/2000/svg">'
                "<style>@import url(https://attacker.invalid/x.css)</style></svg>"
            ),
            (
                '<?xml-stylesheet href="https://attacker.invalid/x.css" '
                'type="text/css"?>'
                '<svg xmlns="http://www.w3.org/2000/svg"/>'
            ),
            (
                '<svg xmlns="http://www.w3.org/2000/svg">'
                '<rect fill="url(other.svg#gradient)"/></svg>'
            ),
            (
                '<svg xmlns="http://www.w3.org/2000/svg" '
                'xml:base="../outside.svg"><use href="#shape"/></svg>'
            ),
        )
        for content in cases:
            ruleset, definitions = self.copies()
            rule = self.rich_rule(ruleset)
            with tempfile.TemporaryDirectory() as temporary:
                root = validate.Path(temporary)
                image_path = root / rule["explanatoryImages"][0]["path"]
                image_path.parent.mkdir(parents=True)
                image_path.write_text(content)
                with self.subTest(content=content), self.assertRaises(SystemExit):
                    validate.bind_ruleset(
                        ruleset, [definitions], "test", asset_root=root
                    )

    def test_rejects_unsafe_missing_or_mistyped_explanatory_image(self) -> None:
        cases = (
            ("../outside.svg", "image/svg+xml", False),
            ("/absolute.svg", "image/svg+xml", False),
            ("assets\\diagram.svg", "image/svg+xml", False),
            ("assets/diagram.png", "image/svg+xml", False),
            ("assets/missing.svg", "image/svg+xml", True),
        )
        for path, media_type, check_existence in cases:
            ruleset, definitions = self.copies()
            rule = self.rich_rule(ruleset)
            image = rule["explanatoryImages"][0]
            image["path"] = path
            image["mediaType"] = media_type
            with tempfile.TemporaryDirectory() as tmp:
                root = validate.Path(tmp) if check_existence else None
                with self.subTest(path=path), self.assertRaises(SystemExit):
                    validate.bind_ruleset(
                        ruleset, [definitions], "test", asset_root=root
                    )

    def test_rejects_duplicate_requirement_or_image_ids(self) -> None:
        for field in ("requirements", "explanatoryImages"):
            ruleset, definitions = self.copies()
            rule = self.rich_rule(ruleset)
            rule[field].append(copy.deepcopy(rule[field][0]))
            with self.subTest(field=field), self.assertRaises(SystemExit):
                validate.bind_ruleset(ruleset, [definitions], "test")

    def test_rejects_active_svg_or_spoofed_raster_image(self) -> None:
        ruleset, definitions = self.copies()
        rule = self.rich_rule(ruleset)
        with tempfile.TemporaryDirectory() as temporary:
            root = validate.Path(temporary)
            (root / "assets").mkdir()
            svg_path = root / rule["explanatoryImages"][0]["path"]
            svg_path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
            )
            with self.assertRaises(SystemExit):
                validate.bind_ruleset(ruleset, [definitions], "test", asset_root=root)

            svg_path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg">'
                '<animate attributeName="opacity" values="0;1"/></svg>'
            )
            with self.assertRaises(SystemExit):
                validate.bind_ruleset(ruleset, [definitions], "test", asset_root=root)

            svg_path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg">'
                '<rect style="fill:url(data:image/svg+xml,bad)"/></svg>'
            )
            with self.assertRaises(SystemExit):
                validate.bind_ruleset(ruleset, [definitions], "test", asset_root=root)

            rule["explanatoryImages"][0]["path"] = "assets/diagram.png"
            rule["explanatoryImages"][0]["mediaType"] = "image/png"
            (root / "assets/diagram.png").write_bytes(b"not a png")
            with self.assertRaises(SystemExit):
                validate.bind_ruleset(ruleset, [definitions], "test", asset_root=root)

    def test_accepts_compatible_default_and_allowed_value(self) -> None:
        _, definitions = self.copies()
        parameter = definitions["definitions"]["axioval:example.property-exists"][
            "parameters"
        ]["property"]
        reference = {
            "type": "propertyReference",
            "property": "axioval:example.ifc.reference",
        }
        parameter["defaultValue"] = copy.deepcopy(reference)
        parameter["allowedValues"] = [reference]
        validate.validate_definition_document(definitions, "test")

    def test_rejects_incompatible_definition_default(self) -> None:
        for invalid_default in (None, {"type": "boolean", "value": True}):
            _, definitions = self.copies()
            definitions["definitions"]["axioval:example.property-exists"]["parameters"][
                "property"
            ]["defaultValue"] = invalid_default
            with (
                self.subTest(invalid_default=invalid_default),
                self.assertRaises(SystemExit),
            ):
                validate.validate_definition_document(definitions, "test")

    def test_rejects_value_outside_allowed_set(self) -> None:
        ruleset, definitions = self.copies()
        definitions["definitions"]["axioval:example.property-exists"]["parameters"][
            "property"
        ]["allowedValues"] = [
            {
                "type": "propertyReference",
                "property": "axioval:example.ifc.reference",
            }
        ]
        with self.assertRaises(SystemExit):
            validate.bind_ruleset(ruleset, [definitions], "test")


class StaticManifestTests(unittest.TestCase):
    def test_schema_and_validator_required_fields_stay_in_sync(self) -> None:
        schema = json.loads(
            (validate.ROOT / "schema/registry-manifest.schema.json").read_text()
        )
        self.assertEqual(set(schema["required"]), validate.REQUIRED)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["definitionEntrypoints"]["minItems"], 1)
        self.assertEqual(
            schema["properties"]["entrypoint"]["pattern"],
            validate.PKL_ENTRYPOINT.pattern,
        )
        self.assertEqual(
            schema["properties"]["definitionEntrypoints"]["items"]["pattern"],
            validate.PKL_ENTRYPOINT.pattern,
        )

    def test_rejects_missing_or_malformed_definition_entrypoints(self) -> None:
        manifest = json.loads(
            (validate.ROOT / "examples/minimal/axioval.json").read_text()
        )
        for entries in (None, [], ["definitions.pkl", "definitions.pkl"], [{}]):
            candidate = copy.deepcopy(manifest)
            if entries is None:
                del candidate["definitionEntrypoints"]
            else:
                candidate["definitionEntrypoints"] = entries
            with self.subTest(entries=entries), self.assertRaises(SystemExit):
                validate.validate_manifest(candidate, Path("axioval.json"))

    def test_rejects_unsafe_entrypoint_paths_before_resolution(self) -> None:
        manifest = json.loads(
            (validate.ROOT / "examples/minimal/axioval.json").read_text()
        )
        for field, value in (
            ("entrypoint", "/ruleset.pkl"),
            ("entrypoint", "../ruleset.pkl"),
            ("entrypoint", "ruleset.txt"),
            ("definitionEntrypoints", ["/definitions.pkl"]),
            ("definitionEntrypoints", ["../definitions.pkl"]),
            ("definitionEntrypoints", ["definitions.txt"]),
        ):
            candidate = copy.deepcopy(manifest)
            candidate[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(SystemExit):
                validate.validate_manifest(candidate, Path("axioval.json"))


class SelectorTests(unittest.TestCase):
    def test_rejects_exists_with_value_and_comparison_without_value(self) -> None:
        from scripts.contracts import validate_selector

        with self.assertRaises(SystemExit):
            validate_selector(
                {
                    "kind": "property",
                    "property": "axioval:example.ifc.reference",
                    "operator": "exists",
                    "value": {"type": "string", "value": "x"},
                },
                "test",
            )
        with self.assertRaises(SystemExit):
            validate_selector(
                {
                    "kind": "property",
                    "property": "axioval:example.ifc.reference",
                    "operator": "equals",
                },
                "test",
            )


PROPERTY_KINDS = {
    "axioval:example.text": "string",
    "axioval:example.state": "enum",
    "axioval:example.count": "integer",
    "axioval:example.width": "quantity",
    "axioval:example.flag": "boolean",
    "axioval:example.tags": "stringList",
}


def property_selector(property_id: str, operator: str, value=None, **flags) -> dict:
    selector = {"kind": "property", "property": property_id, "operator": operator}
    if value is not None:
        selector["value"] = value
    selector.update(flags)
    return selector


def text(value: str) -> dict:
    return {"type": "string", "value": value}


def texts(*values: str) -> dict:
    return {"type": "stringList", "value": list(values)}


class ExtendedPropertySelectorTests(unittest.TestCase):
    """Property selectors mirror the engine's extended comparison contract."""

    properties = {
        property_id: {"valueKind": kind} for property_id, kind in PROPERTY_KINDS.items()
    }

    def check(self, selector: dict) -> None:
        from scripts.contracts import validate_selector

        validate_selector(selector, "test", None, self.properties, None)

    def assert_rejected(self, selector: dict) -> None:
        with self.subTest(selector=selector), self.assertRaises(SystemExit):
            self.check(selector)

    def test_accepts_new_operators_with_their_value_shapes(self) -> None:
        for selector in (
            property_selector("axioval:example.text", "matches", text("EI[0-9]+")),
            property_selector("axioval:example.text", "like", text("EI*")),
            property_selector("axioval:example.text", "contains", text("30")),
            property_selector("axioval:example.text", "oneOf", texts("a", "b")),
            property_selector("axioval:example.text", "noneOf", texts()),
            property_selector("axioval:example.state", "oneOf", texts("open", "shut")),
        ):
            with self.subTest(selector=selector):
                self.check(selector)

    def test_text_operators_require_a_string(self) -> None:
        for operator in ("matches", "like", "contains"):
            self.assert_rejected(
                property_selector("axioval:example.text", operator, texts("a"))
            )
            self.assert_rejected(
                property_selector(
                    "axioval:example.text", operator, {"type": "integer", "value": 1}
                )
            )
            self.assert_rejected(
                property_selector("axioval:example.count", operator, text("1"))
            )

    def test_list_operators_require_a_string_list_of_the_property_kind(self) -> None:
        for operator in ("oneOf", "noneOf"):
            self.assert_rejected(
                property_selector("axioval:example.text", operator, text("a"))
            )
            self.assert_rejected(
                property_selector(
                    "axioval:example.text",
                    operator,
                    {"type": "referenceList", "value": ["axioval:a"]},
                )
            )
            # Elements are checked against the property kind, not the list.
            self.assert_rejected(
                property_selector("axioval:example.state", operator, texts("Not An Id"))
            )
            self.assert_rejected(
                property_selector("axioval:example.count", operator, texts("1"))
            )
            self.assert_rejected(
                property_selector("axioval:example.tags", operator, texts("a"))
            )

    def test_ordering_operators_require_ordered_values(self) -> None:
        for operator in (
            "lessThan",
            "lessThanOrEquals",
            "greaterThan",
            "greaterThanOrEquals",
        ):
            for selector in (
                property_selector(
                    "axioval:example.count", operator, {"type": "integer", "value": 2}
                ),
                property_selector(
                    "axioval:example.width",
                    operator,
                    {"type": "quantity", "value": 0.9, "unit": "m"},
                ),
                property_selector("axioval:example.text", operator, text("B")),
                property_selector("axioval:example.unbound", operator, text("B")),
            ):
                with self.subTest(selector=selector):
                    from scripts.contracts import validate_selector

                    validate_selector(selector, "test")
            for selector in (
                property_selector(
                    "axioval:example.flag", operator, {"type": "boolean", "value": True}
                ),
                property_selector(
                    "axioval:example.state", operator, {"type": "enum", "value": "open"}
                ),
                property_selector("axioval:example.tags", operator, texts("a")),
            ):
                self.assert_rejected(selector)

    def test_accepts_text_options_on_text_comparisons(self) -> None:
        for operator, value in (
            ("equals", text("F30")),
            ("notEquals", text("F30")),
            ("greaterThan", text("F30")),
            ("matches", text("f[0-9]+")),
            ("like", text("f*")),
            ("contains", text("3")),
            ("oneOf", texts("f30", "f60")),
            ("noneOf", texts("f90")),
        ):
            selector = property_selector(
                "axioval:example.text",
                operator,
                value,
                caseSensitive=False,
                trim=True,
            )
            with self.subTest(selector=selector):
                self.check(selector)
        self.check(
            property_selector(
                "axioval:example.state",
                "equals",
                {"type": "enum", "value": "open"},
                caseSensitive=False,
            )
        )
        # Explicit defaults are accepted on any comparison.
        self.check(
            property_selector(
                "axioval:example.count",
                "equals",
                {"type": "integer", "value": 1},
                caseSensitive=True,
                trim=False,
            )
        )
        self.check(property_selector("axioval:example.text", "exists", trim=False))

    def test_rejects_text_options_outside_text_comparisons(self) -> None:
        for flags in ({"caseSensitive": False}, {"trim": True}):
            self.assert_rejected(
                property_selector("axioval:example.text", "exists", **flags)
            )
            self.assert_rejected(
                property_selector(
                    "axioval:example.count",
                    "equals",
                    {"type": "integer", "value": 1},
                    **flags,
                )
            )
            self.assert_rejected(
                property_selector(
                    "axioval:example.flag",
                    "equals",
                    {"type": "boolean", "value": True},
                    **flags,
                )
            )
            self.assert_rejected(
                property_selector(
                    "axioval:example.width",
                    "lessThan",
                    {"type": "quantity", "value": 1, "unit": "m"},
                    **flags,
                )
            )

    def test_rejects_non_boolean_text_options(self) -> None:
        for flag, value in (("caseSensitive", "false"), ("trim", 1), ("trim", None)):
            self.assert_rejected(
                property_selector(
                    "axioval:example.text", "equals", text("a"), **{flag: value}
                )
            )

    def test_pkl_omits_default_text_options(self) -> None:
        evaluated = validate.evaluate(
            validate.ROOT / "tests/fixtures/property-selector-flags.pkl"
        )
        validate.validate_definition_document(evaluated, "fixture")
        plain, folded = evaluated["definitions"]["axioval:example.selected"][
            "parameters"
        ]["compared"]["defaultValue"]["value"]["operands"]
        self.assertEqual(
            plain,
            property_selector("axioval:example.ifc.reference", "like", text("EI*")),
        )
        self.assertEqual(
            folded,
            property_selector(
                "axioval:example.ifc.reference",
                "noneOf",
                texts("a", "b"),
                caseSensitive=False,
                trim=True,
            ),
        )


def column(column_id: str, kind: str, required: bool = True) -> dict:
    declared = {
        "id": column_id,
        "name": {"default": column_id, "translations": {}},
        "kind": kind,
        "required": required,
    }
    if kind == "quantity":
        declared["unitDimension"] = "area"
    return declared


def table_row(pattern: str, area: float, **cells) -> dict:
    row = {
        "space_type": text(pattern),
        "minimum_area": {"type": "quantity", "value": area, "unit": "m2"},
    }
    row.update(cells)
    return row


class TableParameterTests(unittest.TestCase):
    """Table parameters bind typed rows against declared columns."""

    @classmethod
    def setUpClass(cls) -> None:
        expected = validate.ROOT / "examples/minimal/expected"
        cls.definitions = json.loads((expected / "definitions.json").read_text())
        cls.ruleset = json.loads((expected / "ruleset.json").read_text())

    def documents(self, rows: list | None = None, **overrides) -> tuple[dict, dict]:
        ruleset = copy.deepcopy(self.ruleset)
        definitions = copy.deepcopy(self.definitions)
        for rule in ruleset["root"]["rules"]:
            rule.pop("explanatoryImages", None)
        limits = {
            "id": "limits",
            "name": {"default": "Limits", "translations": {}},
            "kind": "table",
            "required": True,
            "allowedValues": [],
            "citations": [],
            "columns": [
                column("space_type", "textPattern"),
                column("minimum_area", "quantity"),
                column("label", "string", required=False),
                column("count", "integer", required=False),
                column("ratio", "number", required=False),
                column("strict", "boolean", required=False),
                column("scope", "selector", required=False),
                column("reference", "reference", required=False),
                column("inspected", "date", required=False),
                column("stamped", "dateTime", required=False),
            ],
        }
        limits.update(overrides)
        definitions["definitions"]["axioval:example.property-exists"]["parameters"][
            "limits"
        ] = limits
        ruleset["root"]["rules"][0]["parameters"]["limits"] = {
            "type": "table",
            "value": [table_row("Office*", 10)] if rows is None else rows,
        }
        return ruleset, definitions

    def bind(self, rows: list | None = None, **overrides) -> None:
        ruleset, definitions = self.documents(rows, **overrides)
        validate.bind_ruleset(ruleset, [definitions], "test")

    def assert_rejected(self, rows: list | None = None, **overrides) -> None:
        with (
            self.subTest(rows=rows, overrides=overrides),
            self.assertRaises(SystemExit),
        ):
            self.bind(rows, **overrides)

    def test_accepts_rows_of_every_column_kind(self) -> None:
        self.bind(
            [
                table_row(
                    "Office",
                    12.5,
                    label=text("single office"),
                    count={"type": "integer", "value": 2},
                    ratio={"type": "number", "value": 0.5},
                    strict={"type": "boolean", "value": True},
                    scope={
                        "type": "selector",
                        "value": {
                            "kind": "entityType",
                            "objectType": "axioval:example.ifc.wall",
                            "includeSubtypes": True,
                        },
                    },
                    reference={
                        "type": "reference",
                        "value": "axioval:example.office",
                    },
                ),
                table_row(r"Office\*", 10),
                table_row("*", 6),
            ]
        )
        self.bind([])

    def test_accepts_a_default_table_checked_against_the_columns(self) -> None:
        ruleset, definitions = self.documents()
        parameter = definitions["definitions"]["axioval:example.property-exists"][
            "parameters"
        ]["limits"]
        parameter["required"] = False
        parameter["defaultValue"] = {"type": "table", "value": [table_row("*", 6)]}
        del ruleset["root"]["rules"][0]["parameters"]["limits"]
        validate.bind_ruleset(ruleset, [definitions], "test")
        parameter["defaultValue"]["value"][0]["colour"] = text("red")
        with self.assertRaises(SystemExit):
            validate.validate_definition_document(definitions, "test")

    def test_rejects_rows_that_do_not_fit_the_columns(self) -> None:
        missing = table_row("Office", 10)
        del missing["minimum_area"]
        for rows in (
            [table_row("Office", 10, colour=text("red"))],
            [table_row("Office", 10, label={"type": "enum", "value": "office"})],
            [table_row("Office", 10, count={"type": "number", "value": 2.0})],
            [table_row("Office", 10, ratio={"type": "integer", "value": 1})],
            [table_row("Office", 10, strict=text("true"))],
            [table_row("Office", 10, scope=text("walls"))],
            [table_row("Office", 10, reference=text("x"))],
            [table_row("Office", 10, label={"type": "table", "value": []})],
            [
                {
                    **table_row("Office", 10),
                    "minimum_area": {"type": "number", "value": 1},
                }
            ],
            [
                {
                    **table_row("Office", 10),
                    "space_type": {"type": "integer", "value": 1},
                }
            ],
            [missing],
            [table_row("Office\\", 10)],
            ["not a row"],
            [
                table_row(
                    "Office",
                    10,
                    scope={
                        "type": "selector",
                        "value": {
                            "kind": "entityType",
                            "objectType": "axioval:example.unknown",
                            "includeSubtypes": True,
                        },
                    },
                )
            ],
        ):
            self.assert_rejected(rows)

    def test_date_columns_take_date_and_date_time_cells(self) -> None:
        self.bind(
            [
                table_row(
                    "Office",
                    10,
                    inspected=date("2024-02-29"),
                    stamped=date_time("2026-09-27T10:00:00.5+02:00"),
                ),
                table_row("*", 6, stamped=date_time("2026-09-27T08:00:00Z")),
            ]
        )
        for cells in (
            {"inspected": date("2026-02-29")},
            {"inspected": date("2026-9-27")},
            {"inspected": date_time("2026-09-27T10:00:00Z")},
            {"inspected": text("2026-09-27")},
            {"stamped": date_time("2026-09-27T10:00:00")},
            {"stamped": date_time("2026-09-27T24:00:00Z")},
            {"stamped": date_time("2026-09-27T10:00:00-00:00")},
            {"stamped": date("2026-09-27")},
        ):
            self.assert_rejected([table_row("Office", 10, **cells)])

    def test_pkl_renders_date_columns(self) -> None:
        evaluated = validate.evaluate(
            validate.ROOT / "tests/fixtures/table-date-columns.pkl"
        )
        validate.validate_definition_document(evaluated, "fixture")
        limits = evaluated["definitions"]["axioval:example.inspection-limits"][
            "parameters"
        ]["limits"]
        self.assertEqual(
            [(declared["id"], declared["kind"]) for declared in limits["columns"]],
            [
                ("space_type", "textPattern"),
                ("inspected", "date"),
                ("stamped", "dateTime"),
            ],
        )
        self.assertEqual(
            limits["defaultValue"]["value"],
            [
                {
                    "space_type": text("Office*"),
                    "inspected": date("2026-09-27"),
                    "stamped": date_time("2026-09-27T10:00:00+02:00"),
                }
            ],
        )

    def test_rejects_invalid_column_declarations(self) -> None:
        for columns in (
            [],
            [column("space_type", "textPattern"), column("space_type", "string")],
            [column("Space Type", "textPattern")],
            [column("rows", "table")],
            [column("rows", "stringList")],
            [{**column("area", "quantity"), "unitDimension": ""}],
            [{**column("label", "string"), "unitDimension": "area"}],
            [{**column("label", "string"), "required": "yes"}],
            [{**column("label", "string"), "width": 3}],
            [
                {
                    key: value
                    for key, value in column("label", "string").items()
                    if key != "name"
                }
            ],
        ):
            self.assert_rejected([], columns=columns)
        quantity = column("area", "quantity")
        del quantity["unitDimension"]
        self.assert_rejected([], columns=[quantity])

    def test_columns_belong_to_tables_only(self) -> None:
        ruleset, definitions = self.documents()
        del definitions["definitions"]["axioval:example.property-exists"][
            "parameters"
        ]["limits"]["columns"]
        with self.assertRaises(SystemExit):
            validate.bind_ruleset(ruleset, [definitions], "test")
        _, definitions = self.documents()
        definitions["definitions"]["axioval:example.property-exists"]["parameters"][
            "property"
        ]["columns"] = [column("label", "string")]
        with self.assertRaises(SystemExit):
            validate.validate_definition_document(definitions, "test")
        self.assert_rejected(
            allowedValues=[{"type": "table", "value": [table_row("Office*", 10)]}]
        )

    def test_a_table_value_needs_a_table_parameter(self) -> None:
        ruleset, definitions = self.documents()
        ruleset["root"]["rules"][0]["parameters"]["property"] = {
            "type": "table",
            "value": [],
        }
        with self.assertRaises(SystemExit):
            validate.bind_ruleset(ruleset, [definitions], "test")
        from scripts.contracts import validate_selector

        with self.assertRaises(SystemExit):
            validate_selector(
                property_selector(
                    "axioval:example.text", "equals", {"type": "table", "value": []}
                ),
                "test",
            )

    def test_pkl_renders_columns_only_on_tables(self) -> None:
        evaluated = validate.evaluate(
            validate.ROOT / "tests/fixtures/table-parameter.pkl"
        )
        validate.validate_definition_document(evaluated, "fixture")
        parameters = evaluated["definitions"]["axioval:example.area-limits"][
            "parameters"
        ]
        self.assertNotIn("columns", parameters["label"])
        limits = parameters["limits"]
        # Undeclared descriptions and non-quantity dimensions are omitted.
        self.assertEqual(
            [{**declared, "name": None} for declared in limits["columns"]],
            [
                {**column("space_type", "textPattern"), "name": None},
                {**column("minimum_area", "quantity"), "name": None},
                {**column("scope", "selector", required=False), "name": None},
            ],
        )
        self.assertEqual(
            limits["defaultValue"]["value"][1],
            table_row("*", 6, scope={"type": "selector", "value": {"kind": "all"}}),
        )


class QuantifiedPropertySelectorTests(unittest.TestCase):
    """List-valued properties compare element by element under a quantifier."""

    properties = {
        property_id: {"valueKind": kind} for property_id, kind in PROPERTY_KINDS.items()
    } | {"axioval:example.references": {"valueKind": "referenceList"}}

    def check(self, selector: dict) -> None:
        from scripts.contracts import validate_selector

        validate_selector(selector, "test", None, self.properties, None)

    def assert_rejected(self, selector: dict) -> None:
        with self.subTest(selector=selector), self.assertRaises(SystemExit):
            self.check(selector)

    def test_accepts_quantified_comparisons_of_list_elements(self) -> None:
        for quantifier in ("any", "all"):
            for selector in (
                property_selector(
                    "axioval:example.tags",
                    "oneOf",
                    texts("A-WALL"),
                    quantifier=quantifier,
                ),
                property_selector(
                    "axioval:example.tags", "noneOf", texts(), quantifier=quantifier
                ),
                property_selector(
                    "axioval:example.tags",
                    "equals",
                    text("A-WALL"),
                    quantifier=quantifier,
                ),
                property_selector(
                    "axioval:example.tags",
                    "like",
                    text("a-*"),
                    quantifier=quantifier,
                    caseSensitive=False,
                    trim=True,
                ),
                property_selector(
                    "axioval:example.tags",
                    "greaterThan",
                    text("B"),
                    quantifier=quantifier,
                ),
                property_selector(
                    "axioval:example.references",
                    "equals",
                    {"type": "reference", "value": "axioval:a"},
                    quantifier=quantifier,
                ),
                # A single value counts as a one-element list.
                property_selector(
                    "axioval:example.count",
                    "greaterThan",
                    {"type": "integer", "value": 2},
                    quantifier=quantifier,
                ),
            ):
                with self.subTest(selector=selector):
                    self.check(selector)
            # Without a catalog the element kind is unknown, so any value fits.
            from scripts.contracts import validate_selector

            validate_selector(
                property_selector(
                    "axioval:example.unbound",
                    "equals",
                    text("a"),
                    quantifier=quantifier,
                ),
                "test",
            )
        self.check(property_selector("axioval:example.tags", "exists"))

    def test_rejects_unknown_quantifiers(self) -> None:
        for quantifier in ("some", "ANY", "none", "", None, True, ["any"]):
            self.assert_rejected(
                property_selector(
                    "axioval:example.tags", "oneOf", texts("a"), quantifier=quantifier
                )
            )

    def test_rejects_a_quantifier_on_exists(self) -> None:
        for quantifier in ("any", "all"):
            self.assert_rejected(
                property_selector(
                    "axioval:example.tags", "exists", quantifier=quantifier
                )
            )
            self.assert_rejected(
                property_selector(
                    "axioval:example.text", "exists", quantifier=quantifier
                )
            )

    def test_list_valued_comparisons_require_a_quantifier(self) -> None:
        for selector in (
            property_selector("axioval:example.tags", "oneOf", texts("a")),
            property_selector("axioval:example.tags", "equals", texts("a")),
            property_selector("axioval:example.tags", "contains", text("a")),
            property_selector(
                "axioval:example.references",
                "equals",
                {"type": "referenceList", "value": ["axioval:a"]},
            ),
        ):
            self.assert_rejected(selector)

    def test_quantified_values_fit_the_element_kind(self) -> None:
        for selector in (
            # The whole list is never compared.
            property_selector(
                "axioval:example.tags", "equals", texts("a"), quantifier="any"
            ),
            property_selector(
                "axioval:example.tags",
                "equals",
                {"type": "integer", "value": 1},
                quantifier="all",
            ),
            property_selector(
                "axioval:example.references",
                "oneOf",
                texts("Not A Reference"),
                quantifier="any",
            ),
            property_selector(
                "axioval:example.count", "like", text("1*"), quantifier="any"
            ),
            property_selector(
                "axioval:example.count",
                "equals",
                {"type": "integer", "value": 1},
                quantifier="any",
                caseSensitive=False,
            ),
        ):
            self.assert_rejected(selector)

    def test_pkl_omits_an_unset_quantifier(self) -> None:
        evaluated = validate.evaluate(
            validate.ROOT / "tests/fixtures/property-selector-quantifier.pkl"
        )
        validate.validate_definition_document(evaluated, "fixture")
        quantified, present = evaluated["definitions"]["axioval:example.selected"][
            "parameters"
        ]["compared"]["defaultValue"]["value"]["operands"]
        self.assertEqual(
            quantified,
            property_selector(
                "axioval:example.layers",
                "oneOf",
                texts("A-WALL", "A-DOOR"),
                quantifier="all",
            ),
        )
        self.assertEqual(present, property_selector("axioval:example.layers", "exists"))


def related_selector(path, selector=None, **fields) -> dict:
    related = {
        "kind": "related",
        "path": path,
        "selector": selector if selector is not None else {"kind": "all"},
    }
    related.update(fields)
    return related


class RelatedSelectorTests(unittest.TestCase):
    """Related selectors test the objects a relationship path reaches."""

    object_types = {"axioval:example.door": {}}
    properties = {
        property_id: {"valueKind": kind} for property_id, kind in PROPERTY_KINDS.items()
    }

    def check(self, selector: dict) -> None:
        from scripts.contracts import validate_selector

        validate_selector(selector, "test", self.object_types, self.properties, {})

    def assert_rejected(self, selector: dict) -> None:
        with self.subTest(selector=selector), self.assertRaises(SystemExit):
            self.check(selector)

    def test_accepts_paths_quantifiers_and_nested_selectors(self) -> None:
        for selector in (
            related_selector(
                ["IfcRelFillsElement:backward", "IfcRelVoidsElement:backward"],
                property_selector(
                    "axioval:example.flag", "equals", {"type": "boolean", "value": True}
                ),
            ),
            related_selector(["IfcRelAggregates"]),
            related_selector(["IfcRelAggregates:forward"], quantifier="any"),
            related_selector(
                [
                    "IfcRelAggregates:backward+",
                    "IfcRelNests:either+",
                    "IfcRelContainedInSpatialStructure:forward+",
                    "IfcRelAggregates+",
                ]
            ),
            related_selector(
                [
                    "IfcRelFillsElement|IfcRelVoidsElement:backward+",
                    "IfcRelAggregates|IfcRelNests",
                    "IfcRelNests|axioval:derived.same-level;by=1:either",
                    "axioval:derived.intersects|IfcRelNests",
                    "axioval:derived.adjacent-space;reach=1|axioval:derived.intersects+",
                ]
            ),
            related_selector(
                [
                    "axioval:relationship.containment:backward",
                    "axioval:relationship.fills|axioval:relationship.voids:backward+",
                    "axioval:relationship.space-boundary|IfcRelSpaceBoundary",
                    "axioval:relationship.type",
                ]
            ),
            related_selector(
                [
                    "axioval:derived.adjacent-space",
                    "axioval:derived.contained-in-space;horizontal=0.25;vertical=0.5",
                    "axioval:derived.overlapping-group-space;ratio=0.9:backward",
                    "axioval:derived.intersects:either+",
                    "IfcRelContainedInSpatialStructure:backward",
                ],
                quantifier="none",
            ),
            related_selector(
                ["IfcRelVoidsElement", "IfcRelFillsElement:either"],
                {
                    "kind": "entityType",
                    "objectType": "axioval:example.door",
                    "includeSubtypes": True,
                },
                quantifier="all",
            ),
            related_selector(
                ["IfcRelContainedInSpatialStructure:backward"],
                {
                    "kind": "not",
                    "operand": related_selector(
                        ["IfcRelAggregates"],
                        property_selector("axioval:example.text", "exists"),
                        quantifier="none",
                    ),
                },
                quantifier="none",
            ),
        ):
            with self.subTest(selector=selector):
                self.check(selector)

    def test_rejects_malformed_related_selectors(self) -> None:
        valid = related_selector(["IfcRelAggregates"])
        for selector in (
            {key: value for key, value in valid.items() if key != "path"},
            {key: value for key, value in valid.items() if key != "selector"},
            {**valid, "operand": {"kind": "all"}},
            {**valid, "direction": "forward"},
            related_selector([]),
            related_selector(["axioval:relationship.walls"]),
            related_selector(["axioval:relationship."]),
            related_selector(["axioval:relationship.Fills"]),
            related_selector(["axioval:relationship.fills|axioval:relationship.fills"]),
            related_selector("IfcRelAggregates"),
            related_selector([""]),
            related_selector([None]),
            related_selector([["IfcRelAggregates"]]),
            related_selector(["IfcRelAggregates:"]),
            related_selector(["IfcRelAggregates:up"]),
            related_selector(["IfcRelAggregates:Forward"]),
            related_selector(["IfcRelAggregates:forward:backward"]),
            related_selector(["IfcRelAggregates:backward++"]),
            related_selector(["IfcRelAggregates:+"]),
            related_selector(["IfcRelAggregates:up+"]),
            related_selector(["IfcRelAggregates:backward +"]),
            related_selector([":forward"]),
            related_selector(["Ifc Rel"]),
            related_selector(["IfcRelAggregates "]),
            related_selector(["axioval:derived."]),
            related_selector(["axioval:derived.Adjacent-Space"]),
            related_selector(["axioval:derived.adjacent-space;reach"]),
            related_selector(["axioval:derived.adjacent-space;reach=-1"]),
            related_selector(["axioval:derived.adjacent-space:sideways"]),
            related_selector(["axioval:other.adjacent-space"]),
            related_selector(["IfcRelNests|"]),
            related_selector(["|IfcRelNests"]),
            related_selector(["IfcRelNests||IfcRelAggregates"]),
            related_selector(["IfcRelNests|IfcRelNests"]),
            related_selector(["IfcRelNests|IfcRelNests:backward+"]),
            related_selector(["IfcRelNests:backward|IfcRelAggregates"]),
            related_selector(["IfcRelNests:backward|IfcRelAggregates:backward"]),
            related_selector(["axioval:derived.intersects:either|IfcRelNests"]),
            related_selector(["IfcRelNests | IfcRelAggregates"]),
            related_selector(["IfcRelNests|IfcRelAggregates:sideways"]),
            related_selector(["IfcRelNests|axioval:derived.intersects:up"]),
            related_selector(["|"]),
            related_selector(["+"]),
            related_selector({"kind": "unknown"}),
            related_selector(None),
        ):
            self.assert_rejected(selector)

    def test_rejects_unknown_quantifiers(self) -> None:
        for quantifier in ("some", "ALL", "exists", "", None, True, ["all"]):
            self.assert_rejected(
                related_selector(["IfcRelAggregates"], quantifier=quantifier)
            )

    def test_nested_selectors_bind_against_the_concept_catalogs(self) -> None:
        for nested in (
            property_selector("axioval:example.unknown", "exists"),
            property_selector("axioval:example.flag", "equals", text("yes")),
            {
                "kind": "entityType",
                "objectType": "axioval:example.window",
                "includeSubtypes": True,
            },
            related_selector(
                ["IfcRelAggregates"],
                property_selector("axioval:example.tags", "oneOf", texts("a")),
            ),
        ):
            self.assert_rejected(related_selector(["IfcRelAggregates"], nested))

    def test_pkl_rejects_malformed_related_selectors(self) -> None:
        selectors = (validate.ROOT / "schema/Selectors.pkl").as_uri()
        for fields in (
            "path {}",
            'path { "" }',
            'path { "IfcRelAggregates" }\n  quantifier = "some"',
        ):
            with (
                self.subTest(fields=fields),
                tempfile.TemporaryDirectory(dir=validate.ROOT / "tests") as tmp,
            ):
                module = Path(tmp) / "related.pkl"
                module.write_text(
                    f'import "{selectors}"\n\n'
                    "value = new Selectors.RelatedSelector {\n"
                    f"  {fields}\n"
                    "  selector = new Selectors.AllSelector {}\n"
                    "}\n",
                    encoding="utf-8",
                )
                with self.assertRaises(SystemExit):
                    validate.evaluate(module)

    def test_pkl_omits_the_default_quantifier(self) -> None:
        evaluated = validate.evaluate(
            validate.ROOT / "tests/fixtures/related-selector.pkl"
        )
        validate.validate_definition_document(evaluated, "fixture")
        defaulted, every, none = evaluated["definitions"]["axioval:example.selected"][
            "parameters"
        ]["compared"]["defaultValue"]["value"]["operands"]
        # The nested property selector still omits its default text flags.
        self.assertEqual(
            defaulted,
            related_selector(
                ["IfcRelFillsElement:backward", "IfcRelVoidsElement:backward"],
                property_selector(
                    "axioval:example.compartmentation",
                    "equals",
                    {"type": "boolean", "value": True},
                ),
            ),
        )
        self.assertEqual(
            every,
            related_selector(
                ["IfcRelVoidsElement", "IfcRelFillsElement:forward"],
                {
                    "kind": "entityType",
                    "objectType": "axioval:example.door",
                    "includeSubtypes": True,
                },
                quantifier="all",
            ),
        )
        self.assertEqual(
            none,
            related_selector(
                ["IfcRelAggregates:either"],
                {
                    "kind": "not",
                    "operand": property_selector(
                        "axioval:example.compartmentation", "exists"
                    ),
                },
                quantifier="none",
            ),
        )



def date(value: str) -> dict:
    return {"type": "date", "value": value}


def date_time(value: str) -> dict:
    return {"type": "dateTime", "value": value}


class DateValueTests(unittest.TestCase):
    """Date and date-time literals follow the engine's rules exactly."""

    properties = {
        property_id: {"valueKind": kind} for property_id, kind in PROPERTY_KINDS.items()
    } | {
        "axioval:example.inspected-on": {"valueKind": "date"},
        "axioval:example.installed-at": {"valueKind": "dateTime"},
    }

    def check(self, selector: dict) -> None:
        from scripts.contracts import validate_selector

        validate_selector(selector, "test", None, self.properties, None)

    def assert_rejected(self, selector: dict) -> None:
        with self.subTest(selector=selector), self.assertRaises(SystemExit):
            self.check(selector)

    def test_accepts_real_days(self) -> None:
        from scripts.contracts import parameter_value

        for literal in (
            "0000-01-01",
            "9999-12-31",
            "2026-09-27",
            "2024-02-29",
            "2000-02-29",
            "0000-02-29",
            "2026-04-30",
            "2026-01-31",
            "2026-09-27Z",
            "2026-09-27+02:00",
            "2022-01-01+00:00",
            "2026-09-27-14:00",
            "2024-02-29+05:45",
        ):
            with self.subTest(literal=literal):
                parameter_value(date(literal), "date", "test")

    def test_rejects_malformed_and_unreal_days(self) -> None:
        from scripts.contracts import parameter_value

        for literal in (
            "",
            "2026-9-27",
            "26-09-27",
            "2026/09/27",
            "20260927",
            "+2026-09-27",
            "12026-09-27",
            "2026-09-27T00:00:00Z",
            "2026-09-27-00:00",
            "2026-09-27+14:01",
            "2026-09-27+02:60",
            "2026-09-27+2:00",
            "2026-09-27+0200",
            "2026-09-27z",
            "2026-02-29Z",
            " 2026-09-27",
            "2026-09-27\n",
            "２０２６-09-27",
            "2026-00-10",
            "2026-13-10",
            "2026-09-00",
            "2026-09-31",
            "2026-02-29",
            "1900-02-29",
            "2026-04-31",
        ):
            with self.subTest(literal=literal), self.assertRaises(SystemExit):
                parameter_value(date(literal), "date", "test")
        for item in (20260927, None, ["2026-09-27"]):
            with self.subTest(item=item), self.assertRaises(SystemExit):
                parameter_value(date(item), "date", "test")

    def test_accepts_date_times_with_an_offset(self) -> None:
        from scripts.contracts import parameter_value

        for literal in (
            "2026-09-27T10:00:00Z",
            "2026-09-27T10:00:00+02:00",
            "2026-09-27T10:00:00.5+02:00",
            "2026-09-27T10:00:00.123456789Z",
            "2026-09-27T10:00:00.500Z",
            "2026-09-27T00:00:00+00:00",
            "2026-09-27T23:59:59-05:00",
            "2026-09-27T12:00:00+14:00",
            "2026-09-27T12:00:00-14:00",
            "2026-09-27T12:00:00+05:45",
            "0000-01-01T00:00:00Z",
            "9999-12-31T23:59:59.999999999-14:00",
            "2024-02-29T12:00:00Z",
        ):
            with self.subTest(literal=literal):
                parameter_value(date_time(literal), "dateTime", "test")

    def test_rejects_each_date_time_rule(self) -> None:
        from scripts.contracts import parameter_value

        for literal in (
            # Shape.
            "",
            "2026-09-27",
            "2026-09-27 10:00:00Z",
            "2026-09-27t10:00:00Z",
            "2026-09-27T10:00Z",
            "2026-09-27T1:00:00Z",
            "2026-09-27T10:00:00z",
            # The offset is required.
            "2026-09-27T10:00:00",
            "2026-09-27T10:00:00.5",
            # Offset shape and range.
            "2026-09-27T10:00:00+02",
            "2026-09-27T10:00:00+0200",
            "2026-09-27T10:00:00+2:00",
            "2026-09-27T10:00:00+14:01",
            "2026-09-27T10:00:00-15:00",
            "2026-09-27T10:00:00+01:60",
            "2026-09-27T10:00:00-00:00",
            "2026-09-27T10:00:00Z+01:00",
            # Fraction of one to nine digits.
            "2026-09-27T10:00:00.Z",
            "2026-09-27T10:00:00.1234567890Z",
            "2026-09-27T10:00:00,5Z",
            # A real day.
            "2026-02-29T10:00:00Z",
            "2026-13-01T10:00:00Z",
            "2026-09-31T10:00:00Z",
            # A time of day from 00:00:00 to 23:59:59.
            "2026-09-27T24:00:00Z",
            "2026-09-27T25:00:00Z",
            "2026-09-27T10:60:00Z",
            "2026-09-27T23:59:60Z",
            "2026-09-27T10:00:61Z",
            # ASCII digits only.
            "2026-09-27T１0:00:00Z",
        ):
            with self.subTest(literal=literal), self.assertRaises(SystemExit):
                parameter_value(date_time(literal), "dateTime", "test")

    def test_date_kinds_are_parameter_and_property_kinds(self) -> None:
        from scripts.contracts import (
            PROPERTY_VALUE_KINDS,
            validate_concept,
            validate_parameter_definition,
        )

        self.assertLessEqual({"date", "dateTime"}, PROPERTY_VALUE_KINDS)
        for kind, value in (
            ("date", date("2026-09-27")),
            ("dateTime", date_time("2026-09-27T10:00:00Z")),
        ):
            with self.subTest(kind=kind):
                validate_concept(
                    {
                        "id": "axioval:example.when",
                        "name": {"default": "When", "translations": {}},
                        "valueKind": kind,
                        "externalNames": [
                            {"typeSystem": "axioval:example.source", "name": "When"}
                        ],
                    },
                    "axioval:example.when",
                    "test",
                    property_definition=True,
                )
                validate_parameter_definition(
                    {
                        "id": "target",
                        "name": {"default": "Target", "translations": {}},
                        "kind": kind,
                        "required": True,
                        "defaultValue": value,
                        "allowedValues": [value],
                        "citations": [],
                    },
                    "test",
                )
        with self.assertRaises(SystemExit):
            validate_parameter_definition(
                {
                    "id": "target",
                    "name": {"default": "Target", "translations": {}},
                    "kind": "date",
                    "required": True,
                    "defaultValue": date_time("2026-09-27T10:00:00Z"),
                    "allowedValues": [],
                    "citations": [],
                },
                "test",
            )

    def test_selectors_compare_and_order_dates(self) -> None:
        for operator in (
            "equals",
            "notEquals",
            "lessThan",
            "lessThanOrEquals",
            "greaterThan",
            "greaterThanOrEquals",
        ):
            for selector in (
                property_selector(
                    "axioval:example.inspected-on", operator, date("2026-09-27")
                ),
                property_selector(
                    "axioval:example.installed-at",
                    operator,
                    date_time("2026-09-27T10:00:00+02:00"),
                ),
                property_selector(
                    "axioval:example.inspected-on",
                    operator,
                    date("2026-09-27"),
                    precision="day",
                ),
                # Day precision compares a date with a date-time either way.
                property_selector(
                    "axioval:example.inspected-on",
                    operator,
                    date_time("2026-09-27T22:30:00-05:00"),
                    precision="day",
                ),
                property_selector(
                    "axioval:example.installed-at",
                    operator,
                    date("2026-09-27"),
                    precision="day",
                ),
                property_selector(
                    "axioval:example.installed-at",
                    operator,
                    date_time("2026-09-27T10:00:00Z"),
                    precision="day",
                ),
            ):
                with self.subTest(selector=selector):
                    self.check(selector)
        self.check(property_selector("axioval:example.inspected-on", "exists"))

    def test_selectors_reject_misplaced_precision_and_mismatched_dates(self) -> None:
        for selector in (
            # Without day precision a date-time never meets a date.
            property_selector(
                "axioval:example.inspected-on",
                "equals",
                date_time("2026-09-27T10:00:00Z"),
            ),
            property_selector(
                "axioval:example.installed-at", "lessThan", date("2026-09-27")
            ),
            # Day precision does not make other kinds dates.
            property_selector(
                "axioval:example.inspected-on",
                "equals",
                text("2026-09-27"),
                precision="day",
            ),
            # Precision applies to date and dateTime values only.
            property_selector(
                "axioval:example.text", "equals", text("a"), precision="day"
            ),
            property_selector(
                "axioval:example.count",
                "greaterThan",
                {"type": "integer", "value": 1},
                precision="day",
            ),
            property_selector(
                "axioval:example.text", "matches", text("20.*"), precision="day"
            ),
            property_selector("axioval:example.inspected-on", "exists", precision="day"),
            # Only `day` exists.
            *(
                property_selector(
                    "axioval:example.inspected-on",
                    "equals",
                    date("2026-09-27"),
                    precision=precision,
                )
                for precision in ("Day", "month", "second", "", None, True, ["day"])
            ),
            # Text options do not apply to dates.
            property_selector(
                "axioval:example.inspected-on",
                "equals",
                date("2026-09-27"),
                caseSensitive=False,
            ),
            # Dates are not texts.
            property_selector(
                "axioval:example.inspected-on", "like", text("2026-*")
            ),
            property_selector(
                "axioval:example.inspected-on", "oneOf", texts("2026-09-27")
            ),
            # Literals are checked in selectors too.
            property_selector(
                "axioval:example.inspected-on", "equals", date("2026-02-29")
            ),
            property_selector(
                "axioval:example.installed-at",
                "equals",
                date_time("2026-09-27T10:00:00"),
            ),
        ):
            self.assert_rejected(selector)
        # Without a catalog, precision still needs a date or dateTime value.
        from scripts.contracts import validate_selector

        validate_selector(
            property_selector(
                "axioval:example.unbound",
                "lessThan",
                date_time("2026-09-27T10:00:00Z"),
                precision="day",
            ),
            "test",
        )
        with self.assertRaises(SystemExit):
            validate_selector(
                property_selector(
                    "axioval:example.unbound", "equals", text("a"), precision="day"
                ),
                "test",
            )

    def test_pkl_renders_dates_and_omits_an_unset_precision(self) -> None:
        evaluated = validate.evaluate(validate.ROOT / "tests/fixtures/date-values.pkl")
        validate.validate_definition_document(evaluated, "fixture")
        parameters = evaluated["definitions"]["axioval:example.dated"]["parameters"]
        self.assertEqual(parameters["target_date"]["defaultValue"], date("2024-02-29"))
        self.assertEqual(
            parameters["target_date_time"]["defaultValue"],
            date_time("2026-09-27T10:00:00.5+02:00"),
        )
        by_day, dated = parameters["compared"]["defaultValue"]["value"]["operands"]
        self.assertEqual(
            by_day,
            property_selector(
                "axioval:example.installed-at",
                "lessThan",
                date("2026-09-27"),
                precision="day",
            ),
        )
        self.assertEqual(
            dated,
            property_selector(
                "axioval:example.inspected-on",
                "greaterThanOrEquals",
                date("2000-01-01"),
            ),
        )

    def test_pkl_refuses_date_literals_of_another_shape(self) -> None:
        with tempfile.TemporaryDirectory(dir=validate.ROOT / "tests") as tmp:
            module = Path(tmp) / "value.pkl"

            def evaluate(value_class: str, literal: str) -> dict:
                module.write_text(
                    f'import "../../schema/Values.pkl"\n'
                    f'value = new Values.{value_class} {{ value = "{literal}" }}\n',
                    encoding="utf-8",
                )
                return validate.evaluate(module)

            self.assertEqual(
                evaluate("DateTimeValue", "2026-09-27T10:00:00.5+02:00")["value"],
                date_time("2026-09-27T10:00:00.5+02:00"),
            )
            for value_class, literal in (
                ("DateValue", "27.09.2026"),
                ("DateTimeValue", "2026-09-27T10:00:00"),
                ("DateTimeValue", "2026-09-27T10:00:00.1234567890Z"),
            ):
                with self.subTest(literal=literal), self.assertRaises(SystemExit):
                    evaluate(value_class, literal)


def discipline_selector(value) -> dict:
    return {"kind": "discipline", "value": value}


class DisciplineSelectorTests(unittest.TestCase):
    """Discipline selectors select the objects of sources declaring a name."""

    object_types = {"axioval:example.wall": {}}

    def check(self, selector: dict) -> None:
        from scripts.contracts import validate_selector

        validate_selector(selector, "test", self.object_types, {}, {})

    def assert_rejected(self, selector: dict) -> None:
        with self.subTest(selector=selector), self.assertRaises(SystemExit):
            self.check(selector)

    def test_accepts_tokens_alone_and_nested(self) -> None:
        for token in ("architecture", "structure", "0", "mep_hvac-2", "a" * 64):
            with self.subTest(token=token):
                self.check(discipline_selector(token))
        for selector in (
            {
                "kind": "allOf",
                "operands": [
                    {
                        "kind": "entityType",
                        "objectType": "axioval:example.wall",
                        "includeSubtypes": True,
                    },
                    discipline_selector("architecture"),
                ],
            },
            {"kind": "anyOf", "operands": [discipline_selector("structure")]},
            {"kind": "not", "operand": discipline_selector("structure")},
            related_selector(
                ["IfcRelAggregates"], discipline_selector("structure")
            ),
            related_selector(
                ["IfcRelAggregates:either"],
                {"kind": "not", "operand": discipline_selector("mep")},
                quantifier="none",
            ),
        ):
            with self.subTest(selector=selector):
                self.check(selector)

    def test_rejects_malformed_tokens(self) -> None:
        for token in (
            "",
            "Architecture",
            "-structure",
            "_structure",
            "struc ture",
            "structure\n",
            "structure.main",
            "struktur\u00e4",
            "a" * 65,
            None,
            1,
            True,
            ["structure"],
            {"value": "structure"},
        ):
            self.assert_rejected(discipline_selector(token))

    def test_rejects_extra_and_missing_keys(self) -> None:
        for selector in (
            {"kind": "discipline"},
            {**discipline_selector("structure"), "values": ["structure"]},
            {**discipline_selector("structure"), "source": "arch.ifc"},
            {**discipline_selector("structure"), "caseSensitive": False},
        ):
            self.assert_rejected(selector)

    def test_rejects_malformed_nested_discipline_selectors(self) -> None:
        for selector in (
            {"kind": "not", "operand": discipline_selector("Structure")},
            {"kind": "allOf", "operands": [discipline_selector("")]},
            related_selector(
                ["IfcRelAggregates"],
                {**discipline_selector("structure"), "extra": True},
            ),
            related_selector(
                ["IfcRelAggregates"],
                {"kind": "not", "operand": discipline_selector("a" * 65)},
            ),
        ):
            self.assert_rejected(selector)

    def test_pkl_rejects_malformed_tokens(self) -> None:
        selectors = (validate.ROOT / "schema/Selectors.pkl").as_uri()
        for token in ("", "Structure", "-mep", "a" * 65, "mep hvac"):
            with (
                self.subTest(token=token),
                tempfile.TemporaryDirectory(dir=validate.ROOT / "tests") as tmp,
            ):
                module = Path(tmp) / "discipline.pkl"
                module.write_text(
                    f'import "{selectors}"\n\n'
                    "value = new Selectors.DisciplineSelector {\n"
                    f'  value = "{token}"\n'
                    "}\n",
                    encoding="utf-8",
                )
                with self.assertRaises(SystemExit):
                    validate.evaluate(module)

    def test_pkl_renders_discipline_selectors(self) -> None:
        evaluated = validate.evaluate(
            validate.ROOT / "tests/fixtures/discipline-selector.pkl"
        )
        validate.validate_definition_document(evaluated, "fixture")
        self.assertEqual(
            evaluated["definitions"]["axioval:example.selected"]["parameters"][
                "compared"
            ]["defaultValue"]["value"],
            {
                "kind": "allOf",
                "operands": [
                    {
                        "kind": "entityType",
                        "objectType": "axioval:example.wall",
                        "includeSubtypes": True,
                    },
                    discipline_selector("architecture"),
                    {"kind": "not", "operand": discipline_selector("mep_hvac-2")},
                    related_selector(
                        ["IfcRelAggregates:either"],
                        discipline_selector("structure"),
                    ),
                ],
            },
        )


def pattern_selector(
    property_pattern, operator: str = "exists", value=None, matched="any", **fields
) -> dict:
    selector = {
        "kind": "propertyPattern",
        "propertyPattern": property_pattern,
        "matched": matched,
        "operator": operator,
    }
    if value is not None:
        selector["value"] = value
    selector.update(fields)
    return selector


class PropertyPatternSelectorTests(unittest.TestCase):
    """Property-pattern selectors match the source's own names by pattern."""

    def check(self, selector: dict, properties=None, property_sets=None) -> None:
        from scripts.contracts import validate_selector

        validate_selector(selector, "test", {}, properties or {}, property_sets or {})

    def assert_rejected(self, selector: dict) -> None:
        with self.subTest(selector=selector), self.assertRaises(SystemExit):
            self.check(selector)

    def test_accepts_patterns_comparisons_and_nesting(self) -> None:
        for selector in (
            pattern_selector("FireRating"),
            pattern_selector("FireRating", matched="all"),
            pattern_selector(
                "Is(External|LoadBearing)",
                "equals",
                {"type": "boolean", "value": True},
                matched="all",
                propertySetPattern="Pset_.*Common",
            ),
            pattern_selector(
                r"[A-Z]\w*Code",
                "oneOf",
                texts("EI 90", "EI 120"),
                caseSensitive=False,
                trim=True,
                quantifier="all",
            ),
            pattern_selector("Name", "matches", text("[A-Z].*"), caseSensitive=False),
            pattern_selector(".*Date", "lessThan", date("2030-01-01"), precision="day"),
            pattern_selector(
                "Width",
                "greaterThan",
                {"type": "quantity", "value": 0.9, "unit": "m"},
            ),
            pattern_selector(r"\p{Lu}+[^\s]*"),
            pattern_selector("^Pset$"),
            {"kind": "not", "operand": pattern_selector("Reference")},
            related_selector(["IfcRelAggregates"], pattern_selector("Status")),
        ):
            with self.subTest(selector=selector):
                self.check(selector)

    def test_patterns_are_never_bound_as_concepts(self) -> None:
        # Names no catalog declares, even names shaped like concept IDs, are
        # patterns over the source's own names.
        self.check(
            pattern_selector(
                "axioval:example.unknown", propertySetPattern="axioval:example.set"
            ),
            properties={
                property_id: {"valueKind": kind}
                for property_id, kind in PROPERTY_KINDS.items()
            },
        )
        self.check(pattern_selector("NotAConcept", propertySetPattern="Pset_.*"))

    def test_rejects_invalid_and_untranslatable_patterns(self) -> None:
        for pattern in (
            "",
            None,
            1,
            ["FireRating"],
            "(",
            "a)",
            "[ab",
            "a\\",
            r"\q",
            r"\$",
            "(?i)fire",
            "a*?",
            "a{",
            "[]",
            "[a-z-[aeiou]]",
            "[a--b]",
            r"\i\c*",
            r"\p{IsBasicLatin}",
            r"\p{Greek}",
        ):
            self.assert_rejected(pattern_selector(pattern))
            self.assert_rejected(pattern_selector("Name", propertySetPattern=pattern))

    def test_rejects_malformed_matched_and_keys(self) -> None:
        valid = pattern_selector("FireRating")
        for matched in ("none", "ALL", "", None, True, ["any"]):
            self.assert_rejected(pattern_selector("FireRating", matched=matched))
        for selector in (
            {key: value for key, value in valid.items() if key != "matched"},
            {key: value for key, value in valid.items() if key != "propertyPattern"},
            {key: value for key, value in valid.items() if key != "operator"},
            {**valid, "property": "axioval:example.text"},
            {**valid, "propertySet": "axioval:example.set"},
            {**valid, "pattern": "FireRating"},
        ):
            self.assert_rejected(selector)

    def test_rejects_malformed_comparisons(self) -> None:
        for selector in (
            pattern_selector("Name", "exists", text("a")),
            pattern_selector("Name", "equals"),
            pattern_selector("Name", "approximately", text("a")),
            pattern_selector("Name", "exists", quantifier="any"),
            pattern_selector("Name", "equals", text("a"), quantifier="some"),
            pattern_selector("Name", "exists", caseSensitive=False),
            pattern_selector("Name", "exists", trim=True),
            pattern_selector("Name", "equals", text("a"), trim="yes"),
            pattern_selector(
                "Name", "equals", {"type": "boolean", "value": True}, trim=True
            ),
            pattern_selector("Name", "matches", {"type": "boolean", "value": True}),
            pattern_selector("Name", "oneOf", text("a")),
            pattern_selector("Name", "lessThan", {"type": "boolean", "value": True}),
            pattern_selector("Name", "equals", text("a"), precision="day"),
            pattern_selector("Name", "equals", date("2030-01-01"), precision="month"),
        ):
            self.assert_rejected(selector)

    def test_pkl_rejects_malformed_property_pattern_selectors(self) -> None:
        selectors = (validate.ROOT / "schema/Selectors.pkl").as_uri()
        for fields in (
            'propertyPattern = ""\n  matched = "any"',
            'propertyPattern = "A"\n  propertySetPattern = ""\n  matched = "any"',
            'propertyPattern = "A"\n  matched = "none"',
            'propertyPattern = "A"',
            'matched = "any"',
        ):
            with (
                self.subTest(fields=fields),
                tempfile.TemporaryDirectory(dir=validate.ROOT / "tests") as tmp,
            ):
                module = Path(tmp) / "pattern.pkl"
                module.write_text(
                    f'import "{selectors}"\n\n'
                    "value = new Selectors.PropertyPatternSelector {\n"
                    f"  {fields}\n"
                    '  operator = "exists"\n'
                    "}\n",
                    encoding="utf-8",
                )
                with self.assertRaises(SystemExit):
                    validate.evaluate(module)

    def test_pkl_omits_defaults(self) -> None:
        evaluated = validate.evaluate(
            validate.ROOT / "tests/fixtures/property-pattern-selector.pkl"
        )
        validate.validate_definition_document(evaluated, "fixture")
        self.assertEqual(
            evaluated["definitions"]["axioval:example.selected"]["parameters"][
                "compared"
            ]["defaultValue"]["value"]["operands"],
            [
                pattern_selector("FireRating"),
                pattern_selector(
                    "Is(External|LoadBearing)",
                    "equals",
                    {"type": "boolean", "value": True},
                    matched="all",
                    propertySetPattern="Pset_.*Common",
                ),
                pattern_selector(
                    r"[A-Z]\w*Code",
                    "oneOf",
                    texts("EI 90", "EI 120"),
                    caseSensitive=False,
                    trim=True,
                    quantifier="all",
                ),
                pattern_selector(
                    ".*Date",
                    "lessThan",
                    date("2030-01-01"),
                    matched="all",
                    propertySetPattern="Pset_.*",
                    precision="day",
                ),
            ],
        )


REFERENCE = "axioval:example.ifc.reference"
WALL_SET = "axioval:example.ifc.pset-wall-common"


def band(below, severity: str = "warning") -> dict:
    return {"below": below, "severity": severity}


def reference_override(severity: str = "error", **fields) -> dict:
    selector = {
        "kind": "property",
        "propertySet": WALL_SET,
        "property": REFERENCE,
        "operator": "equals",
        "value": text("W1"),
    }
    selector.update(fields)
    return {"selector": selector, "severity": severity}


def category(property_id: str = REFERENCE, **fields) -> dict:
    level = {"property": property_id}
    level.update(fields)
    return level


class RuleRefinementTests(unittest.TestCase):
    """Rule instances refine severities and categories after a capability ran."""

    @classmethod
    def setUpClass(cls) -> None:
        expected = validate.ROOT / "examples/minimal/expected"
        cls.definitions = json.loads((expected / "definitions.json").read_text())
        cls.ruleset = json.loads((expected / "ruleset.json").read_text())

    def bind(self, **refinements) -> None:
        ruleset = copy.deepcopy(self.ruleset)
        for rule in ruleset["root"]["rules"]:
            rule.pop("explanatoryImages", None)
        ruleset["root"]["rules"][0].update(refinements)
        validate.bind_ruleset(ruleset, [copy.deepcopy(self.definitions)], "test")

    def assert_rejected(self, **refinements) -> None:
        with self.subTest(refinements=refinements), self.assertRaises(SystemExit):
            self.bind(**refinements)

    def test_accepts_refinements_and_their_absence(self) -> None:
        self.bind()
        self.bind(
            severityBands=[band(0.05, "info"), band(0.2), band(1)],
            severityOverrides=[
                reference_override(),
                {
                    "selector": property_selector(REFERENCE, "exists"),
                    "severity": "info",
                },
                {
                    "selector": {"kind": "not", "operand": {"kind": "all"}},
                    "severity": "warning",
                },
            ],
            categories=[
                category(propertySet=WALL_SET),
                category(),
                category(propertySet="axioval:attributes"),
                category(propertySet="axioval:type-attributes"),
                category(path=["IfcRelContainedInSpatialStructure:backward"]),
                category(path=["IfcRelAggregates+", "IfcRelNests:either"]),
                category(path=["IfcRelAggregates:backward+", "IfcRelNests:either+"]),
                category(
                    path=[
                        "IfcRelFillsElement|IfcRelVoidsElement:backward+",
                        "IfcRelNests|axioval:derived.adjacent-space",
                    ]
                ),
                category(
                    propertySet="axioval:attributes",
                    path=[
                        "axioval:derived.adjacent-space",
                        "axioval:derived.contained-in-space;horizontal=0.25;vertical=0.5",
                        "axioval:derived.overlapping-group-space;ratio=0.9:backward",
                    ],
                ),
            ],
        )

    def test_rejects_bands_that_are_not_positive_finite_and_ascending(self) -> None:
        for bands in (
            [],
            [band(0)],
            [band(-0.1)],
            [band(float("inf"))],
            [band(float("nan"))],
            [band(True)],
            [band("0.1")],
            [band(0.2), band(0.1)],
            [band(0.1), band(0.1)],
            [band(0.1, "fatal")],
            [{"below": 0.1}],
            [{**band(0.1), "above": 0.0}],
            {"below": 0.1, "severity": "info"},
        ):
            self.assert_rejected(severityBands=bands)

    def test_override_selectors_bind_against_the_concept_catalogs(self) -> None:
        for overrides in (
            [],
            [reference_override(property="axioval:example.unknown")],
            [reference_override(propertySet="axioval:example.unknown")],
            [reference_override(value={"type": "integer", "value": 1})],
            [
                {
                    "selector": {
                        "kind": "entityType",
                        "objectType": "axioval:example.unknown",
                        "includeSubtypes": True,
                    },
                    "severity": "error",
                }
            ],
            [reference_override("fatal")],
            [{"selector": {"kind": "all"}}],
            [{**reference_override(), "when": "always"}],
        ):
            self.assert_rejected(severityOverrides=overrides)

    def test_rejects_unbound_or_malformed_categories(self) -> None:
        for levels in (
            [],
            [category("axioval:example.unknown")],
            [category("Reference")],
            [category(propertySet="axioval:example.unknown")],
            [category(propertySet="axioval:unknown-reserved")],
            [category(path=[])],
            [category(path=[""])],
            [category(path=["Ifc Rel"])],
            [category(path=["IfcRelAggregates:sideways"])],
            [category(path=["IfcRelAggregates|"])],
            [category(path=["IfcRelAggregates|IfcRelAggregates"])],
            [category(path=["IfcRelAggregates:backward|IfcRelNests"])],
            [category(path=["axioval:derived."])],
            [category(path=["axioval:derived.adjacent-space;reach"])],
            [category(path=["axioval:derived.adjacent-space:sideways"])],
            [category(path="IfcRelAggregates")],
            [{"propertySet": WALL_SET}],
            [{**category(), "quantifier": "any"}],
        ):
            self.assert_rejected(categories=levels)

    def test_pkl_renders_refinements_and_omits_them_when_empty(self) -> None:
        rules = (validate.ROOT / "schema/RuleSets.pkl").as_uri()
        selectors = (validate.ROOT / "schema/Selectors.pkl").as_uri()
        values = (validate.ROOT / "schema/Values.pkl").as_uri()
        refined = f"""
      severityBands {{
        new {{ below = 0.05; severity = "info" }}
        new {{ below = 0.2; severity = "warning" }}
      }}
      severityOverrides {{
        new {{
          selector = new Selectors.PropertySelector {{
            propertySet = "{WALL_SET}"
            property = "{REFERENCE}"
            operator = "equals"
            value = new Values.StringValue {{ value = "W1" }}
          }}
          severity = "error"
        }}
      }}
      categories {{
        new {{ propertySet = "axioval:attributes"; property = "{REFERENCE}" }}
        new {{
          property = "{REFERENCE}"
          path {{ "axioval:derived.adjacent-space;reach=1" }}
        }}
      }}"""
        with tempfile.TemporaryDirectory(dir=validate.ROOT / "tests") as tmp:
            module = Path(tmp) / "refinements.pkl"
            module.write_text(
                f'amends "{rules}"\n\n'
                f'import "{selectors}"\n'
                f'import "{values}"\n\n'
                'package { id = "axioval:example.refinements"; version = "0.1.0"; '
                'name { default = "Refinements" } }\n'
                'definitionPackages { "axioval:example.definitions" }\n'
                "root {\n"
                '  id = "root"\n'
                '  name { default = "Root" }\n'
                "  rules {\n"
                "    new {\n"
                '      id = "refined"\n'
                '      definitionId = "axioval:example.property-exists"\n'
                '      name { default = "Refined" }\n'
                f"{refined}\n"
                "    }\n"
                "    new {\n"
                '      id = "plain"\n'
                '      definitionId = "axioval:example.property-exists"\n'
                '      name { default = "Plain" }\n'
                "      severityBands {}\n"
                "      categories {}\n"
                "    }\n"
                "  }\n"
                "}\n",
                encoding="utf-8",
            )
            evaluated = validate.evaluate(module)
            refined_rule, plain = evaluated["root"]["rules"]
            self.assertEqual(
                refined_rule["severityBands"],
                [band(0.05, "info"), band(0.2, "warning")],
            )
            self.assertEqual(
                refined_rule["severityOverrides"],
                [reference_override()],
            )
            self.assertEqual(
                refined_rule["categories"],
                [
                    category(propertySet="axioval:attributes"),
                    category(path=["axioval:derived.adjacent-space;reach=1"]),
                ],
            )
            for key in ("severityBands", "severityOverrides", "categories"):
                self.assertNotIn(key, plain)
            self.assertNotIn("description", plain)

            for bands in (
                'new { below = 0.2; severity = "info" }\n'
                'new { below = 0.1; severity = "warning" }',
                'new { below = 0.0; severity = "info" }',
                'new { below = NaN; severity = "info" }',
                'new { below = 0.1; severity = "fatal" }',
            ):
                broken = Path(tmp) / "broken.pkl"
                broken.write_text(
                    f'import "{rules}"\n\n'
                    "bands: Listing<RuleSets.SeverityBand>"
                    "(RuleSets.ascendingBands(this)) = new {\n"
                    f"{bands}\n}}\n",
                    encoding="utf-8",
                )
                with self.subTest(bands=bands), self.assertRaises(SystemExit):
                    validate.evaluate(broken)


def classification_selector(system="uniclass", include_descendants=False, **fields):
    selector = {
        "kind": "classification",
        "system": system,
        "includeDescendants": include_descendants,
    }
    selector.update(fields)
    return selector


def source_selector(field, operator="exists", value=None, **fields) -> dict:
    selector = {"kind": "source", "field": field, "operator": operator}
    if value is not None:
        selector["value"] = value
    selector.update(fields)
    return selector


class PresenceOperatorTests(unittest.TestCase):
    """`isEmpty` and `isNotEmpty` judge presence as `exists` does."""

    properties = {
        property_id: {"valueKind": kind} for property_id, kind in PROPERTY_KINDS.items()
    }

    def check(self, selector: dict) -> None:
        from scripts.contracts import validate_selector

        validate_selector(selector, "test", {}, self.properties, {})

    def test_accepts_presence_operators_without_a_value(self) -> None:
        for operator in ("isEmpty", "isNotEmpty"):
            for selector in (
                property_selector("axioval:example.text", operator),
                property_selector("axioval:example.tags", operator),
                property_selector("axioval:example.flag", operator, trim=False),
                pattern_selector("Fire.*", operator),
                source_selector("project", operator),
            ):
                with self.subTest(selector=selector):
                    self.check(selector)

    def test_rejects_a_value_quantifier_or_text_option(self) -> None:
        for operator in ("isEmpty", "isNotEmpty"):
            for build in (
                lambda **fields: property_selector(
                    "axioval:example.text", operator, **fields
                ),
                lambda **fields: pattern_selector("Fire.*", operator, **fields),
                lambda **fields: source_selector("project", operator, **fields),
            ):
                for fields in (
                    {"value": text("")},
                    {"quantifier": "any"},
                    {"quantifier": "all"},
                    {"caseSensitive": False},
                    {"trim": True},
                ):
                    selector = build(**fields)
                    with self.subTest(selector=selector), self.assertRaises(
                        SystemExit
                    ):
                        self.check(selector)
        with self.assertRaises(SystemExit):
            self.check(property_selector("axioval:example.text", "isBlank"))


class ClassificationSelectorTests(unittest.TestCase):
    """Classification selectors name a code, a code pattern, or a system."""

    def check(self, selector: dict) -> None:
        from scripts.contracts import validate_selector

        validate_selector(selector, "test", {}, {}, {})

    def assert_rejected(self, selector: dict) -> None:
        with self.subTest(selector=selector), self.assertRaises(SystemExit):
            self.check(selector)

    def test_accepts_codes_patterns_and_whole_systems(self) -> None:
        for selector in (
            classification_selector("din276", code="331"),
            classification_selector("din276", True, code="331"),
            classification_selector(codePattern="Ss_25_.*"),
            classification_selector(
                include_descendants=True, codePattern=r"Ss_25_\d{2}"
            ),
            classification_selector(),
            {"kind": "not", "operand": classification_selector()},
            related_selector(["IfcRelAggregates"], classification_selector()),
        ):
            with self.subTest(selector=selector):
                self.check(selector)

    def test_rejects_malformed_classification_selectors(self) -> None:
        for selector in (
            classification_selector(code="331", codePattern="3.*"),
            classification_selector(include_descendants=True),
            classification_selector(code=""),
            classification_selector(code=331),
            classification_selector(codePattern=""),
            classification_selector(codePattern="[a-z-[aeiou]]"),
            classification_selector(codePattern=r"\p{IsBasicLatin}"),
            classification_selector(codePattern="("),
            classification_selector(""),
            classification_selector(None),
            classification_selector(include_descendants="yes"),
            {"kind": "classification", "system": "uniclass"},
            classification_selector(code="331", pattern="3.*"),
        ):
            self.assert_rejected(selector)

    def test_pkl_rejects_contradictory_classification_selectors(self) -> None:
        selectors = (validate.ROOT / "schema/Selectors.pkl").as_uri()
        for fields in (
            'code = "331"; codePattern = "3.*"',
            "includeDescendants = true",
            'codePattern = ""',
        ):
            with (
                self.subTest(fields=fields),
                tempfile.TemporaryDirectory(dir=validate.ROOT / "tests") as tmp,
            ):
                module = Path(tmp) / "classification.pkl"
                module.write_text(
                    f'import "{selectors}"\n\n'
                    "value = new Selectors.ClassificationSelector {\n"
                    f'  system = "uniclass"; {fields}\n'
                    "}\n",
                    encoding="utf-8",
                )
                with self.assertRaises(SystemExit):
                    validate.evaluate(module)


class SourceSelectorTests(unittest.TestCase):
    """Source selectors compare what a source states about itself as text."""

    def check(self, selector: dict) -> None:
        from scripts.contracts import validate_selector

        validate_selector(selector, "test", {}, {}, {})

    def assert_rejected(self, selector: dict) -> None:
        with self.subTest(selector=selector), self.assertRaises(SystemExit):
            self.check(selector)

    def test_accepts_every_field_and_text_comparison(self) -> None:
        for selector in (
            source_selector("fileName", "like", text("*.ifc")),
            source_selector(
                "application",
                "contains",
                text("modeller"),
                caseSensitive=False,
                trim=True,
                quantifier="all",
            ),
            source_selector("schema", "oneOf", texts("IFC4", "IFC4X3_ADD2")),
            source_selector("project", "matches", text("P-[0-9]+")),
            source_selector("project", "greaterThan", text("A")),
            source_selector("timestamp", "like", text("2026-09-*")),
            source_selector("timestamp", "lessThan", text("2026-09-28T00:00:00")),
            source_selector("application", "exists"),
            {"kind": "not", "operand": source_selector("schema", "isEmpty")},
        ):
            with self.subTest(selector=selector):
                self.check(selector)

    def test_rejects_unknown_fields_keys_and_non_text_values(self) -> None:
        for selector in (
            source_selector("author", "equals", text("x")),
            source_selector("FileName", "equals", text("x")),
            source_selector("Timestamp", "equals", text("x")),
            source_selector("timestamp", "lessThan", date("2026-09-28")),
            source_selector(None, "equals", text("x")),
            source_selector("schema", "equals"),
            source_selector("schema", "equals", {"type": "integer", "value": 4}),
            source_selector("schema", "equals", date("2026-09-27")),
            source_selector("schema", "lessThan", {"type": "boolean", "value": True}),
            source_selector("schema", "oneOf", text("IFC4")),
            source_selector("schema", "equals", text("IFC4"), precision="day"),
            source_selector("schema", "equals", text("IFC4"), quantifier="some"),
            source_selector("schema", "equals", text("IFC4"), property="x:y"),
            {"kind": "source", "operator": "exists"},
            {"kind": "source", "field": "schema"},
        ):
            self.assert_rejected(selector)


class PresenceClassificationSourceRenderingTests(unittest.TestCase):
    def test_pkl_omits_defaults_and_unset_codes(self) -> None:
        evaluated = validate.evaluate(
            validate.ROOT
            / "tests/fixtures/presence-classification-source-selectors.pkl"
        )
        validate.validate_definition_document(evaluated, "fixture")
        self.assertEqual(
            evaluated["definitions"]["axioval:example.selected"]["parameters"][
                "compared"
            ]["defaultValue"]["value"]["operands"],
            [
                property_selector("axioval:example.reference", "isEmpty"),
                pattern_selector("Fire.*", "isNotEmpty"),
                classification_selector("din276", code="331"),
                classification_selector(
                    include_descendants=True, codePattern="Ss_25_.*"
                ),
                classification_selector(),
                source_selector(
                    "application",
                    "like",
                    text("Modeller*"),
                    caseSensitive=False,
                    trim=True,
                    quantifier="any",
                ),
                source_selector("schema", "equals", text("IFC4")),
                source_selector("project", "isNotEmpty"),
                source_selector("timestamp", "like", text("2026-*")),
            ],
        )



def rule_outcome(rule: str, outcome: str = "failed") -> dict:
    return {"kind": "ruleOutcome", "rule": rule, "outcome": outcome}


def gate(rule: str, condition: str = "failedObjects") -> dict:
    return {"rule": rule, "condition": condition}


SELECTED = "axioval:example.selected"


class RuleGateTests(unittest.TestCase):
    """Rules gate on, and select by, other rules' outcomes in one ruleset."""

    @classmethod
    def setUpClass(cls) -> None:
        expected = validate.ROOT / "examples/minimal/expected"
        cls.definitions = json.loads((expected / "definitions.json").read_text())
        cls.ruleset = json.loads((expected / "ruleset.json").read_text())

    def documents(self, default: dict | None = None) -> tuple[dict, dict]:
        """Root rules `a` and `b`, and rule `c` in folder `sub`."""
        ruleset = copy.deepcopy(self.ruleset)
        definitions = copy.deepcopy(self.definitions)
        parameter = {
            "id": "subject",
            "name": {"default": "Subject", "translations": {}},
            "kind": "selector",
            "required": default is None,
            "allowedValues": [],
        }
        if default is not None:
            parameter["defaultValue"] = {"type": "selector", "value": default}
        definitions["definitions"][SELECTED] = {
            "id": SELECTED,
            "name": {"default": "Selected", "translations": {}},
            "capability": "axioval:capability.selected",
            "parameters": {"subject": parameter},
            "tags": [],
        }
        template = ruleset["root"]["rules"][0]
        template.pop("explanatoryImages", None)
        template.pop("requirements", None)

        def rule(rule_id: str) -> dict:
            instance = copy.deepcopy(template)
            instance["id"] = rule_id
            return instance

        ruleset["root"]["rules"] = [rule("a"), rule("b")]
        ruleset["root"]["folders"] = [
            {
                "id": "sub",
                "name": {"default": "Sub", "translations": {}},
                "rules": [rule("c")],
                "folders": [],
            }
        ]
        return ruleset, definitions

    @staticmethod
    def rules(ruleset: dict) -> dict:
        root = ruleset["root"]
        return {rule["id"]: rule for rule in root["rules"] + root["folders"][0]["rules"]}

    def bind(self, ruleset: dict, definitions: dict) -> None:
        validate.bind_ruleset(ruleset, [definitions], "test")

    def assert_rejected(self, ruleset: dict, definitions: dict) -> None:
        with self.assertRaises(SystemExit):
            self.bind(ruleset, definitions)

    def selecting(self, rules: dict, rule_id: str, selector: dict) -> None:
        rules[rule_id]["definitionId"] = SELECTED
        rules[rule_id]["parameters"] = {
            "subject": {"type": "selector", "value": selector}
        }

    def test_accepts_gates_on_rules_and_folders(self) -> None:
        ruleset, definitions = self.documents()
        self.bind(ruleset, definitions)
        rules = self.rules(ruleset)
        for condition in ("allIfPassed", "allIfFailed", "passedObjects", "failedObjects"):
            rules["b"]["gate"] = gate("a", condition)
            ruleset["root"]["folders"][0]["gate"] = gate("b", condition)
            with self.subTest(condition=condition):
                self.bind(ruleset, definitions)
        # A disabled rule may gate another.
        rules["a"]["enabled"] = False
        self.bind(ruleset, definitions)

    def test_accepts_namespaced_folder_annotations(self) -> None:
        ruleset, definitions = self.documents()
        ruleset["root"]["folders"][0]["annotations"] = {
            "ids:specification": "<specification name=\"Walls\"/>",
            "ids:info.title": "Walls",
        }
        self.bind(ruleset, definitions)

    def test_rejects_malformed_folder_annotations(self) -> None:
        for annotations in (
            {},
            {"specification": "x"},
            {"IDS:specification": "x"},
            {"ids:": "x"},
            {"ids:specification": 1},
            ["ids:specification"],
        ):
            ruleset, definitions = self.documents()
            ruleset["root"]["folders"][0]["annotations"] = annotations
            with self.subTest(annotations=annotations):
                self.assert_rejected(ruleset, definitions)

    def test_accepts_rule_outcome_selectors_wherever_selectors_go(self) -> None:
        ruleset, definitions = self.documents()
        rules = self.rules(ruleset)
        rules["b"]["applicability"] = {
            "kind": "allOf",
            "operands": [
                rule_outcome("a"),
                {"kind": "not", "operand": rule_outcome("c", "passed")},
            ],
        }
        rules["c"]["severityOverrides"] = [
            {"selector": rule_outcome("a", "passed"), "severity": "warning"}
        ]
        self.selecting(
            rules,
            "a",
            {
                "kind": "related",
                "path": ["IfcRelFillsElement:backward"],
                "selector": {"kind": "not", "operand": {"kind": "all"}},
            },
        )
        self.bind(ruleset, definitions)
        # `c` reads `a`, so `a` reading `c` closes a cycle.
        rules["a"]["parameters"]["subject"]["value"]["selector"] = rule_outcome("c")
        self.assert_rejected(ruleset, definitions)

    def test_rejects_malformed_gates_and_selectors(self) -> None:
        for field, candidate in (
            ("gate", gate("a", "sometimes")),
            ("gate", gate("")),
            ("gate", gate("Not-An-Id")),
            ("gate", {"rule": "a"}),
            ("gate", {**gate("a"), "negated": True}),
            ("gate", None),
            ("gate", "a"),
            ("applicability", rule_outcome("a", "undecided")),
            ("applicability", {"kind": "ruleOutcome", "rule": "a"}),
            ("applicability", {**rule_outcome("a"), "negated": True}),
            ("applicability", rule_outcome(7)),
        ):
            ruleset, definitions = self.documents()
            self.rules(ruleset)["b"][field] = candidate
            with self.subTest(field=field, candidate=candidate):
                self.assert_rejected(ruleset, definitions)
        ruleset, definitions = self.documents()
        ruleset["root"]["folders"][0]["gate"] = gate("a", "never")
        self.assert_rejected(ruleset, definitions)

    def test_rejects_unknown_rules_and_folder_ids(self) -> None:
        for field, candidate in (
            ("gate", gate("missing")),
            ("gate", gate("sub")),
            ("gate", gate("root")),
            ("applicability", rule_outcome("missing")),
        ):
            ruleset, definitions = self.documents()
            self.rules(ruleset)["b"][field] = candidate
            with self.subTest(field=field, candidate=candidate):
                self.assert_rejected(ruleset, definitions)
        ruleset, definitions = self.documents()
        ruleset["root"]["folders"][0]["gate"] = gate("missing")
        self.assert_rejected(ruleset, definitions)

    def test_rejects_self_references_and_cycles(self) -> None:
        cases = (
            {"a": {"gate": gate("a")}},
            {"a": {"applicability": rule_outcome("a")}},
            {"a": {"severityOverrides": [
                {"selector": rule_outcome("a"), "severity": "info"}
            ]}},
            {"a": {"gate": gate("b")}, "b": {"gate": gate("a", "allIfPassed")}},
            {
                "a": {"gate": gate("b")},
                "b": {"applicability": rule_outcome("c")},
                "c": {"severityOverrides": [
                    {"selector": rule_outcome("a"), "severity": "info"}
                ]},
            },
        )
        for case in cases:
            ruleset, definitions = self.documents()
            rules = self.rules(ruleset)
            for rule_id, fields in case.items():
                rules[rule_id].update(copy.deepcopy(fields))
            with self.subTest(case=case):
                self.assert_rejected(ruleset, definitions)
        # A cycle through a selector parameter, and through a folder's gate.
        ruleset, definitions = self.documents()
        rules = self.rules(ruleset)
        self.selecting(rules, "a", rule_outcome("c"))
        rules["c"]["gate"] = gate("a")
        self.assert_rejected(ruleset, definitions)
        ruleset, definitions = self.documents()
        ruleset["root"]["folders"][0]["gate"] = gate("a")
        self.rules(ruleset)["a"]["applicability"] = rule_outcome("c")
        self.assert_rejected(ruleset, definitions)

    def test_a_folder_gate_names_a_rule_outside_the_folder(self) -> None:
        ruleset, definitions = self.documents()
        ruleset["root"]["folders"][0]["gate"] = gate("c")
        self.assert_rejected(ruleset, definitions)
        ruleset["root"]["gate"] = gate("a")
        del ruleset["root"]["folders"][0]["gate"]
        self.assert_rejected(ruleset, definitions)

    def test_defaulted_selector_parameters_count_as_references(self) -> None:
        ruleset, definitions = self.documents(default=rule_outcome("b"))
        rules = self.rules(ruleset)
        rules["a"]["definitionId"] = SELECTED
        rules["a"]["parameters"] = {}
        self.bind(ruleset, definitions)
        rules["b"]["gate"] = gate("a")
        self.assert_rejected(ruleset, definitions)
        # A bound value replaces the default.
        rules["a"]["parameters"] = {
            "subject": {"type": "selector", "value": {"kind": "all"}}
        }
        self.bind(ruleset, definitions)

    def test_accepts_auxiliary_rules_an_enabled_rule_reads(self) -> None:
        cases = (
            {"b": {"gate": gate("a")}},
            {"b": {"gate": gate("a", "allIfPassed")}},
            {"b": {"applicability": rule_outcome("a")}},
            {"c": {"severityOverrides": [
                {"selector": rule_outcome("a", "passed"), "severity": "info"}
            ]}},
            # An auxiliary rule may read another; the chain ends in a report.
            {"b": {"gate": gate("a"), "auxiliary": True}, "c": {"gate": gate("b")}},
        )
        for case in cases:
            ruleset, definitions = self.documents()
            rules = self.rules(ruleset)
            rules["a"]["auxiliary"] = True
            for rule_id, fields in case.items():
                rules[rule_id].update(copy.deepcopy(fields))
            with self.subTest(case=case):
                self.bind(ruleset, definitions)
        # Through a folder's gate, and through a defaulted selector parameter.
        ruleset, definitions = self.documents()
        self.rules(ruleset)["a"]["auxiliary"] = True
        ruleset["root"]["folders"][0]["gate"] = gate("a")
        self.bind(ruleset, definitions)
        ruleset, definitions = self.documents(default=rule_outcome("a"))
        rules = self.rules(ruleset)
        rules["a"]["auxiliary"] = True
        rules["b"]["definitionId"] = SELECTED
        rules["b"]["parameters"] = {}
        self.bind(ruleset, definitions)
        # A disabled auxiliary rule never runs, so nothing need read it.
        ruleset, definitions = self.documents()
        rules = self.rules(ruleset)
        rules["a"].update(auxiliary=True, enabled=False)
        self.bind(ruleset, definitions)

    def test_rejects_unread_and_malformed_auxiliary_rules(self) -> None:
        ruleset, definitions = self.documents()
        self.rules(ruleset)["a"]["auxiliary"] = True
        self.assert_rejected(ruleset, definitions)
        # Read only by a disabled rule, or only by another unread one.
        for case in (
            {"b": {"gate": gate("a"), "enabled": False}},
            {"b": {"applicability": rule_outcome("a"), "auxiliary": True}},
        ):
            ruleset, definitions = self.documents()
            rules = self.rules(ruleset)
            rules["a"]["auxiliary"] = True
            for rule_id, fields in case.items():
                rules[rule_id].update(copy.deepcopy(fields))
            with self.subTest(case=case):
                self.assert_rejected(ruleset, definitions)
        for flag in (False, "true", 1, None, [True]):
            ruleset, definitions = self.documents()
            rules = self.rules(ruleset)
            rules["a"]["auxiliary"] = flag
            rules["b"]["gate"] = gate("a")
            with self.subTest(flag=flag):
                self.assert_rejected(ruleset, definitions)

    def test_pkl_renders_gates_and_rule_outcome_selectors(self) -> None:
        rules = (validate.ROOT / "schema/RuleSets.pkl").as_uri()
        selectors = (validate.ROOT / "schema/Selectors.pkl").as_uri()

        def module(body: str) -> str:
            return (
                f'amends "{rules}"\n\n'
                f'import "{selectors}"\n\n'
                'package { id = "axioval:example.gates"; version = "0.1.0"; '
                'name { default = "Gates" } }\n'
                'definitionPackages { "axioval:example.definitions" }\n'
                "root {\n"
                '  id = "root"\n'
                '  name { default = "Root" }\n'
                f"{body}\n"
                "}\n"
            )

        body = """  rules {
    new {
      id = "door-type"
      definitionId = "axioval:example.property-exists"
      name { default = "Door type" }
      auxiliary = true
    }
  }
  folders {
    new {
      id = "hardware"
      name { default = "Hardware" }
      gate { rule = "door-type"; condition = "failedObjects" }
      rules {
        new {
          id = "closer"
          definitionId = "axioval:example.property-exists"
          name { default = "Closer" }
          gate { rule = "door-type"; condition = "allIfFailed" }
          applicability = new Selectors.RuleOutcomeSelector {
            rule = "door-type"
            outcome = "passed"
          }
        }
      }
    }
  }"""
        with tempfile.TemporaryDirectory(dir=validate.ROOT / "tests") as tmp:
            path = Path(tmp) / "gates.pkl"
            path.write_text(module(body), encoding="utf-8")
            evaluated = validate.evaluate(path)
            door_type = evaluated["root"]["rules"][0]
            hardware = evaluated["root"]["folders"][0]
            closer = hardware["rules"][0]
            self.assertNotIn("gate", door_type)
            self.assertIs(door_type["auxiliary"], True)
            self.assertNotIn("auxiliary", closer)
            self.assertNotIn("gate", evaluated["root"])
            self.assertEqual(hardware["gate"], gate("door-type"))
            self.assertEqual(closer["gate"], gate("door-type", "allIfFailed"))
            self.assertEqual(closer["applicability"], rule_outcome("door-type", "passed"))
            for broken in (
                body.replace('condition = "failedObjects"', 'condition = "sometimes"'),
                body.replace('outcome = "passed"', 'outcome = "undecided"'),
                body.replace('rule = "door-type"\n', 'rule = "Door Type"\n'),
                body.replace("auxiliary = true", 'auxiliary = "yes"'),
            ):
                self.assertNotEqual(broken, body)
                path.write_text(module(broken), encoding="utf-8")
                with self.subTest(broken=broken), self.assertRaises(SystemExit):
                    validate.evaluate(path)



CLASSIFICATION_SET = "axioval:classification"


def classification_row(class_name: str, selector: dict | None = None) -> dict:
    return {
        "selector": selector or property_selector(REFERENCE, "like", text("W*")),
        "class": class_name,
    }


def classification(class_id: str, *rows: dict, **fields) -> dict:
    definition = {
        "id": class_id,
        "name": {"default": class_id, "translations": {}},
        "rows": list(rows) or [classification_row("wall")],
    }
    definition.update(fields)
    return definition


def reads_class(class_id: str, operator: str = "exists", value=None, **fields) -> dict:
    return property_selector(
        class_id, operator, value, propertySet=CLASSIFICATION_SET, **fields
    )


class ClassificationTests(unittest.TestCase):
    """A ruleset derives classes by ordered rows and reads them as properties."""

    @classmethod
    def setUpClass(cls) -> None:
        expected = validate.ROOT / "examples/minimal/expected"
        cls.definitions = json.loads((expected / "definitions.json").read_text())
        cls.ruleset = json.loads((expected / "ruleset.json").read_text())

    def bind(self, classifications=None, **rule_fields) -> None:
        ruleset = copy.deepcopy(self.ruleset)
        rule = ruleset["root"]["rules"][0]
        rule.pop("explanatoryImages", None)
        rule.pop("requirements", None)
        rule.update(copy.deepcopy(rule_fields))
        if classifications is not None:
            ruleset["classifications"] = copy.deepcopy(classifications)
        validate.bind_ruleset(ruleset, [copy.deepcopy(self.definitions)], "test")

    def assert_rejected(self, classifications=None, **rule_fields) -> None:
        with (
            self.subTest(classifications=classifications, rule=rule_fields),
            self.assertRaises(SystemExit),
        ):
            self.bind(classifications, **rule_fields)

    def test_accepts_classifications_and_their_absence(self) -> None:
        self.bind()
        self.bind(
            {
                "use": classification(
                    "use",
                    classification_row("office"),
                    classification_row("other", {"kind": "all"}),
                    description={"default": "Use", "translations": {}},
                ),
                "zone": classification(
                    "zone",
                    classification_row("dry", reads_class("use", "equals", text("office"))),
                    classification_row(
                        "wet",
                        {
                            "kind": "related",
                            "path": ["IfcRelAggregates:backward"],
                            "selector": {"kind": "not", "operand": reads_class("use")},
                        },
                    ),
                    mode="allMatch",
                ),
                "any name at all": classification("any name at all", mode="firstMatch"),
            }
        )

    def test_rejects_malformed_classifications(self) -> None:
        for classifications in (
            {},
            [classification("use")],
            {"use": classification("zone")},
            {" ": classification(" ")},
            {"": classification("")},
            {"use": classification("use", mode="lastMatch")},
            {"use": {**classification("use"), "rows": []}},
            {"use": classification("use", classification_row(" "))},
            {"use": classification("use", classification_row(""))},
            {"use": classification("use", {"selector": {"kind": "all"}})},
            {"use": classification("use", {**classification_row("a"), "weight": 1})},
            {"use": {**classification("use"), "priority": 1}},
            {"use": {k: v for k, v in classification("use").items() if k != "name"}},
        ):
            self.assert_rejected(classifications)

    def test_rows_bind_against_the_concepts_and_read_no_rule(self) -> None:
        for selector in (
            property_selector("axioval:example.unknown", "exists"),
            property_selector(REFERENCE, "exists", propertySet="axioval:example.unknown"),
            property_selector(REFERENCE, "equals", {"type": "integer", "value": 1}),
            {"kind": "entityType", "objectType": "axioval:example.unknown",
             "includeSubtypes": True},
            {"kind": "ruleOutcome", "rule": "wall-reference-required",
             "outcome": "failed"},
            {"kind": "not", "operand": {"kind": "ruleOutcome",
             "rule": "wall-reference-required", "outcome": "passed"}},
            reads_class("undeclared"),
        ):
            self.assert_rejected({"use": classification("use", classification_row("a", selector))})

    def test_rejects_classifications_reading_one_another_in_a_cycle(self) -> None:
        for classifications in (
            {"use": classification("use", classification_row("a", reads_class("use")))},
            {
                "use": classification("use", classification_row("a", reads_class("zone"))),
                "zone": classification(
                    "zone",
                    classification_row(
                        "b", {"kind": "anyOf", "operands": [reads_class("use")]}
                    ),
                ),
            },
        ):
            self.assert_rejected(classifications)

    def test_references_name_declared_classifications(self) -> None:
        declared = {
            "use": classification("use"),
            "zones": classification("zones", mode="allMatch"),
        }
        override = {"selector": reads_class("use", "equals", text("office")),
                    "severity": "info"}
        self.bind(
            declared,
            applicability={"kind": "not", "operand": reads_class("use", "isEmpty")},
            severityOverrides=[
                override,
                {"selector": reads_class("zones", "equals", text("wet"),
                                         quantifier="any"), "severity": "warning"},
            ],
            categories=[{"propertySet": CLASSIFICATION_SET, "property": "use"}],
            parameters={
                "property": {
                    "type": "propertyReference",
                    "propertySet": CLASSIFICATION_SET,
                    "property": "use",
                }
            },
        )
        for fields in (
            {"applicability": reads_class("undeclared")},
            {"severityOverrides": [{**override, "selector": reads_class("undeclared")}]},
            {"categories": [{"propertySet": CLASSIFICATION_SET, "property": "undeclared"}]},
            {"categories": [{"propertySet": CLASSIFICATION_SET, "property": " "}]},
            {"parameters": {"property": {"type": "propertyReference",
                                         "propertySet": CLASSIFICATION_SET,
                                         "property": "undeclared"}}},
            # An all-match classification is a list, compared with a quantifier.
            {"applicability": reads_class("zones", "equals", text("wet"))},
            {"applicability": reads_class("use", "equals", {"type": "integer", "value": 1})},
        ):
            self.assert_rejected(declared, **fields)
        # Without classifications, the reserved set names nothing.
        self.assert_rejected(applicability=reads_class("use"))

    def test_the_reserved_set_needs_no_concept_but_a_non_blank_name(self) -> None:
        from scripts.contracts import parameter_value, validate_selector

        validate_selector(reads_class("any name"), "test")
        parameter_value(
            {"type": "propertyReference", "propertySet": CLASSIFICATION_SET,
             "property": "any name"},
            "propertyReference",
            "test",
        )
        for selector in (reads_class(" "), reads_class(""), property_selector("use", "exists")):
            with self.subTest(selector=selector), self.assertRaises(SystemExit):
                validate_selector(selector, "test")
        with self.assertRaises(SystemExit):
            parameter_value(
                {"type": "propertyReference", "property": "use"},
                "propertyReference",
                "test",
            )

    def test_pkl_renders_classifications_and_omits_them_when_empty(self) -> None:
        rules = (validate.ROOT / "schema/RuleSets.pkl").as_uri()
        selectors = (validate.ROOT / "schema/Selectors.pkl").as_uri()
        values = (validate.ROOT / "schema/Values.pkl").as_uri()

        def module(body: str) -> str:
            return (
                f'amends "{rules}"\n\n'
                f'import "{selectors}"\n'
                f'import "{values}"\n\n'
                'package { id = "axioval:example.classes"; version = "0.1.0"; '
                'name { default = "Classes" } }\n'
                'definitionPackages { "axioval:example.definitions" }\n'
                'root { id = "root"; name { default = "Root" } }\n'
                f"{body}\n"
            )

        body = f"""classifications {{
  ["use"] {{
    id = "use"
    name {{ default = "Use" }}
    rows {{
      new {{
        selector = new Selectors.PropertySelector {{
          property = "{REFERENCE}"
          operator = "like"
          value = new Values.StringValue {{ value = "W*" }}
        }}
        `class` = "wall"
      }}
    }}
  }}
  ["zones"] {{
    id = "zones"
    name {{ default = "Zones" }}
    mode = "allMatch"
    rows {{
      new {{
        selector = new Selectors.PropertySelector {{
          propertySet = "{CLASSIFICATION_SET}"
          property = "use"
          operator = "equals"
          value = new Values.StringValue {{ value = "wall" }}
        }}
        `class` = "dry"
      }}
    }}
  }}
}}"""
        with tempfile.TemporaryDirectory(dir=validate.ROOT / "tests") as tmp:
            path = Path(tmp) / "classes.pkl"
            path.write_text(module(body), encoding="utf-8")
            evaluated = validate.evaluate(path)
            self.assertEqual(
                evaluated["classifications"],
                {
                    "use": classification(
                        "use",
                        classification_row("wall"),
                        name={"default": "Use", "translations": {}},
                    ),
                    "zones": classification(
                        "zones",
                        classification_row(
                            "dry", reads_class("use", "equals", text("wall"))
                        ),
                        name={"default": "Zones", "translations": {}},
                        mode="allMatch",
                    ),
                },
            )
            path.write_text(module(""), encoding="utf-8")
            self.assertNotIn("classifications", validate.evaluate(path))
            path.write_text(module("classifications {}"), encoding="utf-8")
            self.assertNotIn("classifications", validate.evaluate(path))
            for broken in (
                body.replace('["use"] {\n    id = "use"', '["use"] {\n    id = "other"'),
                body.replace('`class` = "wall"', '`class` = " "'),
                body.replace('mode = "allMatch"', 'mode = "lastMatch"'),
                body.replace('property = "use"', 'property = " "'),
                body.replace(f'propertySet = "{CLASSIFICATION_SET}"\n', ""),
            ):
                self.assertNotEqual(broken, body)
                path.write_text(module(broken), encoding="utf-8")
                with self.subTest(broken=broken), self.assertRaises(SystemExit):
                    validate.evaluate(path)
            path.write_text(
                module('classifications { ["use"] { id = "use"; name { default = "Use" } } }'),
                encoding="utf-8",
            )
            with self.assertRaises(SystemExit):
                validate.evaluate(path)


def declared_class(class_id: str, parent: str | None = None, **fields) -> dict:
    declared = {"id": class_id, "name": {"default": class_id, "translations": {}}}
    if parent is not None:
        declared["parent"] = parent
    declared.update(fields)
    return declared


def cost_groups(*rows: dict, **fields) -> dict:
    """A three-level cost-group tree whose rows assign leaves and an inner class."""
    return classification(
        "cost-group",
        *(
            rows
            or (
                classification_row("kg-331"),
                classification_row("kg-330", {"kind": "all"}),
            )
        ),
        classes=[
            declared_class("kg-300", code="300"),
            declared_class("kg-330", "kg-300", code="330"),
            declared_class("kg-331", "kg-330", code="331"),
            declared_class("kg-332", "kg-330"),
        ],
        **fields,
    )


def derived_class(class_name: str, classification_id: str = "cost-group", **fields) -> dict:
    return {
        "kind": "derivedClass",
        "classification": classification_id,
        "class": class_name,
        **fields,
    }


class HierarchicalClassificationTests(unittest.TestCase):
    """Declared class trees: rows assign declared classes, levels read the
    tree, and a derived-class selector takes a class with its descendants."""

    @classmethod
    def setUpClass(cls) -> None:
        expected = validate.ROOT / "examples/minimal/expected"
        cls.definitions = json.loads((expected / "definitions.json").read_text())
        cls.ruleset = json.loads((expected / "ruleset.json").read_text())

    bind = ClassificationTests.bind
    assert_rejected = ClassificationTests.assert_rejected

    def test_accepts_a_tree_its_levels_and_derived_class_selectors(self) -> None:
        declared = {"cost-group": cost_groups(), "use": classification("use")}
        self.bind(declared)
        for applicability in (
            derived_class("kg-330", includeDescendants=True),
            derived_class("kg-332"),
            derived_class("wall", "use"),
            reads_class("cost-group;level=1", "equals", text("kg-300")),
            reads_class("cost-group;level=3"),
            {"kind": "not", "operand": derived_class("kg-300", includeDescendants=True)},
        ):
            with self.subTest(applicability=applicability):
                self.bind(declared, applicability=applicability)
        self.bind(
            declared,
            parameters={
                "property": {
                    "type": "propertyReference",
                    "propertySet": CLASSIFICATION_SET,
                    "property": "cost-group;level=2",
                }
            },
        )
        # A row of another classification may read the tree.
        self.bind(
            {
                **declared,
                "zone": classification(
                    "zone",
                    classification_row("dry", derived_class("kg-330", includeDescendants=True)),
                ),
            }
        )

    def test_rejects_malformed_trees(self) -> None:
        def with_classes(*classes: dict, rows=None) -> dict:
            tree = cost_groups()
            tree["classes"] = list(classes)
            if rows is not None:
                tree["rows"] = rows
            return {"cost-group": tree}

        root = declared_class("kg-300")
        for classifications in (
            {"cost-group": {**cost_groups(), "classes": []}},
            with_classes(root, rows=[classification_row("kg-999")]),
            with_classes(root, declared_class("kg-300"), rows=[classification_row("kg-300")]),
            with_classes(
                declared_class("a", code="1"),
                declared_class("b", code="1"),
                rows=[classification_row("a")],
            ),
            with_classes(declared_class("a", "b"), rows=[classification_row("a")]),
            with_classes(
                declared_class("a", "b"), declared_class("b", "a"),
                rows=[classification_row("a")],
            ),
            with_classes(declared_class("a", "a"), rows=[classification_row("a")]),
            with_classes(declared_class(" "), rows=[classification_row(" ")]),
            with_classes(declared_class("a", code=" "), rows=[classification_row("a")]),
            with_classes(declared_class("a", code=300), rows=[classification_row("a")]),
            with_classes(declared_class("a", level=1), rows=[classification_row("a")]),
            with_classes(
                {"id": "a", "code": "1"}, rows=[classification_row("a")]
            ),
        ):
            self.assert_rejected(classifications)

    def test_rejects_levels_and_classes_outside_the_tree(self) -> None:
        declared = {"cost-group": cost_groups(), "use": classification("use")}
        for applicability in (
            reads_class("cost-group;level=4"),
            reads_class("cost-group;level=0"),
            reads_class("cost-group;level=01"),
            reads_class("cost-group;depth=1"),
            reads_class("use;level=1"),
            reads_class("undeclared;level=1"),
            derived_class("kg-999"),
            derived_class("kg-330", "undeclared"),
            derived_class("office", "use"),
            derived_class("kg-330", includeDescendants=False),
            derived_class("kg-330", includeDescendants="yes"),
            derived_class(" "),
            {"kind": "derivedClass", "classification": "cost-group"},
            derived_class("kg-330", code="330"),
        ):
            self.assert_rejected(declared, applicability=applicability)
        # A classification's rows never select its own classes.
        self.assert_rejected(
            {"cost-group": cost_groups(classification_row("kg-331", derived_class("kg-330")))}
        )

    def test_pkl_renders_a_tree_and_keeps_flat_classifications_unchanged(self) -> None:
        rules = (validate.ROOT / "schema/RuleSets.pkl").as_uri()
        selectors = (validate.ROOT / "schema/Selectors.pkl").as_uri()

        def module(body: str) -> str:
            return (
                f'amends "{rules}"\n\n'
                f'import "{selectors}"\n\n'
                'package { id = "axioval:example.classes"; version = "0.1.0"; '
                'name { default = "Classes" } }\n'
                'definitionPackages { "axioval:example.definitions" }\n'
                'root { id = "root"; name { default = "Root" } }\n'
                f"{body}\n"
            )

        body = """classifications {
  ["cost-group"] {
    id = "cost-group"
    name { default = "cost-group" }
    rows {
      new {
        selector = new Selectors.DerivedClassSelector {
          classification = "use"
          `class` = "wall"
        }
        `class` = "kg-331"
      }
      new {
        selector = new Selectors.DerivedClassSelector {
          classification = "use"
          `class` = "wall"
          includeDescendants = true
        }
        `class` = "kg-330"
      }
    }
    classes {
      new { id = "kg-300"; code = "300"; name { default = "kg-300" } }
      new { id = "kg-330"; code = "330"; name { default = "kg-330" }; parent = "kg-300" }
      new { id = "kg-331"; name { default = "kg-331" }; parent = "kg-330" }
    }
  }
}"""
        with tempfile.TemporaryDirectory(dir=validate.ROOT / "tests") as tmp:
            path = Path(tmp) / "tree.pkl"
            path.write_text(module(body), encoding="utf-8")
            evaluated = validate.evaluate(path)
            self.assertEqual(
                evaluated["classifications"]["cost-group"],
                classification(
                    "cost-group",
                    classification_row("kg-331", derived_class("wall", "use")),
                    classification_row(
                        "kg-330", derived_class("wall", "use", includeDescendants=True)
                    ),
                    classes=[
                        declared_class("kg-300", code="300"),
                        declared_class("kg-330", "kg-300", code="330"),
                        declared_class("kg-331", "kg-330"),
                    ],
                ),
            )
            self.assertEqual(
                list(evaluated["classifications"]["cost-group"]),
                ["id", "name", "rows", "classes"],
            )
            self.assertEqual(
                list(evaluated["classifications"]["cost-group"]["classes"][1]),
                ["id", "code", "name", "parent"],
            )
            for broken in (
                body.replace('new { id = "kg-331"', 'new { id = "kg-330"'),
                body.replace('new { id = "kg-331";', 'new { id = "kg-331"; code = "330";'),
                body.replace('`class` = "wall"\n          includeDescendants', '`class` = " "\n          includeDescendants'),
                body.replace('code = "300";', 'code = " ";'),
            ):
                self.assertNotEqual(broken, body)
                path.write_text(module(broken), encoding="utf-8")
                with self.subTest(broken=broken), self.assertRaises(SystemExit):
                    validate.evaluate(path)


GROUP_SET = "axioval:group"
WALL = "axioval:example.ifc.wall"


def walls() -> dict:
    return {"kind": "entityType", "objectType": WALL, "includeSubtypes": True}


def grouping(grouping_id: str = "flats", by: dict | None = None, **fields) -> dict:
    definition = {
        "id": grouping_id,
        "name": {"default": grouping_id, "translations": {}},
        "members": walls(),
        "by": by
        or {"kind": "property", "propertySet": WALL_SET, "property": REFERENCE},
    }
    definition.update(fields)
    return definition


def compartments(**fields) -> dict:
    return {
        "kind": "compartment",
        "separators": walls(),
        "boundary": property_selector(REFERENCE, "like", text("EI*"), propertySet=WALL_SET),
        **fields,
    }


def derived_group(grouping_id: str = "flats") -> dict:
    return {"kind": "derivedGroup", "grouping": grouping_id}


class GroupingTests(unittest.TestCase):
    """Groupings derive groups from their members, by a property value, a
    classification code, or as compartments, and selectors, relationships and
    the reserved set `axioval:group` reach them."""

    @classmethod
    def setUpClass(cls) -> None:
        expected = validate.ROOT / "examples/minimal/expected"
        cls.definitions = json.loads((expected / "definitions.json").read_text())
        cls.ruleset = json.loads((expected / "ruleset.json").read_text())

    def bind(self, groupings=None, classifications=None, **rule_fields) -> None:
        ruleset = copy.deepcopy(self.ruleset)
        rule = ruleset["root"]["rules"][0]
        rule.pop("explanatoryImages", None)
        rule.pop("requirements", None)
        rule.update(copy.deepcopy(rule_fields))
        if groupings is not None:
            ruleset["groupings"] = copy.deepcopy(groupings)
        if classifications is not None:
            ruleset["classifications"] = copy.deepcopy(classifications)
        validate.bind_ruleset(ruleset, [copy.deepcopy(self.definitions)], "test")

    def assert_rejected(self, groupings=None, classifications=None, **rule_fields) -> None:
        with (
            self.subTest(groupings=groupings, classifications=classifications, rule=rule_fields),
            self.assertRaises(SystemExit),
        ):
            self.bind(groupings, classifications, **rule_fields)

    def test_accepts_groupings_of_every_kind(self) -> None:
        declared = {
            "flats": grouping(description={"default": "Flats", "translations": {}}),
            "zones": grouping("zones", {"kind": "classification", "system": "Uniclass"}),
            "uses": grouping(
                "uses",
                {"kind": "property", "propertySet": CLASSIFICATION_SET, "property": "use"},
                members={"kind": "all"},
            ),
            "by-area": grouping(
                "by-area", {"kind": "property", "propertySet": MEASURED_SET, "property": "area"}
            ),
            "unscoped": grouping("unscoped", {"kind": "property", "property": REFERENCE}),
            "fire": grouping("fire", compartments()),
            "fire-tuned": grouping(
                "fire-tuned", compartments(tolerance=0, overlap=0.5)
            ),
            "fire.2": grouping(
                "fire.2",
                compartments(
                    tolerance=0.1,
                    separators={"kind": "anyOf", "operands": [walls(), derived_class("wall", "use")]},
                ),
            ),
        }
        classifications = {"use": classification("use")}
        self.bind(declared, classifications)
        for applicability in (
            derived_group(),
            derived_group("fire"),
            {"kind": "not", "operand": derived_group("zones")},
            property_selector("key", "equals", text("1"), propertySet=GROUP_SET),
            property_selector(
                "members", "greaterThan", {"type": "integer", "value": 1}, propertySet=GROUP_SET
            ),
            related_selector(["axioval:derived.group;by=flats"]),
            related_selector(["axioval:derived.group;by=flats:backward"], selector=walls()),
            related_selector(
                ["axioval:derived.group;by=flats|axioval:derived.group;by=fire:either"]
            ),
            related_selector(
                ["axioval:derived.adjacent-across;tolerance=0.05;overlap=0.3:either"]
            ),
            related_selector(["axioval:derived.adjacent-across"]),
        ):
            with self.subTest(applicability=applicability):
                self.bind(declared, classifications, applicability=applicability)
        self.bind(
            declared,
            classifications,
            categories=[
                {"propertySet": GROUP_SET, "property": "key",
                 "path": ["axioval:derived.group;by=flats"]}
            ],
            parameters={
                "property": {
                    "type": "propertyReference",
                    "propertySet": GROUP_SET,
                    "property": "key",
                }
            },
        )

    def test_rejects_malformed_groupings(self) -> None:
        for groupings in (
            {},
            [grouping()],
            {"flats": grouping("zones")},
            {"": grouping("")},
            {" ": grouping(" ")},
            {"a b": grouping("a b")},
            *({f"a{c}b": grouping(f"a{c}b")} for c in ":;|/"),
            {"flats": {**grouping(), "weight": 1}},
            {"flats": {k: v for k, v in grouping().items() if k != "by"}},
            {"flats": {k: v for k, v in grouping().items() if k != "members"}},
            {"flats": {k: v for k, v in grouping().items() if k != "name"}},
            {"flats": grouping(members={"kind": "entityType", "objectType": "axioval:example.ifc.door", "includeSubtypes": True})},
            {"flats": grouping(members={"kind": "ruleOutcome", "rule": "wall-reference-required", "outcome": "passed"})},
            {"flats": grouping(members=derived_group("flats"))},
            {"flats": grouping(members={"kind": "not", "operand": property_selector("key", "exists", propertySet=GROUP_SET)})},
            {"flats": grouping(by={"kind": "colour"})},
            {"flats": grouping(by={"kind": "property"})},
            {"flats": grouping(by={"kind": "property", "property": "axioval:example.ifc.unknown"})},
            {"flats": grouping(by={"kind": "property", "propertySet": "axioval:example.unknown", "property": REFERENCE})},
            {"flats": grouping(by={"kind": "property", "propertySet": GROUP_SET, "property": "key"})},
            {"flats": grouping(by={"kind": "property", "propertySet": CLASSIFICATION_SET, "property": "use"})},
            {"flats": grouping(by={"kind": "property", "propertySet": MEASURED_SET, "property": "mass"})},
            {"flats": grouping(by={"kind": "property", "property": REFERENCE, "system": "x"})},
            {"flats": grouping(by={"kind": "classification", "system": " "})},
            {"flats": grouping(by={"kind": "classification", "system": 1})},
            {"flats": grouping(by={"kind": "classification"})},
            {"flats": grouping(by=compartments(tolerance=-0.1))},
            {"flats": grouping(by=compartments(tolerance=True))},
            {"flats": grouping(by=compartments(tolerance="0.1"))},
            {"flats": grouping(by=compartments(overlap=0))},
            {"flats": grouping(by=compartments(overlap=-1))},
            {"flats": grouping(by=compartments(overlap=float("inf")))},
            {"flats": grouping(by=compartments(tolerance=float("nan")))},
            {"flats": grouping(by=compartments(reach=1))},
            {"flats": grouping(by={k: v for k, v in compartments().items() if k != "boundary"})},
            {"flats": grouping(by=compartments(boundary=derived_group("flats")))},
            {"flats": grouping(by=compartments(separators={"kind": "ruleOutcome", "rule": "wall-reference-required", "outcome": "failed"}))},
        ):
            self.assert_rejected(groupings)

    def test_rejects_undeclared_groupings_and_group_facts(self) -> None:
        declared = {"flats": grouping()}
        for applicability in (
            derived_group("zones"),
            derived_group(" "),
            {"kind": "derivedGroup"},
            {"kind": "derivedGroup", "grouping": "flats", "includeDescendants": True},
            property_selector("count", "exists", propertySet=GROUP_SET),
            property_selector("Key", "exists", propertySet=GROUP_SET),
            property_selector("members", "equals", text("1"), propertySet=GROUP_SET),
            related_selector(["axioval:derived.group;by=zones"]),
            related_selector(["axioval:derived.group"]),
            related_selector(["axioval:derived.group;by="]),
            related_selector(["axioval:derived.group;by=a/b"]),
            related_selector(["axioval:derived.group;by=flats;by=flats"]),
            related_selector(["axioval:derived.group;by=flats|axioval:derived.group;by=flats"]),
        ):
            self.assert_rejected(declared, applicability=applicability)
        # Without groupings no group is declared.
        self.assert_rejected(applicability=derived_group())
        self.assert_rejected(
            declared,
            categories=[{"property": REFERENCE, "path": ["axioval:derived.group;by=zones"]}],
        )
        # Classes are derived before groups, so a row never reads one.
        for row_selector in (
            derived_group(),
            property_selector("key", "exists", propertySet=GROUP_SET),
        ):
            self.assert_rejected(
                declared, {"use": classification("use", classification_row("wall", row_selector))}
            )

    def test_pkl_renders_groupings_and_omits_them_when_empty(self) -> None:
        rules = (validate.ROOT / "schema/RuleSets.pkl").as_uri()
        selectors = (validate.ROOT / "schema/Selectors.pkl").as_uri()

        def module(body: str) -> str:
            return (
                f'amends "{rules}"\n\n'
                f'import "{selectors}"\n\n'
                'package { id = "axioval:example.groups"; version = "0.1.0"; '
                'name { default = "Groups" } }\n'
                'definitionPackages { "axioval:example.definitions" }\n'
                'root { id = "root"; name { default = "Root" } }\n'
                f"{body}\n"
            )

        body = """groupings {
  ["flats"] {
    id = "flats"
    name { default = "flats" }
    members = new Selectors.EntityTypeSelector { objectType = "axioval:example.ifc.wall" }
    by = new PropertyGroupingKey { property = "axioval:example.ifc.reference" }
  }
  ["zones"] {
    id = "zones"
    name { default = "zones" }
    description { default = "Zones" }
    members = new Selectors.DerivedGroupSelector { grouping = "flats" }
    by = new ClassificationGroupingKey { system = "Uniclass" }
  }
  ["fire"] {
    id = "fire"
    name { default = "fire" }
    members = new Selectors.AllSelector {}
    by = new CompartmentGroupingKey {
      separators = new Selectors.AllSelector {}
      boundary = new Selectors.AllSelector {}
      tolerance = 0.1
    }
  }
}"""
        with tempfile.TemporaryDirectory(dir=validate.ROOT / "tests") as tmp:
            path = Path(tmp) / "groups.pkl"
            path.write_text(module(body), encoding="utf-8")
            evaluated = validate.evaluate(path)
            name = lambda text_: {"default": text_, "translations": {}}  # noqa: E731
            self.assertEqual(
                evaluated["groupings"],
                {
                    "flats": {
                        "id": "flats",
                        "name": name("flats"),
                        "members": walls(),
                        "by": {"kind": "property", "property": REFERENCE},
                    },
                    "zones": {
                        "id": "zones",
                        "name": name("zones"),
                        "description": name("Zones"),
                        "members": derived_group("flats"),
                        "by": {"kind": "classification", "system": "Uniclass"},
                    },
                    "fire": {
                        "id": "fire",
                        "name": name("fire"),
                        "members": {"kind": "all"},
                        "by": {
                            "kind": "compartment",
                            "separators": {"kind": "all"},
                            "boundary": {"kind": "all"},
                            "tolerance": 0.1,
                        },
                    },
                },
            )
            self.assertEqual(
                list(evaluated["groupings"]["fire"]["by"]),
                ["kind", "separators", "boundary", "tolerance"],
            )
            path.write_text(module(""), encoding="utf-8")
            self.assertNotIn("groupings", validate.evaluate(path))
            for broken in (
                body.replace('["fire"] {\n    id = "fire"', '["fire"] {\n    id = "fire2"'),
                body.replace('id = "zones"', 'id = "zo nes"').replace('["zones"]', '["zo nes"]'),
                body.replace('id = "zones"', 'id = "a/b"').replace('["zones"]', '["a/b"]'),
                body.replace("tolerance = 0.1", "tolerance = -0.1"),
                body.replace("tolerance = 0.1", "overlap = 0"),
                body.replace('system = "Uniclass"', 'system = " "'),
                body.replace('grouping = "flats"', 'grouping = " "'),
                body.replace(
                    'new PropertyGroupingKey { property',
                    'new PropertyGroupingKey { propertySet = "axioval:group"; property',
                ).replace('"axioval:example.ifc.reference" }', '"key" }'),
                body.replace(
                    'new PropertyGroupingKey { property',
                    'new PropertyGroupingKey { propertySet = "axioval:example.pset"; property',
                ).replace('"axioval:example.ifc.reference" }', '"key" }'),
            ):
                self.assertNotEqual(broken, body)
                path.write_text(module(broken), encoding="utf-8")
                with self.subTest(broken=broken), self.assertRaises(SystemExit):
                    validate.evaluate(path)


MEASURED_SET = "axioval:measured"


def measured(name: str, operator: str = "lessThan", value=None, **fields) -> dict:
    if value is None and operator not in {"exists", "isEmpty", "isNotEmpty"}:
        value = {"type": "quantity", "value": 0.05, "unit": "m"}
    return property_selector(name, operator, value, propertySet=MEASURED_SET, **fields)


class MeasuredValueTests(unittest.TestCase):
    """Values measured from geometry are properties of a reserved set."""

    NAMES = (
        "extent_x",
        "extent_y",
        "extent_z",
        "bottom",
        "top",
        "area",
        "volume",
        "x",
        "y",
        "z",
        "level_height",
        "bottom_above_level;path=IfcRelContainedInSpatialStructure:backward",
        "bottom_above_level;path=IfcRelAggregates:backward+,IfcRelNests",
        "bottom_above_level;path=IfcRelFillsElement|IfcRelVoidsElement:backward+,"
        "IfcRelContainedInSpatialStructure:backward",
        "bottom_above_level;path=IfcRelAggregates|axioval:derived.intersects:either",
        "boundary_area;kind=IfcWall",
        "boundary_area;kind=IfcWall;plane=0.05",
    )

    @classmethod
    def setUpClass(cls) -> None:
        expected = validate.ROOT / "examples/minimal/expected"
        cls.definitions = json.loads((expected / "definitions.json").read_text())
        cls.ruleset = json.loads((expected / "ruleset.json").read_text())

    def bind(self, **rule_fields) -> None:
        ruleset = copy.deepcopy(self.ruleset)
        rule = ruleset["root"]["rules"][0]
        rule.pop("explanatoryImages", None)
        rule.pop("requirements", None)
        rule.update(copy.deepcopy(rule_fields))
        validate.bind_ruleset(ruleset, [copy.deepcopy(self.definitions)], "test")

    def assert_rejected(self, **rule_fields) -> None:
        with self.subTest(rule=rule_fields), self.assertRaises(SystemExit):
            self.bind(**rule_fields)

    def test_accepts_every_name_ignoring_ascii_case(self) -> None:
        from scripts.contracts import validate_selector

        for name in (
            *self.NAMES,
            "EXTENT_Z",
            "Volume",
            " top ",
            "Bottom_Above_Level; PATH = IfcRelAggregates:either+ , IfcRelNests",
            "boundary_area;plane=1e-2;Kind=IfcCovering",
            "boundary_area;kind=IfcWall;plane=0",
        ):
            with self.subTest(name=name):
                validate_selector(measured(name), "test")
                self.bind(
                    applicability=measured(name),
                    severityOverrides=[
                        {"selector": measured(name, "exists"), "severity": "info"}
                    ],
                    categories=[{"propertySet": MEASURED_SET, "property": name}],
                    parameters={
                        "property": {
                            "type": "propertyReference",
                            "propertySet": MEASURED_SET,
                            "property": name,
                        }
                    },
                )

    def test_rejects_other_names_and_non_quantity_comparisons(self) -> None:
        for name in (
            "height",
            "extent",
            "extent-z",
            "",
            "EXTENT_\u017f",
            "axioval:example.ifc.reference",
            "\u212aelvin",
            "extent_z;",
            "extent_z;path=IfcRelAggregates",
            "level_height;plane=0",
            "bottom_above_level",
            "bottom_above_level;path=",
            "bottom_above_level;path=IfcRelAggregates,,IfcRelNests",
            "bottom_above_level;path=IfcRelAggregates:up",
            "bottom_above_level;path=IfcRelAggregates|",
            "bottom_above_level;path=IfcRelAggregates|IfcRelAggregates",
            "bottom_above_level;path=IfcRelAggregates:backward|IfcRelNests",
            "bottom_above_level;path=Ifc Rel",
            "bottom_above_level;path=IfcRelAggregates;kind=IfcWall",
            "bottom_above_level;path",
            "boundary_area",
            "boundary_area;kind=",
            "boundary_area;plane=0.5",
            "boundary_area;kind=IfcWall;plane=-0.5",
            "boundary_area;kind=IfcWall;plane=inf",
            "boundary_area;kind=IfcWall;plane=NaN",
            "boundary_area;kind=IfcWall;plane=1_0",
            "boundary_area;kind=IfcWall;plane=",
            "boundary_area;kind=IfcWall;kind=IfcSlab",
            "boundary_area;kind=IfcWall;depth=1",
        ):
            self.assert_rejected(applicability=measured(name))
            self.assert_rejected(
                categories=[{"propertySet": MEASURED_SET, "property": name}]
            )
            self.assert_rejected(
                parameters={
                    "property": {
                        "type": "propertyReference",
                        "propertySet": MEASURED_SET,
                        "property": name,
                    }
                }
            )
        for selector in (
            measured("extent_z", "equals", text("tall")),
            measured("extent_z", "lessThan", {"type": "number", "value": 0.05}),
            measured("extent_z", "like", text("1*")),
            measured("extent_z", "exists", caseSensitive=False),
        ):
            self.assert_rejected(applicability=selector)

    def test_pkl_accepts_measured_names_only_in_the_reserved_set(self) -> None:
        selectors = (validate.ROOT / "schema/Selectors.pkl").as_uri()
        values = (validate.ROOT / "schema/Values.pkl").as_uri()
        with tempfile.TemporaryDirectory(dir=validate.ROOT / "tests") as tmp:
            path = Path(tmp) / "measured.pkl"

            def evaluate(property_set: str | None, name: str) -> dict:
                qualifier = (
                    f'propertySet = "{property_set}"' if property_set else ""
                )
                path.write_text(
                    f'import "{selectors}"\n'
                    f'import "{values}"\n\n'
                    "selector = new Selectors.PropertySelector {\n"
                    f"  {qualifier}\n"
                    f'  property = "{name}"\n'
                    '  operator = "lessThan"\n'
                    '  value = new Values.QuantityValue { value = 0.05; unit = "m" }\n'
                    "}\n"
                    "reference = new Values.PropertyReferenceValue {\n"
                    f"  {qualifier}\n"
                    f'  property = "{name}"\n'
                    "}\n",
                    encoding="utf-8",
                )
                return validate.evaluate(path)

            evaluated = evaluate(MEASURED_SET, "Extent_Z")
            self.assertEqual(evaluated["selector"]["property"], "Extent_Z")
            self.assertEqual(evaluated["reference"]["propertySet"], MEASURED_SET)
            name = "boundary_area;kind=IfcWall;plane=0.05"
            self.assertEqual(
                evaluate(MEASURED_SET, name)["reference"]["property"], name
            )
            for property_set, name in (
                (MEASURED_SET, "height"),
                (MEASURED_SET, "height;path=IfcRelAggregates"),
                (MEASURED_SET, "axioval:example.height"),
                (None, "extent_z"),
                ("axioval:attributes", "extent_z"),
            ):
                with self.subTest(property_set=property_set, name=name):
                    with self.assertRaises(SystemExit):
                        evaluate(property_set, name)



ATTRIBUTE_SETS = (
    "axioval:attributes",
    "axioval:type-attributes",
    "axioval:presentation",
    "axioval:material",
    "axioval:body",
)


class ReservedAttributeSetTests(unittest.TestCase):
    """The attribute sets bind to themselves; their properties are concepts."""

    @classmethod
    def setUpClass(cls) -> None:
        expected = validate.ROOT / "examples/minimal/expected"
        cls.definitions = json.loads((expected / "definitions.json").read_text())
        cls.ruleset = json.loads((expected / "ruleset.json").read_text())

    def bind(self, **rule_fields) -> None:
        ruleset = copy.deepcopy(self.ruleset)
        rule = ruleset["root"]["rules"][0]
        rule.pop("explanatoryImages", None)
        rule.pop("requirements", None)
        rule.update(copy.deepcopy(rule_fields))
        validate.bind_ruleset(ruleset, [copy.deepcopy(self.definitions)], "test")

    def assert_rejected(self, **rule_fields) -> None:
        with self.subTest(rule=rule_fields), self.assertRaises(SystemExit):
            self.bind(**rule_fields)

    @staticmethod
    def uses(property_set: str, property_id: str = REFERENCE) -> dict:
        selector = property_selector(property_id, "exists", propertySet=property_set)
        return {
            "applicability": {
                "kind": "allOf",
                "operands": [
                    selector,
                    related_selector(["IfcRelAggregates:backward"], selector),
                ],
            },
            "severityOverrides": [{"selector": selector, "severity": "info"}],
            "categories": [{"propertySet": property_set, "property": property_id}],
            "parameters": {
                "property": {
                    "type": "propertyReference",
                    "propertySet": property_set,
                    "property": property_id,
                }
            },
        }

    def test_accepts_every_attribute_set_around_a_property_concept(self) -> None:
        for property_set in ATTRIBUTE_SETS:
            uses = self.uses(property_set)
            for field, value in uses.items():
                with self.subTest(property_set=property_set, field=field):
                    self.bind(**{field: value})
            self.bind(**uses)

    def test_property_in_an_attribute_set_is_still_bound(self) -> None:
        for property_set in ATTRIBUTE_SETS:
            for property_id in ("axioval:unknown.property", "Name", ""):
                uses = self.uses(property_set, property_id)
                for field, value in uses.items():
                    self.assert_rejected(**{field: value})

    def test_other_sets_are_still_concepts(self) -> None:
        for property_set in ("axioval:unknown.set", "axioval:attribute"):
            uses = self.uses(property_set)
            for field, value in uses.items():
                self.assert_rejected(**{field: value})

    def test_property_set_patterns_are_never_bound(self) -> None:
        from scripts.contracts import validate_selector

        for property_set in ATTRIBUTE_SETS:
            with self.subTest(property_set=property_set):
                validate_selector(
                    pattern_selector("Name", propertySetPattern=property_set),
                    "test",
                    {},
                    {},
                    {},
                )

    def test_pkl_accepts_attribute_sets_around_property_concepts(self) -> None:
        selectors = (validate.ROOT / "schema/Selectors.pkl").as_uri()
        values = (validate.ROOT / "schema/Values.pkl").as_uri()
        with tempfile.TemporaryDirectory(dir=validate.ROOT / "tests") as tmp:
            path = Path(tmp) / "attributes.pkl"

            def evaluate(property_set: str, name: str) -> dict:
                path.write_text(
                    f'import "{selectors}"\n'
                    f'import "{values}"\n\n'
                    "selector = new Selectors.PropertySelector {\n"
                    f'  propertySet = "{property_set}"\n'
                    f'  property = "{name}"\n'
                    '  operator = "exists"\n'
                    "}\n"
                    "reference = new Values.PropertyReferenceValue {\n"
                    f'  propertySet = "{property_set}"\n'
                    f'  property = "{name}"\n'
                    "}\n",
                    encoding="utf-8",
                )
                return validate.evaluate(path)

            for property_set in ATTRIBUTE_SETS:
                with self.subTest(property_set=property_set):
                    evaluated = evaluate(property_set, REFERENCE)
                    self.assertEqual(
                        evaluated["selector"]["propertySet"], property_set
                    )
                    self.assertEqual(evaluated["reference"]["property"], REFERENCE)
                    with self.assertRaises(SystemExit):
                        evaluate(property_set, "Name")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def workbook(cells: str, sheet: str = "Rooms", shared: list[str] | None = None) -> bytes:
    """A minimal xlsx workbook whose sheet `sheet` holds the worksheet XML
    `cells` and whose shared strings are `shared`."""
    buffer = io.BytesIO()
    strings = "".join(f"<si><t>{item}</t></si>" for item in shared or [])
    members = {
        "xl/workbook.xml": (
            '<workbook xmlns:r="urn:r"><sheets>'
            '<sheet name="Other" sheetId="1" r:id="rId1"/>'
            f'<sheet name="{sheet}" sheetId="2" r:id="rId2"/>'
            "</sheets></workbook>"
        ),
        "xl/_rels/workbook.xml.rels": (
            "<Relationships>"
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Target="/xl/worksheets/sheet2.xml"/>'
            "</Relationships>"
        ),
        "xl/sharedStrings.xml": f"<sst>{strings}</sst>",
        "xl/worksheets/sheet1.xml": "<worksheet><sheetData/></worksheet>",
        "xl/worksheets/sheet2.xml": (
            f"<worksheet><sheetData>{cells}</sheetData></worksheet>"
        ),
    }
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return buffer.getvalue()


ROOMS_CSV = (
    "﻿type,min_area,label,count,ratio,strict,reference,inspected,stamped\r\n"
    'Office*,10,"single, office",2,0.5,true,axioval:example.office,2026-01-31,'
    "2026-01-31T08:00:00Z\r\n"
    "\r\n"
    ",,,,,,,,\r\n"
    '"Lab ""A""",12.5e0,,,,false,,,\n'
    "*,6,,,,,,,"
).encode()


def file_columns(*extra: dict) -> list[dict]:
    return [
        {"id": "space_type", "header": "type", "kind": "textPattern"},
        {"id": "minimum_area", "header": "min_area", "kind": "quantity", "unit": "m2"},
        *extra,
    ]


ROOMS_COLUMNS = file_columns(
    {"id": "label", "kind": "string"},
    {"id": "count", "kind": "integer"},
    {"id": "ratio", "kind": "number"},
    {"id": "strict", "kind": "boolean"},
    {"id": "reference", "kind": "reference"},
    {"id": "inspected", "kind": "date"},
    {"id": "stamped", "kind": "dateTime"},
)


def table_file(path: str, data: bytes, columns: list | None = None, **fields) -> dict:
    value = {
        "type": "tableFile",
        "path": path,
        "sha256": sha256(data),
        "columns": copy.deepcopy(ROOMS_COLUMNS if columns is None else columns),
    }
    value.update(fields)
    return value


class TableFileTests(unittest.TestCase):
    """A table's rows may come from a CSV file or a workbook sheet in the
    package, pinned by its SHA-256 and bound exactly as inline rows."""

    documents = TableParameterTests.documents

    @classmethod
    def setUpClass(cls) -> None:
        expected = validate.ROOT / "examples/minimal/expected"
        cls.definitions = json.loads((expected / "definitions.json").read_text())
        cls.ruleset = json.loads((expected / "ruleset.json").read_text())

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def write(self, path: str, data: bytes) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def bind_file(self, value: dict, root: Path | None = None, **overrides) -> None:
        ruleset, definitions = self.documents(**overrides)
        ruleset["root"]["rules"][0]["parameters"]["limits"] = value
        validate.bind_ruleset(
            ruleset, [definitions], "test", asset_root=self.root if root is None else root
        )

    def assert_file_rejected(self, value: dict, data: bytes | None = None) -> None:
        with self.subTest(value=value, data=data), self.assertRaises(SystemExit):
            if data is not None:
                self.write(value["path"], data)
            self.bind_file(value)

    def test_accepts_csv_rows_of_every_column_kind(self) -> None:
        self.write("tables/rooms.csv", ROOMS_CSV)
        self.bind_file(table_file("tables/rooms.csv", ROOMS_CSV))
        from scripts.contracts import table_file_rows

        rows = table_file_rows(ROOMS_CSV, "tables/rooms.csv", None, ROOMS_COLUMNS)
        self.assertEqual(
            rows[0],
            {
                "space_type": text("Office*"),
                "minimum_area": {"type": "quantity", "value": 10.0, "unit": "m2"},
                "label": text("single, office"),
                "count": {"type": "integer", "value": 2},
                "ratio": {"type": "number", "value": 0.5},
                "strict": {"type": "boolean", "value": True},
                "reference": {"type": "reference", "value": "axioval:example.office"},
                "inspected": {"type": "date", "value": "2026-01-31"},
                "stamped": {"type": "dateTime", "value": "2026-01-31T08:00:00Z"},
            },
        )
        self.assertEqual(
            rows[1],
            {
                "space_type": text('Lab "A"'),
                "minimum_area": {"type": "quantity", "value": 12.5, "unit": "m2"},
                "strict": {"type": "boolean", "value": False},
            },
        )
        self.assertEqual(len(rows), 3)
        # Only the declared columns are needed, in any order of the file.
        data = b"min_area,type\n7,Kitchen\n"
        self.write("kitchen.csv", data)
        self.bind_file(table_file("kitchen.csv", data, file_columns()))

    def test_accepts_a_workbook_sheet_by_value(self) -> None:
        data = workbook(
            '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="inlineStr">'
            "<is><t>min_area</t></is></c><c r=\"C1\" t=\"s\"><v>1</v></c></row>"
            '<row r="3"><c r="A3" t="str"><v>Office*</v></c><c r="B3"><v>10.5</v></c>'
            '<c r="C3" t="b"><v>1</v></c></row>',
            shared=["type", "strict"],
        )
        columns = file_columns({"id": "strict", "kind": "boolean"})
        self.write("rooms.xlsx", data)
        self.bind_file(table_file("rooms.xlsx", data, columns, sheet="Rooms"))
        from scripts.contracts import table_file_rows

        self.assertEqual(
            table_file_rows(data, "rooms.xlsx", "Rooms", columns),
            [
                {
                    "space_type": text("Office*"),
                    "minimum_area": {"type": "quantity", "value": 10.5, "unit": "m2"},
                    "strict": {"type": "boolean", "value": True},
                }
            ],
        )
        for broken in (
            '<row r="1"><c r="A1"><f>1+1</f><v>2</v></c></row>',
            '<row r="1"><c r="A1" t="e"><v>#DIV/0!</v></c></row>',
            '<row r="1"><c r="A1" t="s"><v>9</v></c></row>',
            '<row r="1"><c r="A1" t="b"><v>2</v></c></row>',
            '<row r="x"><c r="A1"><v>1</v></c></row>',
            '<row r="1"><c r="11"><v>1</v></c></row>',
            '<row r="1"><c r="A1" t="z"><v>1</v></c></row>',
        ):
            data = workbook(broken)
            self.assert_file_rejected(
                table_file("broken.xlsx", data, columns, sheet="Rooms"), data
            )
        data = workbook('<row r="1"><c r="A1"><v>1</v></c></row>')
        self.assert_file_rejected(
            table_file("unnamed.xlsx", data, columns, sheet="Missing"), data
        )
        data = workbook('<?pi x?><row r="1"><c r="A1"><v>1</v></c></row>')
        self.assert_file_rejected(table_file("pi.xlsx", data, columns, sheet="Rooms"), data)
        data = b"not a workbook"
        self.assert_file_rejected(table_file("zip.xlsx", data, columns, sheet="Rooms"), data)

    def test_accepts_a_default_table_from_a_file(self) -> None:
        data = b"type,min_area\n*,6\n"
        self.write("defaults.csv", data)
        ruleset, definitions = self.documents()
        parameter = definitions["definitions"]["axioval:example.property-exists"][
            "parameters"
        ]["limits"]
        parameter["required"] = False
        parameter["defaultValue"] = table_file("defaults.csv", data, file_columns())
        del ruleset["root"]["rules"][0]["parameters"]["limits"]
        validate.bind_ruleset(ruleset, [definitions], "test", asset_root=self.root)
        validate.validate_definition_document(definitions, "test", asset_root=self.root)
        with self.assertRaises(SystemExit):
            validate.validate_definition_document(definitions, "test")
        parameter["defaultValue"]["sha256"] = "0" * 64
        with self.assertRaises(SystemExit):
            validate.validate_definition_document(
                definitions, "test", asset_root=self.root
            )

    def test_rejects_malformed_references(self) -> None:
        data = b"type,min_area\n*,6\n"
        self.write("rooms.csv", data)
        self.write("rooms.xlsx", data)
        good = table_file("rooms.csv", data, file_columns())
        self.bind_file(good)
        # Without the package root a table file cannot be bound.
        with self.assertRaises(SystemExit):
            validate.bind_ruleset(*self.with_value(good), "test")
        for changes in (
            {"path": "../rooms.csv"},
            {"path": "/rooms.csv"},
            {"path": "./rooms.csv"},
            {"path": "a//rooms.csv"},
            {"path": "a\\rooms.csv"},
            {"path": "c:rooms.csv"},
            {"path": "rooms.txt"},
            {"path": "missing.csv"},
            {"path": 1},
            {"sheet": "Rooms"},
            {"path": "rooms.xlsx"},
            {"sheet": ""},
            {"sha256": "0" * 64},
            {"sha256": sha256(data).upper()},
            {"sha256": None},
            {"rows": []},
            {"columns": []},
            {"columns": file_columns({"id": "label", "kind": "selector"})},
            {"columns": file_columns({"id": "label", "kind": "string", "unit": "m"})},
            {"columns": file_columns({"id": "label", "kind": "colour"})},
            {"columns": file_columns({"id": "label", "kind": "string", "header": ""})},
            {"columns": file_columns({"id": "label", "kind": "string", "header": "type"})},
            {"columns": file_columns({"id": "space_type", "kind": "string"})},
            {"columns": file_columns({"id": "label", "kind": "string", "width": 1})},
            {"columns": [file_columns()[0], {**file_columns()[1], "unit": " "}]},
            {"columns": [file_columns()[0], {k: v for k, v in file_columns()[1].items() if k != "unit"}]},
            # Columns the table does not have, of another kind, or missing.
            {"columns": file_columns({"id": "colour", "kind": "string"})},
            {"columns": file_columns({"id": "count", "kind": "number"})},
            {"columns": [file_columns()[0]]},
        ):
            value = {**good, **changes}
            value = {k: v for k, v in value.items() if v is not None}
            with self.subTest(changes=changes), self.assertRaises(SystemExit):
                self.bind_file(value)
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        (Path(outside.name) / "escape.csv").write_bytes(data)
        (self.root / "escape.csv").symlink_to(Path(outside.name) / "escape.csv")
        self.assert_file_rejected({**good, "path": "escape.csv"})
        with patch("scripts.contracts.TABLE_FILE_LIMIT_BYTES", 4):
            self.assert_file_rejected(good)

    def with_value(self, value: dict) -> tuple[dict, list]:
        ruleset, definitions = self.documents()
        ruleset["root"]["rules"][0]["parameters"]["limits"] = value
        return ruleset, [definitions]

    def test_rejects_headers_and_cells_the_engine_rejects(self) -> None:
        columns = file_columns(
            {"id": "count", "kind": "integer"},
            {"id": "strict", "kind": "boolean"},
            {"id": "inspected", "kind": "date"},
        )
        header = b"type,min_area,count,strict,inspected\n"
        self.write("ok.csv", header + b"*,6,1,true,2026-01-31\n")
        self.bind_file(table_file("ok.csv", header + b"*,6,1,true,2026-01-31\n", columns))
        for data in (
            b"",
            b"\n\n",
            b"type,min_area,count,strict\n*,6,1,true\n",
            b"type,min_area,count,strict,inspected,extra\n*,6,1,true,2026-01-31,x\n",
            b"type,type,count,strict,inspected\n*,6,1,true,2026-01-31\n",
            header + b"*,6,1,true\n",
            header + b"*,6,1,true,2026-01-31,x\n",
            header + b"*,six,1,true,2026-01-31\n",
            header + b"*,1_0,1,true,2026-01-31\n",
            header + b"*, 6,1,true,2026-01-31\n",
            header + b"*,inf,1,true,2026-01-31\n",
            header + b"*,1e400,1,true,2026-01-31\n",
            header + b"*,6,1.0,true,2026-01-31\n",
            header + b"*,6,9223372036854775808,true,2026-01-31\n",
            header + b"*,6,1,yes,2026-01-31\n",
            header + b"*,6,1,True,2026-01-31\n",
            header + b"*,6,1,true,2026-02-30\n",
            header + b",6,1,true,2026-01-31\n",
            header + b"Office\\,6,1,true,2026-01-31\n",
            header + b'*,6,1,true,"2026-01-31\n',
            header + b'*,6,1,true,2026"-01-31\n',
            header + b'*,6,1,true,"2026-01-31"x\n',
            header + b"*,6,1,true,\xff\n",
        ):
            self.assert_file_rejected(table_file("bad.csv", data, columns), data)

    def test_pkl_renders_a_table_file_and_rejects_malformed_ones(self) -> None:
        values = (validate.ROOT / "schema/Values.pkl").as_uri()
        digest = "0" * 64

        def module(body: str) -> str:
            return f'import "{values}"\n\nvalue = new Values.TableFileValue {{\n{body}\n}}\n'

        body = f"""  path = "tables/rooms.xlsx"
  sheet = "Rooms"
  sha256 = "{digest}"
  columns {{
    new {{ id = "space_type"; header = "type"; kind = "textPattern" }}
    new {{ id = "minimum_area"; kind = "quantity"; unit = "m2" }}
  }}"""
        with tempfile.TemporaryDirectory(dir=validate.ROOT / "tests") as tmp:
            path = Path(tmp) / "table-file.pkl"
            path.write_text(module(body), encoding="utf-8")
            self.assertEqual(
                validate.evaluate(path)["value"],
                {
                    "type": "tableFile",
                    "path": "tables/rooms.xlsx",
                    "sheet": "Rooms",
                    "sha256": digest,
                    "columns": [
                        {"id": "space_type", "header": "type", "kind": "textPattern"},
                        {"id": "minimum_area", "kind": "quantity", "unit": "m2"},
                    ],
                },
            )
            for broken in (
                body.replace('rooms.xlsx"', 'rooms.csv"'),
                body.replace('  sheet = "Rooms"\n', ""),
                body.replace('sheet = "Rooms"', 'sheet = ""'),
                body.replace("tables/", "../"),
                body.replace("tables/", "/"),
                body.replace("tables/", "a\\\\"),
                body.replace("rooms.xlsx", "rooms.txt"),
                body.replace(digest, digest.replace("0", "A")),
                body.replace('unit = "m2"', 'unit = " "'),
                body.replace('; unit = "m2"', ""),
                body.replace('kind = "textPattern"', 'kind = "selector"'),
                body.replace('kind = "textPattern"', 'kind = "textPattern"; unit = "m"'),
                body.replace('header = "type"', 'header = ""'),
                body.replace('header = "type"', 'header = "minimum_area"'),
                body.replace('id = "minimum_area"', 'id = "space_type"; header = "x"'),
            ):
                with self.subTest(broken=broken), self.assertRaises(SystemExit):
                    path.write_text(module(broken), encoding="utf-8")
                    validate.evaluate(path)


def relation(relation_id: str = "serves", by: dict | None = None, **fields) -> dict:
    definition = {
        "id": relation_id,
        "name": {"default": relation_id, "translations": {}},
        "from": walls(),
        "to": {"kind": "all"},
        "by": by
        or {
            "kind": "property",
            "from": {"propertySet": WALL_SET, "property": REFERENCE},
            "to": {"property": REFERENCE},
        },
    }
    definition.update(fields)
    return definition


def pair_rows(*pairs: tuple) -> dict:
    return {
        "type": "table",
        "value": [{"from": text(left), "to": text(right)} for left, right in pairs],
    }


class RelationTests(unittest.TestCase):
    """Relations a ruleset declares between objects, by listed pairs or equal
    property values, which every relationship path may walk."""

    @classmethod
    def setUpClass(cls) -> None:
        expected = validate.ROOT / "examples/minimal/expected"
        cls.definitions = json.loads((expected / "definitions.json").read_text())
        cls.ruleset = json.loads((expected / "ruleset.json").read_text())

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.pairs = b"pump,room\nifc-step:a.ifc/#1,ifc-step:a.ifc/#2\n"
        (self.root / "serves.csv").write_bytes(self.pairs)

    def pairs_file(self, **fields) -> dict:
        value = {
            "type": "tableFile",
            "path": "serves.csv",
            "sha256": sha256(self.pairs),
            "columns": [
                {"id": "from", "header": "pump", "kind": "string"},
                {"id": "to", "header": "room", "kind": "string"},
            ],
        }
        value.update(fields)
        return value

    def bind(self, relations=None, groupings=None, classifications=None, **rule_fields) -> None:
        ruleset = copy.deepcopy(self.ruleset)
        rule = ruleset["root"]["rules"][0]
        rule.pop("explanatoryImages", None)
        rule.pop("requirements", None)
        rule.update(copy.deepcopy(rule_fields))
        for key, declared in (
            ("relations", relations),
            ("groupings", groupings),
            ("classifications", classifications),
        ):
            if declared is not None:
                ruleset[key] = copy.deepcopy(declared)
        validate.bind_ruleset(
            ruleset, [copy.deepcopy(self.definitions)], "test", asset_root=self.root
        )

    def assert_rejected(self, relations=None, groupings=None, classifications=None, **rule_fields) -> None:
        with (
            self.subTest(relations=relations, rule=rule_fields),
            self.assertRaises(SystemExit),
        ):
            self.bind(relations, groupings, classifications, **rule_fields)

    def test_accepts_relations_by_property_and_by_listed_pairs(self) -> None:
        declared = {
            "serves": relation(description={"default": "Serves", "translations": {}}),
            "listed": relation(
                "listed",
                {"kind": "pairs", "pairs": pair_rows(("a", "b"), ("a", "c"))},
            ),
            "filed": relation(
                "filed",
                {"kind": "pairs", "pairs": self.pairs_file(), "scheme": "ifc-globalid"},
                to=derived_group("flats"),
            ),
            "empty": relation("empty", {"kind": "pairs", "pairs": pair_rows()}),
            "supplied": relation("supplied", {"kind": "supplied"}),
            "supplied-by-scheme": relation(
                "supplied-by-scheme",
                {
                    "kind": "supplied",
                    "columns": [
                        {"id": "to", "header": "room", "kind": "string"},
                        {"id": "from", "kind": "string"},
                    ],
                    "scheme": "ifc-globalid",
                },
            ),
            "by-class": relation(
                "by-class",
                {
                    "kind": "property",
                    "from": {"propertySet": CLASSIFICATION_SET, "property": "use"},
                    "to": {"propertySet": GROUP_SET, "property": "key"},
                },
                **{"from": derived_class("wall", "use")},
            ),
        }
        groupings = {"flats": grouping()}
        classifications = {"use": classification("use")}
        self.bind(declared, groupings, classifications)
        for applicability in (
            related_selector(["axioval:derived.relation;id=serves"]),
            related_selector(["axioval:derived.relation;id=serves:backward+"]),
            related_selector(
                ["axioval:derived.relation;id=listed|axioval:derived.relation;id=filed:either"]
            ),
            related_selector(["axioval:derived.relation;id=supplied-by-scheme:backward"]),
            related_selector(["axioval:derived.relation;id=by-class"], selector=walls()),
        ):
            with self.subTest(applicability=applicability):
                self.bind(declared, groupings, classifications, applicability=applicability)
        self.bind(
            declared,
            groupings,
            classifications,
            categories=[
                {"property": REFERENCE, "path": ["axioval:derived.relation;id=serves"]}
            ],
        )
        # A grouping's members may walk a declared relation.
        self.bind(
            declared,
            {"flats": grouping(members=related_selector(["axioval:derived.relation;id=serves"]))},
            classifications,
        )

    def test_rejects_malformed_relations(self) -> None:
        for relations in (
            {},
            [relation()],
            {"serves": relation("listed")},
            {"": relation("")},
            {"a b": relation("a b")},
            *({f"a{c}b": relation(f"a{c}b")} for c in ":;|/"),
            {"serves": {**relation(), "weight": 1}},
            *(
                {"serves": {k: v for k, v in relation().items() if k != key}}
                for key in ("id", "name", "from", "to", "by")
            ),
            {"serves": relation(**{"from": {"kind": "entityType", "objectType": "axioval:example.ifc.door", "includeSubtypes": True}})},
            {"serves": relation(to={"kind": "ruleOutcome", "rule": "wall-reference-required", "outcome": "passed"})},
            {"serves": relation(to={"kind": "not", "operand": related_selector(["axioval:derived.relation;id=serves"])})},
            {"serves": relation(**{"from": related_selector(["IfcRelAggregates|axioval:derived.relation;id=serves"])})},
            {"serves": relation(by={"kind": "colour"})},
            {"serves": relation(by={"kind": "property", "from": {"property": REFERENCE}})},
            {"serves": relation(by={"kind": "property", "from": {"property": REFERENCE}, "to": {"property": "axioval:example.ifc.unknown"}})},
            {"serves": relation(by={"kind": "property", "from": {"property": REFERENCE}, "to": {"propertySet": "axioval:example.unknown", "property": REFERENCE}})},
            {"serves": relation(by={"kind": "property", "from": {"property": REFERENCE}, "to": {"propertySet": CLASSIFICATION_SET, "property": "use"}})},
            {"serves": relation(by={"kind": "property", "from": {"property": REFERENCE, "scheme": "x"}, "to": {"property": REFERENCE}})},
            {"serves": relation(by={"kind": "property", "from": {"property": REFERENCE}, "to": {"property": REFERENCE}, "pairs": pair_rows()})},
            {"serves": relation(by={"kind": "pairs"})},
            {"serves": relation(by={"kind": "pairs", "pairs": pair_rows(), "scheme": " "})},
            {"serves": relation(by={"kind": "pairs", "pairs": pair_rows(), "scheme": 1})},
            {"serves": relation(by={"kind": "pairs", "pairs": text("a")})},
            {"serves": relation(by={"kind": "pairs", "pairs": {**pair_rows(), "extra": 1}})},
            {"serves": relation(by={"kind": "pairs", "pairs": pair_rows(("a", " "))})},
            {"serves": relation(by={"kind": "pairs", "pairs": pair_rows(("", "b"))})},
            {"serves": relation(by={"kind": "pairs", "pairs": {"type": "table", "value": [{"from": text("a")}]}})},
            {"serves": relation(by={"kind": "pairs", "pairs": {"type": "table", "value": [{"from": text("a"), "to": text("b"), "via": text("c")}]}})},
            {"serves": relation(by={"kind": "pairs", "pairs": {"type": "table", "value": [{"from": text("a"), "to": {"type": "reference", "value": "axioval:x"}}]}})},
            {"serves": relation(by={"kind": "pairs", "pairs": self.pairs_file(sha256="0" * 64)})},
            {"serves": relation(by={"kind": "pairs", "pairs": self.pairs_file(columns=[{"id": "from", "header": "pump", "kind": "string"}])})},
            {"serves": relation(by={"kind": "pairs", "pairs": self.pairs_file(columns=[{"id": "from", "header": "pump", "kind": "string"}, {"id": "to", "header": "room", "kind": "textPattern"}])})},
            {"serves": relation(by={"kind": "pairs", "pairs": self.pairs_file(columns=[{"id": "from", "header": "pump", "kind": "string"}, {"id": "into", "header": "room", "kind": "string"}])})},
            # Supplied pairs: never listed, at most a `from` and `to` column each.
            {"serves": relation(by={"kind": "supplied", "pairs": pair_rows()})},
            {"serves": relation(by={"kind": "supplied", "pairs": self.pairs_file()})},
            {"serves": relation(by={"kind": "supplied", "from": {"property": REFERENCE}})},
            {"serves": relation(by={"kind": "supplied", "scheme": " "})},
            {"serves": relation(by={"kind": "supplied", "scheme": 1})},
            {"serves": relation(by={"kind": "supplied", "columns": None})},
            {"serves": relation(by={"kind": "supplied", "columns": {"from": "pump"}})},
            {"serves": relation(by={"kind": "supplied", "columns": []})},
            {"serves": relation(by={"kind": "supplied", "columns": [{"id": "from", "kind": "string"}]})},
            {"serves": relation(by={"kind": "supplied", "columns": [{"id": "from", "kind": "string"}, {"id": "to", "kind": "string"}, {"id": "via", "kind": "string"}]})},
            {"serves": relation(by={"kind": "supplied", "columns": [{"id": "from", "kind": "string"}, {"id": "from", "header": "pump", "kind": "string"}]})},
            {"serves": relation(by={"kind": "supplied", "columns": [{"id": "from", "kind": "string"}, {"id": "into", "kind": "string"}]})},
            {"serves": relation(by={"kind": "supplied", "columns": [{"id": "from", "kind": "string"}, {"id": "to", "kind": "reference"}]})},
            {"serves": relation(by={"kind": "supplied", "columns": [{"id": "from", "kind": "string"}, {"id": "to", "kind": "quantity", "unit": "m"}]})},
            {"serves": relation(by={"kind": "supplied", "columns": [{"id": "from", "kind": "string"}, {"id": "to", "kind": "string", "unit": "m"}]})},
            {"serves": relation(by={"kind": "supplied", "columns": [{"id": "from", "kind": "string"}, {"id": "to", "header": "from", "kind": "string"}]})},
            {"serves": relation(by={"kind": "supplied", "columns": [{"id": "from", "kind": "string"}, {"id": "to", "header": "", "kind": "string"}]})},
            {"serves": relation(by={"kind": "supplied", "columns": [{"id": "from", "kind": "string"}, {"id": "to", "header": 1, "kind": "string"}]})},
            {"serves": relation(by={"kind": "supplied", "columns": [{"id": "from", "kind": "string"}, {"id": "to", "kind": "string", "required": True}]})},
            {"serves": relation(by={"kind": "supplied", "columns": [{"id": "from", "kind": "string"}, "to"]})},
        ):
            self.assert_rejected(relations)
        blank = b"pump,room\na, \n"
        (self.root / "blank.csv").write_bytes(blank)
        self.assert_rejected(
            {"serves": relation(by={"kind": "pairs", "pairs": self.pairs_file(path="blank.csv", sha256=sha256(blank))})}
        )
        with self.assertRaises(SystemExit):
            ruleset = copy.deepcopy(self.ruleset)
            ruleset["root"]["rules"][0].pop("explanatoryImages", None)
            ruleset["relations"] = {
                "serves": relation(by={"kind": "pairs", "pairs": self.pairs_file()})
            }
            validate.bind_ruleset(ruleset, [copy.deepcopy(self.definitions)], "test")

    def test_rejects_undeclared_relations_in_paths(self) -> None:
        declared = {"serves": relation()}
        for applicability in (
            related_selector(["axioval:derived.relation;id=feeds"]),
            related_selector(["axioval:derived.relation;id=1"]),
            related_selector(["axioval:derived.relation"]),
            related_selector(["axioval:derived.relation;id="]),
            related_selector(["axioval:derived.relation;id=a/b"]),
            related_selector(["axioval:derived.relation;id=serves;id=serves"]),
            related_selector(
                ["axioval:derived.relation;id=serves|axioval:derived.relation;id=serves"]
            ),
            related_selector(["IfcRelAggregates|axioval:derived.relation;id=feeds:backward+"]),
        ):
            self.assert_rejected(declared, applicability=applicability)
        # Without relations none is declared.
        self.assert_rejected(
            applicability=related_selector(["axioval:derived.relation;id=serves"])
        )
        self.assert_rejected(
            declared,
            categories=[{"property": REFERENCE, "path": ["axioval:derived.relation;id=feeds"]}],
        )
        self.assert_rejected(
            declared,
            {"flats": grouping(members=related_selector(["axioval:derived.relation;id=feeds"]))},
        )

    def test_pkl_renders_relations_and_omits_them_when_empty(self) -> None:
        rules = (validate.ROOT / "schema/RuleSets.pkl").as_uri()
        selectors = (validate.ROOT / "schema/Selectors.pkl").as_uri()
        values = (validate.ROOT / "schema/Values.pkl").as_uri()

        def module(body: str) -> str:
            return (
                f'amends "{rules}"\n\n'
                f'import "{selectors}"\n'
                f'import "{values}"\n\n'
                'package { id = "axioval:example.relations"; version = "0.1.0"; '
                'name { default = "Relations" } }\n'
                'definitionPackages { "axioval:example.definitions" }\n'
                'root { id = "root"; name { default = "Root" } }\n'
                f"{body}\n"
            )

        digest = sha256(self.pairs)
        body = f"""relations {{
  ["serves"] {{
    id = "serves"
    name {{ default = "serves" }}
    from = new Selectors.EntityTypeSelector {{ objectType = "axioval:example.ifc.wall" }}
    to = new Selectors.AllSelector {{}}
    by = new PairsRelationKey {{
      scheme = "ifc-globalid"
      pairs = new Values.TableFileValue {{
        path = "serves.csv"
        sha256 = "{digest}"
        columns {{
          new {{ id = "from"; header = "pump"; kind = "string" }}
          new {{ id = "to"; header = "room"; kind = "string" }}
        }}
      }}
    }}
  }}
  ["zone"] {{
    id = "zone"
    name {{ default = "zone" }}
    description {{ default = "Zone" }}
    from = new Selectors.AllSelector {{}}
    to = new Selectors.AllSelector {{}}
    by = new PropertyRelationKey {{
      from {{ propertySet = "axioval:example.ifc.pset-wall-common"; property = "axioval:example.ifc.reference" }}
      to {{ property = "axioval:example.ifc.reference" }}
    }}
  }}
  ["listed"] {{
    id = "listed"
    name {{ default = "listed" }}
    from = new Selectors.AllSelector {{}}
    to = new Selectors.AllSelector {{}}
    by = new PairsRelationKey {{
      pairs = new Values.TableValue {{
        value {{
          new {{
            ["from"] = new Values.StringValue {{ value = "a" }}
            ["to"] = new Values.StringValue {{ value = "b" }}
          }}
        }}
      }}
    }}
  }}
}}"""
        with tempfile.TemporaryDirectory(dir=validate.ROOT / "tests") as tmp:
            path = Path(tmp) / "relations.pkl"
            path.write_text(module(body), encoding="utf-8")
            evaluated = validate.evaluate(path)
            name = lambda text_: {"default": text_, "translations": {}}  # noqa: E731
            self.assertEqual(
                evaluated["relations"],
                {
                    "serves": {
                        "id": "serves",
                        "name": name("serves"),
                        "from": walls(),
                        "to": {"kind": "all"},
                        "by": {
                            "kind": "pairs",
                            "pairs": self.pairs_file(),
                            "scheme": "ifc-globalid",
                        },
                    },
                    "zone": {
                        "id": "zone",
                        "name": name("zone"),
                        "description": name("Zone"),
                        "from": {"kind": "all"},
                        "to": {"kind": "all"},
                        "by": {
                            "kind": "property",
                            "from": {"propertySet": WALL_SET, "property": REFERENCE},
                            "to": {"property": REFERENCE},
                        },
                    },
                    "listed": {
                        "id": "listed",
                        "name": name("listed"),
                        "from": {"kind": "all"},
                        "to": {"kind": "all"},
                        "by": {"kind": "pairs", "pairs": pair_rows(("a", "b"))},
                    },
                },
            )
            self.assertEqual(
                list(evaluated["relations"]["serves"]),
                ["id", "name", "from", "to", "by"],
            )
            (Path(tmp) / "serves.csv").write_bytes(self.pairs)
            validate.bind_ruleset(
                evaluated, [copy.deepcopy(self.definitions)], "test", asset_root=Path(tmp)
            )
            path.write_text(module(""), encoding="utf-8")
            self.assertNotIn("relations", validate.evaluate(path))
            for broken in (
                body.replace('["zone"] {\n    id = "zone"', '["zone"] {\n    id = "zone2"'),
                body.replace('id = "zone"', 'id = "zo ne"').replace('["zone"]', '["zo ne"]'),
                body.replace('id = "zone"', 'id = "a;b"').replace('["zone"]', '["a;b"]'),
                body.replace('scheme = "ifc-globalid"', 'scheme = " "'),
                body.replace("new Values.TableValue", "new Values.StringValue"),
                body.replace('to { property = "axioval:example.ifc.reference" }', "to {}"),
            ):
                with self.subTest(broken=broken), self.assertRaises(SystemExit):
                    path.write_text(module(broken), encoding="utf-8")
                    validate.evaluate(path)

    def test_pkl_renders_supplied_relations(self) -> None:
        rules = (validate.ROOT / "schema/RuleSets.pkl").as_uri()
        selectors = (validate.ROOT / "schema/Selectors.pkl").as_uri()

        def module(by: str) -> str:
            return (
                f'amends "{rules}"\n\n'
                f'import "{selectors}"\n\n'
                'package { id = "axioval:example.relations"; version = "0.1.0"; '
                'name { default = "Relations" } }\n'
                'definitionPackages { "axioval:example.definitions" }\n'
                'root { id = "root"; name { default = "Root" } }\n'
                "relations {\n"
                '  ["serves"] {\n'
                '    id = "serves"\n'
                '    name { default = "serves" }\n'
                "    from = new Selectors.AllSelector {}\n"
                "    to = new Selectors.AllSelector {}\n"
                f"    by = new SuppliedRelationKey {{{by}}}\n"
                "  }\n"
                "}\n"
            )

        full = (
            '\n      scheme = "ifc-globalid"\n'
            "      columns {\n"
            '        new { id = "from"; header = "pump"; kind = "string" }\n'
            '        new { id = "to"; kind = "string" }\n'
            "      }\n    "
        )
        with tempfile.TemporaryDirectory(dir=validate.ROOT / "tests") as tmp:
            path = Path(tmp) / "supplied.pkl"
            for by, expected in (
                ("", {"kind": "supplied"}),
                (
                    full,
                    {
                        "kind": "supplied",
                        "columns": [
                            {"id": "from", "header": "pump", "kind": "string"},
                            {"id": "to", "kind": "string"},
                        ],
                        "scheme": "ifc-globalid",
                    },
                ),
            ):
                with self.subTest(by=by):
                    path.write_text(module(by), encoding="utf-8")
                    evaluated = validate.evaluate(path)
                    rendered = evaluated["relations"]["serves"]["by"]
                    self.assertEqual(rendered, expected)
                    self.assertEqual(list(rendered), list(expected))
                    validate.bind_ruleset(
                        evaluated, [copy.deepcopy(self.definitions)], "test"
                    )
            for broken in (
                full.replace('scheme = "ifc-globalid"', 'scheme = " "'),
                full.replace('new { id = "to"; kind = "string" }\n', ""),
                full.replace(
                    'new { id = "to"; kind = "string" }',
                    'new { id = "to"; kind = "string" }\n'
                    '        new { id = "via"; kind = "string" }',
                ),
                full.replace('id = "to"', 'id = "into"'),
                full.replace('id = "to"', 'id = "from"'),
                full.replace('id = "to"; kind = "string"', 'id = "to"; kind = "reference"'),
                full.replace('id = "to"; kind = "string"', 'id = "to"; header = "pump"; kind = "string"'),
                full.replace('id = "to"; kind = "string"', 'id = "to"; header = ""; kind = "string"'),
                full.replace('id = "to"; kind = "string"', 'id = "to"; kind = "quantity"; unit = "m"'),
                "\n      pairs = 1\n    ",
            ):
                with self.subTest(broken=broken), self.assertRaises(SystemExit):
                    path.write_text(module(broken), encoding="utf-8")
                    validate.evaluate(path)


if __name__ == "__main__":
    unittest.main()
