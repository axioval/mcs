from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts import contracts, mcs_archive, validate

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/expression"
EXAMPLE = ROOT / "examples/expressions"
# The rules the outcome-reading fixtures name.
OUTCOME_RULES = ("escape-route", "fire-resistance", "ramp-slope")


def fixtures() -> dict[str, bytes]:
    return {path.stem: path.read_bytes() for path in sorted(FIXTURES.glob("*.json"))}


def offline_root(directory: Path) -> Path:
    """A repository root holding the schema, the shared fixtures and a Pkl
    project without remote dependencies, so packing needs no network."""
    root = directory / "repository"
    (root / "schema").mkdir(parents=True)
    for module in (ROOT / "schema").glob("*.pkl"):
        shutil.copy(module, root / "schema" / module.name)
    shutil.copy(ROOT / "schema/registry-manifest.schema.json", root / "schema")
    shutil.copy(ROOT / ".pkl-version", root)
    shutil.copy(ROOT / "LICENSE", root)
    (root / "PklProject").write_text('amends "pkl:Project"\n')
    shutil.copytree(FIXTURES, root / "tests/fixtures/expression")
    return root


def manifest(package_id: str, description: str) -> str:
    return json.dumps(
        {
            "$schema": "../schema/registry-manifest.schema.json",
            "manifestVersion": "0.1.0",
            "kind": "ruleset",
            "id": package_id,
            "version": "0.1.0",
            "schemaVersion": "0.1.0",
            "entrypoint": "ruleset.pkl",
            "definitionEntrypoints": ["definitions.pkl"],
            "description": description,
        },
        indent=2,
    )


def fixture_concepts() -> dict[str, set[str]]:
    """The `ex:` object types, property sets and properties the fixtures name."""
    concepts: dict[str, set[str]] = {
        "objectTypes": set(),
        "propertySets": set(),
        "properties": set(),
    }
    pending: list = [json.loads(data) for data in fixtures().values()]
    while pending:
        item = pending.pop()
        if isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, dict):
            for key, catalog in (
                ("objectType", "objectTypes"),
                ("propertySet", "propertySets"),
                ("property", "properties"),
            ):
                if isinstance(item.get(key), str) and item[key].startswith("ex:"):
                    concepts[catalog].add(item[key])
            pending.extend(item.values())
    return concepts


def conformance_definitions() -> str:
    """A definitions package declaring every concept the fixtures name and a
    rule template whose parameters the fixtures read."""
    catalogs = []
    for catalog, concepts in sorted(fixture_concepts().items()):
        entries = []
        for concept in sorted(concepts):
            kind = '\n    valueKind = "string"' if catalog == "properties" else ""
            entries.append(
                f"""  ["{concept}"] {{
    id = "{concept}"
    name {{ default = "{concept}" }}{kind}
    externalNames {{
      new {{ typeSystem = "axioval:conformance.fixtures"; name = "{concept}" }}
    }}
  }}
"""
            )
        catalogs.append(f"{catalog} {{\n{''.join(entries)}}}\n")
    return CONFORMANCE_DEFINITIONS.replace("%CATALOGS%", "".join(catalogs))


