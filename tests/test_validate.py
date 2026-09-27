from __future__ import annotations

import copy
import json
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