CONFORMANCE_DEFINITIONS = """\
amends "../schema/Definitions.pkl"

import "../schema/Values.pkl"

package {
  id = "axioval:conformance.expression-definitions"
  name { default = "Expression conformance definitions" }
  version = "0.1.0"
}
%CATALOGS%definitions {
  ["axioval:conformance.expression"] {
    id = "axioval:conformance.expression"
    name { default = "Expression" }
    capability = "axioval:capability.expression"
    parameters {
      ["expression"] {
        id = "expression"
        name { default = "Expression" }
        kind = "expression"
      }
      ["slope_angle"] {
        id = "slope_angle"
        name { default = "Slope angle" }
        kind = "number"
        required = false
        defaultValue = new Values.NumberValue { value = 0.1 }
      }
      ["minimum_width"] {
        id = "minimum_width"
        name { default = "Minimum width" }
        kind = "quantity"
        unitDimension = "https://qudt.org/vocab/quantitykind/Length"
        required = false
        defaultValue = new Values.QuantityValue { value = 0.9; unit = "m" }
      }
      ["limits"] {
        id = "limits"
        name { default = "Limits" }
        kind = "table"
        required = false
        columns {
          new { id = "key_1"; name { default = "Key 1" }; kind = "string" }
          new { id = "key_2"; name { default = "Key 2" }; kind = "string" }
          new { id = "maximum"; name { default = "Maximum" }; kind = "number" }
        }
        defaultValue = new Values.TableValue {
          value {
            new {
              ["key_1"] = new Values.StringValue { value = "EI 30" }
              ["key_2"] = new Values.StringValue { value = "office" }
              ["maximum"] = new Values.NumberValue { value = 35.0 }
            }
          }
        }
      }
    }
  }
}
"""


def conformance_ruleset(stems: list[str]) -> str:
    """A ruleset binding each fixture, imported from its shared Pkl module,
    as one rule's expression parameter."""
    imports = "".join(
        f'import "../tests/fixtures/expression/{stem}.pkl" as {alias(stem)}\n'
        for stem in stems
    )
    rules = "".join(rule(f"fixture-{stem}", alias(stem)) for stem in stems) + "".join(
        rule(rule_id, alias("literal-boolean")) for rule_id in OUTCOME_RULES
    )
    return f"""\
amends "../schema/RuleSets.pkl"

import "../schema/Expressions.pkl"
import "../schema/Selectors.pkl"
import "../schema/Types.pkl"
{imports}
package = new Types.PackageMetadata {{
  id = "axioval:conformance.expressions"
  name {{ default = "Expression conformance" }}
  version = "0.1.0"
}}
definitionPackages {{ "axioval:conformance.expression-definitions" }}
groupings {{
  ["flights-of-storey"] {{
    id = "flights-of-storey"
    name {{ default = "Flights of a storey" }}
    members = new Selectors.AllSelector {{}}
    by = new ClassificationGroupingKey {{ system = "conformance" }}
  }}
}}
values {{
  ["clear_width"] {{
    name {{ default = "Clear width" }}
    expression = new Expressions.PropertyExpression {{
      propertySet = "axioval:measured"
      property = "extent_x"
    }}
  }}
}}
root {{
  id = "root"
  name {{ default = "Fixtures" }}
  rules {{
{rules}  }}
}}
"""


def alias(stem: str) -> str:
    return "fixture_" + stem.replace("-", "_")


def rule(rule_id: str, module: str) -> str:
    return f"""\
    new {{
      id = "{rule_id}"
      definitionId = "axioval:conformance.expression"
      name {{ default = "{rule_id}" }}
      parameters {{
        ["expression"] = new Expressions.ExpressionValue {{ value = {module}.expression }}
      }}
    }}
"""


class ExpressionFixtureTests(unittest.TestCase):
    """The engine's expression fixtures, shared as conformance fixtures."""

    def test_fixtures_cover_every_kind_and_scalar_type(self) -> None:
        values = {stem: json.loads(data) for stem, data in fixtures().items()}
        self.assertEqual(
            {value["kind"] for value in values.values()},
            set(contracts.EXPRESSION_KINDS),
        )
        self.assertEqual(len(contracts.EXPRESSION_KINDS), 47)
        self.assertEqual(
            {
                value["value"]["type"]
                for value in values.values()
                if value["kind"] == "literal"
            },
            contracts.SCALAR_VALUE_KINDS,
        )
        for stem, value in values.items():
            self.assertEqual(value["kind"], stem.partition("-")[0], stem)
        modules = {path.stem for path in FIXTURES.glob("*.pkl")} - {"Fixture"}
        self.assertEqual(modules, set(values))

    def test_readme_pins_the_engine_commit(self) -> None:
        readme = (FIXTURES / "README.md").read_text()
        self.assertRegex(readme, r"\b[0-9a-f]{40}\b")
        self.assertIn("crates/contracts/ir/tests/fixtures/expression", readme)

    @unittest.skipUnless(
        os.environ.get("AXIOVAL_ENGINE_FIXTURES"),
        "set AXIOVAL_ENGINE_FIXTURES to the engine's expression fixture directory",
    )
    def test_fixtures_have_not_drifted_from_the_engine(self) -> None:
        engine = Path(os.environ["AXIOVAL_ENGINE_FIXTURES"])
        upstream = {
            path.stem: path.read_bytes() for path in sorted(engine.glob("*.json"))
        }
        self.assertTrue(upstream, f"no fixtures in {engine}")
        self.assertEqual(set(upstream), set(fixtures()))
        for stem, data in fixtures().items():
            self.assertEqual(data, upstream[stem], stem)

    def test_pkl_authors_every_fixture_byte_for_byte(self) -> None:
        stems = sorted(fixtures())
        self.assertEqual(len(stems), 56)
        with tempfile.TemporaryDirectory() as output:
            proc = subprocess.run(
                [
                    validate.pkl_executable(),
                    "eval",
                    "-f",
                    "json",
                    "--root-dir",
                    str(ROOT),
                    "--allowed-modules",
                    "file:,pkl:",
                    "--allowed-resources",
                    "prop:pkl.outputFormat",
                    "--output-path",
                    f"{output}/%{{moduleName}}.json",
                    *(str(FIXTURES / f"{stem}.pkl") for stem in stems),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            for stem in stems:
                with self.subTest(fixture=stem):
                    self.assertEqual(
                        (Path(output) / f"{stem}.json").read_bytes(),
                        fixtures()[stem],
                    )

    def test_binder_accepts_every_fixture_structurally(self) -> None:
        for stem, data in fixtures().items():
            with self.subTest(fixture=stem):
                contracts.validate_expression(json.loads(data), stem)

    def test_every_fixture_round_trips_through_mcs_byte_for_byte(self) -> None:
        """Every fixture binds as a rule's expression parameter in a package
        declaring the `ex:` concepts it names, packs deterministically,
        verifies, and comes back with the same bytes in the transport's
        canonical form (sorted keys, compact separators), the form `.mcs`
        stores normalized JSON in."""
        stems = sorted(fixtures())
        with tempfile.TemporaryDirectory() as directory:
            root = offline_root(Path(directory))
            package = root / "conformance"
            package.mkdir()
            (package / "axioval.json").write_text(
                manifest(
                    "axioval:conformance.expressions",
                    "Shared expression fixtures bound as rule parameters.",
                )
            )
            (package / "definitions.pkl").write_text(conformance_definitions())
            (package / "ruleset.pkl").write_text(conformance_ruleset(stems))
            first = Path(directory) / "one.mcs"
            second = Path(directory) / "two.mcs"
            mcs_archive.pack(package, first, root)
            mcs_archive.pack(package, second, root)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            metadata = mcs_archive.inspect(first)
            mcs_archive.verify(first)
            inventory = {entry["path"]: entry for entry in metadata["inventory"]}
            with zipfile.ZipFile(first) as archive:
                ruleset = json.loads(archive.read("normalized/ruleset.json"))
                for stem in stems:
                    source = f"source/tests/fixtures/expression/{stem}.pkl"
                    self.assertEqual(
                        archive.read(source), (FIXTURES / f"{stem}.pkl").read_bytes()
                    )
                    self.assertEqual(
                        inventory[source]["sha256"],
                        hashlib.sha256(
                            (FIXTURES / f"{stem}.pkl").read_bytes()
                        ).hexdigest(),
                    )
            bound = {
                rule["id"].removeprefix("fixture-"): rule["parameters"]["expression"]
                for rule in ruleset["root"]["rules"]
                if rule["id"].startswith("fixture-")
            }
            self.assertEqual(set(bound), set(fixtures()))
            for stem in stems:
                with self.subTest(fixture=stem):
                    self.assertEqual(bound[stem]["type"], "expression")
                    self.assertEqual(
                        mcs_archive._json_bytes(bound[stem]["value"]),
                        mcs_archive._json_bytes(json.loads(fixtures()[stem])),
                    )

    def test_example_packs_and_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = offline_root(Path(directory))
            shutil.copytree(EXAMPLE, root / "examples/expressions")
            archive = Path(directory) / "expressions.mcs"
            mcs_archive.pack(root / "examples/expressions", archive, root)
            mcs_archive.verify(archive)
            with zipfile.ZipFile(archive) as packed:
                ruleset = json.loads(packed.read("normalized/ruleset.json"))
            self.assertEqual(
                ruleset,
                json.loads((EXAMPLE / "expected/ruleset.json").read_text()),
            )


class ExpressionBindingTests(unittest.TestCase):
    """The binder accepts expressions only as fail-closed declarative data."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.definitions = json.loads(
            (EXAMPLE / "expected/definitions.json").read_text()
        )
        cls.ruleset = json.loads((EXAMPLE / "expected/ruleset.json").read_text())

    def documents(self) -> tuple[dict, dict]:
        return copy.deepcopy(self.ruleset), copy.deepcopy(self.definitions)

    def bind(self, ruleset: dict, definitions: dict) -> None:
        validate.bind_ruleset(ruleset, [definitions], "test", asset_root=EXAMPLE)

    def assert_refused(self, ruleset: dict, definitions: dict, reason: str) -> None:
        with self.assertRaises(SystemExit) as failure:
            self.bind(ruleset, definitions)
        self.assertIn(reason, str(failure.exception))

    @staticmethod
    def rule(ruleset: dict) -> dict:
        return ruleset["root"]["rules"][0]

    @staticmethod
    def requirement(ruleset: dict) -> dict:
        return ruleset["root"]["rules"][0]["parameters"]["requirement"]["value"]

    @staticmethod
    def selector(ruleset: dict) -> dict:
        return ruleset["root"]["rules"][0]["applicability"]["operands"][1]

    def test_accepts_example(self) -> None:
        self.bind(*self.documents())

    def test_rejects_unknown_property_concept_and_set(self) -> None:
        ruleset, definitions = self.documents()
        operand = self.selector(ruleset)["expression"]["operands"][0]["operand"]
        operand["property"] = "axioval:example.expressions.slope"
        self.assert_refused(ruleset, definitions, "unknown property concept")
        # A property is a qualified concept, as a selector names it.
        for property_set, name in (
            (None, "IsExternal"),
            ("Pset_WallCommon", "axioval:example.expressions.rise"),
        ):
            ruleset, definitions = self.documents()
            node = {"kind": "property", "property": name}
            if property_set is not None:
                node["propertySet"] = property_set
            self.requirement(ruleset)["left"] = node
            with self.subTest(property_set=property_set, name=name):
                self.assert_refused(ruleset, definitions, "qualified identifier")
        ruleset, definitions = self.documents()
        self.requirement(ruleset)["left"] = {
            "kind": "property",
            "propertySet": "axioval:unknown.set",
            "property": "axioval:example.expressions.rise",
        }
        self.assert_refused(ruleset, definitions, "unknown property-set concept")

    def test_binds_derived_set_names(self) -> None:
        ruleset, definitions = self.documents()
        self.requirement(ruleset)["left"] = {
            "kind": "property",
            "propertySet": "axioval:value",
            "property": "slope_percent",
        }
        self.bind(ruleset, definitions)
        for property_set, name, reason in (
            ("axioval:value", "steepness", "derives no value 'steepness'"),
            ("axioval:measured", "girth", "is not a measured name"),
            ("axioval:classification", "zone", "unknown classification 'zone'"),
        ):
            ruleset, definitions = self.documents()
            self.requirement(ruleset)["left"] = {
                "kind": "property",
                "propertySet": property_set,
                "property": name,
            }
            with self.subTest(property_set=property_set):
                self.assert_refused(ruleset, definitions, reason)

    def test_rejects_undeclared_derived_value(self) -> None:
        ruleset, definitions = self.documents()
        self.requirement(ruleset)["left"]["name"] = "slope"
        self.assert_refused(ruleset, definitions, "derives no value 'slope'")
        ruleset, definitions = self.documents()
        self.selector(ruleset)["expression"] = {"kind": "derived", "name": "slope"}
        self.assert_refused(ruleset, definitions, "derives no value 'slope'")

    def test_parameters_are_read_only_by_expression_parameters(self) -> None:
        ruleset, definitions = self.documents()
        self.requirement(ruleset)["right"]["name"] = "minimum_slope"
        self.assert_refused(ruleset, definitions, "has no parameter 'minimum_slope'")
        ruleset, definitions = self.documents()
        self.requirement(ruleset)["right"]["name"] = "requirement"
        self.assert_refused(ruleset, definitions, "is no single value")
        ruleset, definitions = self.documents()
        self.selector(ruleset)["expression"] = {
            "kind": "parameter",
            "name": "maximum_slope",
        }
        self.assert_refused(
            ruleset, definitions, "only the value of a rule's expression"
        )
        ruleset, definitions = self.documents()
        ruleset["values"]["slope_percent"]["expression"] = {
            "kind": "parameter",
            "name": "maximum_slope",
        }
        self.assert_refused(
            ruleset, definitions, "only the value of a rule's expression"
        )

    def test_unbound_optional_parameter_is_not_readable(self) -> None:
        ruleset, definitions = self.documents()
        parameter = definitions["definitions"][
            "axioval:example.expression-requirement"
        ]["parameters"]["maximum_slope"]
        parameter["required"] = False
        del self.rule(ruleset)["parameters"]["maximum_slope"]
        self.assert_refused(ruleset, definitions, "has no parameter 'maximum_slope'")
        parameter["defaultValue"] = {"type": "number", "value": 8.0}
        self.bind(ruleset, definitions)

    def test_lookup_binds_a_table_parameter_and_its_columns(self) -> None:
        ruleset, definitions = self.documents()
        lookup = {
            "kind": "lookup",
            "table": "limits",
            "keys": {
                "usage": {
                    "kind": "literal",
                    "value": {"type": "string", "value": "public"},
                }
            },
            "column": "maximum",
        }
        self.requirement(ruleset)["right"] = lookup
        self.assert_refused(ruleset, definitions, "has no parameter 'limits'")
        definition = definitions["definitions"][
            "axioval:example.expression-requirement"
        ]
        definition["parameters"]["limits"] = {
            "id": "limits",
            "name": {"default": "Limits", "translations": {}},
            "kind": "table",
            "required": True,
            "allowedValues": [],
            "columns": [
                {
                    "id": "usage",
                    "name": {"default": "Usage", "translations": {}},
                    "kind": "textPattern",
                    "required": True,
                },
                {
                    "id": "maximum",
                    "name": {"default": "Maximum", "translations": {}},
                    "kind": "number",
                    "required": True,
                },
            ],
        }
        self.rule(ruleset)["parameters"]["limits"] = {
            "type": "table",
            "value": [
                {
                    "usage": {"type": "string", "value": "public"},
                    "maximum": {"type": "number", "value": 6.0},
                }
            ],
        }
        self.bind(ruleset, definitions)
        lookup["column"] = "minimum"
        self.assert_refused(ruleset, definitions, "has no column 'minimum'")
        lookup["column"] = "maximum"
        lookup["table"] = "maximum_slope"
        self.assert_refused(ruleset, definitions, "is no table")

    def test_rule_outcomes_bind_and_never_cycle(self) -> None:
        ruleset, definitions = self.documents()
        self.requirement(ruleset)["right"] = {"kind": "deviation", "rule": "ramp-slope"}
        self.assert_refused(ruleset, definitions, "depends on its own outcome")
        ruleset, definitions = self.documents()
        self.selector(ruleset)["expression"] = {
            "kind": "ruleOutcome",
            "rule": "handrails",
        }
        self.assert_refused(ruleset, definitions, "which the ruleset does not define")
        ruleset, definitions = self.documents()
        ruleset["values"]["slope_percent"]["expression"] = {
            "kind": "findingCount",
            "rule": "ramp-slope",
        }
        self.assert_refused(ruleset, definitions, "values are derived before any rule")

    def test_values_are_identifiers_without_cycles(self) -> None:
        ruleset, definitions = self.documents()
        ruleset["values"]["slope_ratio"] = {
            "name": {"default": "Slope ratio", "translations": {}},
            "expression": {"kind": "derived", "name": "slope_percent"},
        }
        self.bind(ruleset, definitions)
        ruleset["values"]["slope_percent"]["expression"] = {
            "kind": "property",
            "propertySet": "axioval:value",
            "property": "slope_ratio",
        }
        self.assert_refused(ruleset, definitions, "read one another in a cycle")
        ruleset, definitions = self.documents()
        ruleset["values"]["slope percent"] = ruleset["values"].pop("slope_percent")
        self.assert_refused(ruleset, definitions, "a value name must be an identifier")
        ruleset, definitions = self.documents()
        ruleset["values"] = {}
        self.assert_refused(ruleset, definitions, "values is omitted when empty")
        ruleset, definitions = self.documents()
        ruleset["values"]["slope_percent"]["unit"] = "%"
        self.assert_refused(ruleset, definitions, "unknown=['unit']")

    def test_derived_sets_keep_their_evaluation_order(self) -> None:
        ruleset, definitions = self.documents()
        ruleset["classifications"] = {
            "steepness": {
                "id": "steepness",
                "name": {"default": "Steepness", "translations": {}},
                "rows": [
                    {
                        "selector": {
                            "kind": "expression",
                            "expression": {"kind": "ruleOutcome", "rule": "ramp-slope"},
                        },
                        "class": "steep",
                    }
                ],
            }
        }
        self.assert_refused(ruleset, definitions, "classes are derived before any rule")
        ruleset, definitions = self.documents()
        ruleset["groupings"] = {
            "flights": {
                "id": "flights",
                "name": {"default": "Flights", "translations": {}},
                "members": {
                    "kind": "expression",
                    "expression": {
                        "kind": "aggregate",
                        "function": "any",
                        "over": {"kind": "group", "grouping": "flights"},
                        "value": {
                            "kind": "literal",
                            "value": {"type": "boolean", "value": True},
                        },
                    },
                },
                "by": {"kind": "classification", "system": "Uniclass"},
            }
        }
        self.assert_refused(ruleset, definitions, "must not read a derived group")
        ruleset, definitions = self.documents()
        ruleset["relations"] = {
            "serves": {
                "id": "serves",
                "name": {"default": "Serves", "translations": {}},
                "from": {
                    "kind": "expression",
                    "expression": {
                        "kind": "aggregate",
                        "function": "count",
                        "over": {
                            "kind": "path",
                            "path": ["axioval:derived.relation;id=serves"],
                        },
                    },
                },
                "to": {"kind": "all"},
                "by": {"kind": "supplied"},
            }
        }
        self.assert_refused(
            ruleset, definitions, "must not read a rule's outcome or a declared"
        )

    def test_aggregates_bind_their_sources_and_filters(self) -> None:
        cases = (
            ({"kind": "group", "grouping": "flats"}, None, "unknown grouping 'flats'"),
            (
                {"kind": "path", "path": ["axioval:derived.relation;id=serves"]},
                None,
                "unknown relation 'serves'",
            ),
            (
                {"kind": "path", "path": ["IfcRelVoidsElement:sideways"]},
                None,
                "path step",
            ),
            (
                {
                    "kind": "selector",
                    "selector": {
                        "kind": "entityType",
                        "objectType": "axioval:unknown",
                        "includeSubtypes": True,
                    },
                },
                None,
                "unknown object-type concept",
            ),
            (
                {"kind": "measured", "name": "steps"},
                {"kind": "all"},
                "takes no where",
            ),
            (
                {"kind": "measured", "name": "treads"},
                None,
                "not a measured member list",
            ),
            ({"kind": "measured", "name": "steps;offset"}, None, "is not 'key=value'"),
        )
        for over, where, reason in cases:
            ruleset, definitions = self.documents()
            aggregate = {"kind": "aggregate", "function": "count", "over": over}
            if where is not None:
                aggregate["where"] = where
            self.requirement(ruleset)["left"] = aggregate
            with self.subTest(over=over):
                self.assert_refused(ruleset, definitions, reason)
        ruleset, definitions = self.documents()
        self.requirement(ruleset)["left"] = {
            "kind": "aggregate",
            "function": "max",
            "over": {"kind": "measured", "name": "steps"},
            "value": {
                "kind": "property",
                "propertySet": "axioval:member",
                "property": "rise",
            },
        }
        self.bind(ruleset, definitions)

    def test_member_fields_are_read_only_over_measured_members(self) -> None:
        ruleset, definitions = self.documents()
        self.requirement(ruleset)["left"] = {
            "kind": "property",
            "propertySet": "axioval:member",
            "property": "rise",
        }
        self.assert_refused(ruleset, definitions, "axioval:member is read only")

    def test_structure_fails_closed(self) -> None:
        literal = {"kind": "literal", "value": {"type": "number", "value": 1.0}}
        cases = (
            ({"kind": "loop", "body": literal}, "unknown expression kind 'loop'"),
            ({"kind": "null", "comment": "x"}, "unknown=['comment']"),
            ({"kind": "null", "label": " "}, "blank label"),
            ({"kind": "and", "operands": []}, "has no operands"),
            ({"kind": "if", "branches": [], "else": literal}, "has no branch"),
            ({"kind": "oneOf", "operand": literal, "values": []}, "has no values"),
            (
                {
                    "kind": "compare",
                    "operator": "equals",
                    "left": literal,
                    "right": literal,
                    "caseSensitive": True,
                },
                "caseSensitive is false or omitted",
            ),
            (
                {
                    "kind": "compare",
                    "operator": "is",
                    "left": literal,
                    "right": literal,
                },
                "unknown comparison 'is'",
            ),
            (
                {
                    "kind": "convertSlope",
                    "operand": literal,
                    "from": "ratio",
                    "to": "grade",
                },
                "'ratio', 'percent' or 'angle'",
            ),
            (
                {"kind": "literal", "value": {"type": "stringList", "value": ["a"]}},
                "one scalar value",
            ),
            (
                {"kind": "literal", "value": {"type": "number", "value": float("inf")}},
                "not finite",
            ),
            (
                {
                    "kind": "literal",
                    "value": {"type": "quantity", "value": 1.0, "unit": " "},
                },
                "blank unit",
            ),
            (
                {"kind": "literal", "value": {"type": "date", "value": "2026-02-29"}},
                "is not a date",
            ),
            (
                {
                    "kind": "aggregate",
                    "function": "sum",
                    "over": {"kind": "group", "grouping": "g"},
                },
                "takes a value unless it counts",
            ),
            (
                {
                    "kind": "aggregate",
                    "function": "count",
                    "over": {"kind": "group", "grouping": "g"},
                    "value": literal,
                },
                "takes a value unless it counts",
            ),
            ({"kind": "property", "property": " "}, "blank property"),
            (
                {"kind": "property", "property": "x", "of": "owner"},
                "of must be 'subject'",
            ),
            ({"kind": "ruleOutcome", "rule": "Not A Rule"}, "rule must be a rule id"),
            (
                {"kind": "lookup", "table": "limits", "keys": {}, "column": "maximum"},
                "matches no key column",
            ),
        )
        for expression, reason in cases:
            with self.subTest(expression=expression):
                with self.assertRaises(SystemExit) as failure:
                    contracts.validate_expression(expression, "test")
                self.assertIn(reason, str(failure.exception))

    def test_depth_size_and_aggregate_nesting_are_bounded(self) -> None:
        def nested(depth: int) -> dict:
            node: dict = {"kind": "null"}
            for _ in range(depth - 1):
                node = {"kind": "not", "operand": node}
            return node

        contracts.validate_expression(nested(64), "test")
        with self.assertRaises(SystemExit) as failure:
            contracts.validate_expression(nested(65), "test")
        self.assertIn("deeper than 64", str(failure.exception))
        many = {"kind": "and", "operands": [{"kind": "null"}] * 2047}
        contracts.validate_expression(many, "test")
        many["operands"].append({"kind": "null"})
        with self.assertRaises(SystemExit) as failure:
            contracts.validate_expression(many, "test")
        self.assertIn("more than 2048 nodes", str(failure.exception))

        def aggregates(levels: int) -> dict:
            node: dict = {"kind": "literal", "value": {"type": "integer", "value": 1}}
            for _ in range(levels):
                node = {
                    "kind": "aggregate",
                    "function": "sum",
                    "over": {"kind": "path", "path": ["IfcRelAggregates"]},
                    "value": node,
                }
            return node

        contracts.validate_expression(aggregates(2), "test")
        with self.assertRaises(SystemExit) as failure:
            contracts.validate_expression(aggregates(3), "test")
        self.assertIn("aggregates nest deeper than 2", str(failure.exception))
        # A member filter's expressions count toward the nesting, as the
        # engine counts them.
        filtered = aggregates(1)
        filtered["where"] = {"kind": "expression", "expression": aggregates(2)}
        with self.assertRaises(SystemExit) as failure:
            contracts.validate_expression(filtered, "test")
        self.assertIn("aggregates nest deeper than 2", str(failure.exception))

    def test_expression_values_need_an_expression_parameter(self) -> None:
        ruleset, definitions = self.documents()
        self.rule(ruleset)["parameters"]["maximum_slope"] = {
            "type": "expression",
            "value": {"kind": "literal", "value": {"type": "number", "value": 6.0}},
        }
        self.assert_refused(ruleset, definitions, "expected number value variant")
        ruleset, definitions = self.documents()
        self.rule(ruleset)["parameters"]["requirement"] = {
            "type": "boolean",
            "value": True,
        }
        self.assert_refused(ruleset, definitions, "expected expression value variant")

    def test_expression_defaults_bind_against_the_rule_using_them(self) -> None:
        ruleset, definitions = self.documents()
        requirement = self.rule(ruleset)["parameters"].pop("requirement")
        parameter = definitions["definitions"][
            "axioval:example.expression-requirement"
        ]["parameters"]["requirement"]
        parameter["required"] = False
        parameter["defaultValue"] = requirement
        self.bind(ruleset, definitions)
        requirement["value"]["left"] = {
            "kind": "property",
            "property": "axioval:unknown",
        }
        self.assert_refused(ruleset, definitions, "unknown property concept")

    def test_pkl_rejects_unsupported_parameter_kinds(self) -> None:
        source = (ROOT / "schema/Definitions.pkl").read_text()
        kinds = re.search(r"typealias ParameterKind = (.*)", source).group(1)
        self.assertIn('"expression"', kinds)
        self.assertIn("expression", contracts.VALUE_KINDS)
        self.assertNotIn("expression", contracts.PROPERTY_VALUE_KINDS)


if __name__ == "__main__":
    unittest.main()
