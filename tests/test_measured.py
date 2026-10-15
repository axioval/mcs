from __future__ import annotations

import copy
import json
import os
import re
import unittest
from pathlib import Path

from scripts import contracts, measured_registry, validate

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/expressions"
MEASURED_SET = "axioval:measured"
# The done-when names of axioval/mcs#8.
SUM_WITHIN = "sum_within;to=ex:extinguisher;value=ex:units;radius=15"


def pkl_set(path: Path, const: str) -> list[str]:
    """The names a Pkl `Set(...)` constant lists, in order."""
    match = re.search(
        rf"const {const}: Set<String> = Set\((.*?)\n\)", path.read_text(), re.S
    )
    assert match, f"{path} declares no {const}"
    return re.findall(r'"([^"]*)"', match.group(1))


def sample(parameter: dict) -> str:
    """A value of `parameter`'s kind the engine accepts."""
    kind = parameter["kind"]
    return {
        "path": "IfcRelAggregates:backward",
        "paths": "IfcRelAggregates:backward IfcRelNests",
        "sourceKind": "IfcWall",
        "objects": "IfcWall",
        "text": "WA1",
        "pattern": "[A-Z]+",
        "length": "1",
        "number": "1",
        "area": "1",
        "angle": "1",
        "truth": "true",
        "vector": "0,0,1",
        "polygon": "0:0,1:0,0:1",
        "property": "Pset_Example/Value",
        "table": "@table",
        "choice": (kind.get("options") or [""])[0],
        "choices": (kind.get("options") or [""])[0],
    }[kind["type"]]


def least_call(entry: dict) -> str:
    """`entry`'s name with every required parameter, and what its checks
    across parameters need besides: a `radius`, a `zone`, a facing face's
    `direction` and `tolerance`."""
    parameters = {parameter["key"]: parameter for parameter in entry["parameters"]}
    stated = {
        key: sample(parameter)
        for key, parameter in parameters.items()
        if parameter["required"]
    }
    reaches = [key for key in ("radius", "group", "zone") if key in parameters]
    if len(reaches) > 1 and not set(reaches) & set(stated):
        stated["radius"] = "1"
    if {"zone", "stands_in"} <= parameters.keys() and not {"zone", "stands_in"} & set(
        stated
    ):
        stated["zone"] = "WA1"
    if stated.get("face") == "facing":
        stated.update(direction="0,0,1", tolerance="10")
    return ";".join([entry["name"], *(f"{key}={value}" for key, value in stated.items())])


class MeasuredRegistryTests(unittest.TestCase):
    """The binder's measured names are the engine's measured registry."""

    def test_snapshot_pins_the_engine_commit(self) -> None:
        engine = contracts.MEASURED_REGISTRY["engine"]
        self.assertRegex(engine["commit"], r"\A[0-9a-f]{40}\Z")
        self.assertEqual(engine["repository"], "https://github.com/axioval/engine")
        self.assertEqual(engine["source"], measured_registry.SOURCE)

    def test_snapshot_is_rendered_deterministically(self) -> None:
        snapshot = measured_registry.load()
        rendered = measured_registry.render(
            {
                "measuredValues": snapshot["measuredValues"],
                "measuredMembers": snapshot["measuredMembers"],
            },
            snapshot["engine"]["commit"],
        )
        self.assertEqual(rendered, measured_registry.SNAPSHOT.read_text(encoding="utf-8"))

    def test_names_are_sorted_lowercase_and_known_kinds(self) -> None:
        for registry in (contracts.MEASURED_VALUES, contracts.MEASURED_MEMBERS):
            names = list(registry)
            self.assertEqual(names, sorted(set(names)))
            for name, entry in registry.items():
                # Pkl's `isPropertyName` matches the base against this.
                self.assertRegex(name, r"\A[a-z_]+\Z")
                self.assertIn(entry.get("subject", "object"), {"object", "source", "project"})
                for parameter in entry["parameters"]:
                    with self.subTest(name=name, key=parameter["key"]):
                        self.assertIn(
                            parameter["kind"]["type"], contracts.MEASURED_PARAMETER_KINDS
                        )
        self.assertFalse(contracts.MEASURED_VALUES.keys() & contracts.MEASURED_MEMBERS.keys())

    def test_pkl_lists_every_registry_name(self) -> None:
        self.assertEqual(
            pkl_set(ROOT / "schema/Types.pkl", "measuredNames"),
            list(contracts.MEASURED_VALUES),
        )
        self.assertEqual(
            pkl_set(ROOT / "schema/Expressions.pkl", "measuredMemberLists"),
            list(contracts.MEASURED_MEMBERS),
        )

    def test_every_name_with_its_required_parameters_parses(self) -> None:
        for name, entry in contracts.MEASURED_VALUES.items():
            with self.subTest(name=name):
                self.assertIsNone(contracts.measured_name_error(least_call(entry)))
        for name, entry in contracts.MEASURED_MEMBERS.items():
            with self.subTest(name=name):
                self.assertIsNone(contracts.measured_members_error(least_call(entry)))

    def test_drift_reports_a_name_the_engine_adds(self) -> None:
        snapshot = measured_registry.load()
        catalogue = {
            "measuredValues": copy.deepcopy(snapshot["measuredValues"]),
            "measuredMembers": copy.deepcopy(snapshot["measuredMembers"]),
        }
        self.assertEqual(measured_registry.drift(snapshot, catalogue), [])
        catalogue["measuredValues"].append(
            {"name": "girth", "parameters": [], "label": [], "help": []}
        )
        catalogue["measuredMembers"].pop()
        catalogue["measuredValues"][0]["parameters"][0]["required"] = False
        self.assertEqual(
            measured_registry.drift(snapshot, catalogue),
            [
                "measuredValues: the engine adds 'girth'",
                "measuredValues: the engine changes 'above_terrain'",
                "measuredMembers: the engine no longer has "
                f"{snapshot['measuredMembers'][-1]['name']!r}",
            ],
        )

    @unittest.skipUnless(
        os.environ.get("AXIOVAL_ENGINE_CATALOGUE"),
        "set AXIOVAL_ENGINE_CATALOGUE to the engine's golden authoring catalogue",
    )
    def test_registry_has_not_drifted_from_the_engine(self) -> None:
        catalogue = json.loads(
            Path(os.environ["AXIOVAL_ENGINE_CATALOGUE"]).read_text(encoding="utf-8")
        )
        snapshot = measured_registry.load()
        self.assertEqual(measured_registry.drift(snapshot, catalogue), [])
        upstream = measured_registry.project(catalogue)
        for section in ("measuredValues", "measuredMembers"):
            self.assertEqual(snapshot[section], upstream[section], section)


class MeasuredGrammarTests(unittest.TestCase):
    """Parameters are checked as the engine's `measured::parse` checks them,
    refused with the engine's reason."""

    ACCEPTED = (
        "slope",
        "SLOPE",
        SUM_WITHIN,
        "Sum_Within; TO = IfcFireSuppressionTerminal ; value=Pset_Extinguisher/Units;radius=@reach",
        "sum_within;to=a;value=b;zone=WA1",
        "sum_within;to=a;value=b;zone=@zone_id",
        "sum_within;to=a;value=b;group=compartments",
        "sum_within;to=a;value=b;radius=30;measure=walking;walking_radius=0.3;"
        "walking_height=2;walking_step=0.2;walking_slope=0.06",
        "count_within;to=IfcDoor;zone=WA1",
        "count_within;to=IfcDoor;radius=5;projection=vertical;direction=above",
        "slope;face=facing;direction=0,0,1;tolerance=180",
        "boundary_area;kind=IfcWall",
        "bottom_above_level;path=IfcRelAggregates:backward+,IfcRelNests",
        "above_terrain;terrain=original;of=top",
        "above_terrain;terrain=finished;of=level;reference=beneath;path=IfcRelContainedInSpatialStructure",
        "mean_terrain_height;terrain=original;outline=IfcBuilding",
        "zone_area;zone=WA1",
        "zone_area;stands_in=parcel",
        "zone_value;stands_in=parcel;value=storeys_max",
        "zone_length;zone=@zone;value=eaves_height",
        "zone_angle;zone=WA1;value=roof_pitch_min",
        "zone_footprint_area;zone=WA1;elements=IfcBuilding",
        "setback_depth;terrain=original;factor=0.4;minimum=3",
        "setback_outside_area;terrain=finished;factor=0.4;stands_in=parcel",
        "setback_overlap_area;terrain=original;factor=0.4;others=@neighbours;"
        "roof=IfcRoof;roof_share=0.5",
        "undrained_area;outlets=IfcFlowTerminal",
        "drainage_path;outlets=@outlets;minimum_fall=0.01",
        "max_along;of=gradient",
        "fall_in_flow",
        "extent_x",
    )
    MEMBERS = (
        "steps",
        "layers",
        "layers;spaces=IfcSpace",
        "zone_neighbours;stands_in=parcel;kinds=road",
        "line_spacing;members=IfcBeam;member_path=IfcRelAggregates;direction=1,0,0",
        "roof_features;feature=ridge",
    )
    REFUSED = (
        ("slpoe", "`slpoe` is no measured value; known: above_terrain, "),
        ("sum_within;to=ex:extinguisher;value=ex:units", "`sum_within` needs `radius`"),
        ("sum_within;value=ex:units;radius=15", "`sum_within` needs `to`"),
        ("extent_x;path=a", "`extent_x` takes no parameter `path`"),
        (
            "sum_within;to=a;value=b;radius=1;radios=2",
            "`sum_within` takes no parameter `radios`; it takes `to`, `value`, "
            "`radius`, ",
        ),
        ("area;flat", "`flat` of `area` is not `key=value`"),
        ("boundary_area;kind=IfcWall;KIND=IfcSlab", "`boundary_area` states `kind` twice"),
        ("boundary_area;kind=", "`boundary_area` parameter `kind`: it is empty"),
        (
            "boundary_area;kind=w;plane=1_0",
            "`boundary_area` parameter `plane`: `1_0` is no length of at least 0 m",
        ),
        ("bottom_above_level;path=a,,b", "`bottom_above_level` parameter `path`: a step is empty"),
        (
            "bottom_above_level;path=Ifc Rel",
            "`bottom_above_level` parameter `path`: path step 'Ifc Rel' must be",
        ),
        (
            "count_within;to=IfcDoor;radius=5;zone=WA1",
            "`count_within` parameter `zone`: one of `radius`, `zone` reaches the "
            "counterparts",
        ),
        (
            "sum_within;to=a;value=b;group=g;zone=z",
            "`sum_within` parameter `zone`: one of `radius`, `group`, `zone` reaches "
            "the counterparts",
        ),
        (
            "sum_within;to=a;value=b;zone=z;projection=horizontal",
            "`sum_within` parameter `projection`: a context `zone` reaches the "
            "counterparts at no distance",
        ),
        (
            "sum_within;to=a;value=b;group=g;from=1",
            "`sum_within` parameter `from`: a shared `group` reaches the counterparts "
            "at no distance",
        ),
        (
            "sum_within;to=a;value=b;radius=30;measure=walking",
            "`sum_within` needs `walking_radius`",
        ),
        (
            "sum_within;to=a;value=b;radius=30;walking_step=0.2",
            "`sum_within` parameter `walking_step`: only `measure=walking` takes it",
        ),
        (
            "sum_within;to=a;value=b;radius=30;measure=walking;walking_radius=0.3;"
            "walking_height=2;walking_step=0.2;projection=horizontal",
            "`sum_within` parameter `projection`: a walk is measured in plan, never "
            "projected",
        ),
        (
            "slope;face=facing;direction=0,0,1",
            "`slope` needs `tolerance`",
        ),
        (
            "slope;direction=0,0,1",
            "`slope` parameter `direction`: only `face=facing` takes it",
        ),
        (
            "slope;face=facing;direction=0,0,1;tolerance=180.5",
            "`slope` parameter `tolerance`: 180.5 degrees is more than 180",
        ),
        (
            "slope;face=facing;direction=0,0,0;tolerance=1",
            "`slope` parameter `direction`: `0,0,0` is no `x,y,z` direction",
        ),
        (
            "slope;face=steep",
            "`slope` parameter `face`: `steep` is none of top, bottom, facing",
        ),
        ("zone_area", "`zone_area` needs `zone`"),
        (
            "zone_area;zone=WA1;stands_in=parcel",
            "`zone_area` parameter `stands_in`: it names the zone in place of `zone`; "
            "state one of them",
        ),
        (
            "zone_length;zone=WA1;value=coverage_ratio_max",
            "`zone_length` parameter `value`: `coverage_ratio_max` is none of eaves_height",
        ),
        (
            "zone_footprint_area;zone=WA1;elements=@anchor",
            "`zone_footprint_area` parameter `elements`: `@anchor` names the anchor, "
            "but `zone_footprint_area` is measured for each project, never for an object",
        ),
        ("zone_footprint_area;stands_in=parcel;elements=x", "`zone_footprint_area` takes no parameter `stands_in`"),
        (
            "boundary_area;kind=@anchor",
            "`boundary_area` parameter `kind`: `@anchor` names the anchor, which only "
            "objects measured against take",
        ),
        (
            "slope;face=facing;direction=@d;tolerance=1",
            "`slope` parameter `direction`: `@d` names a rule parameter, which it never takes",
        ),
        ("boundary_area;kind=@", "`boundary_area` parameter `kind`: `@` names no rule parameter"),
        (
            "setback_depth;terrain=original;factor=-1",
            "`setback_depth` parameter `factor`: `-1` is no number of at least 0",
        ),
        (
            "undrained_area;outlets=IfcFlowTerminal;minimum_fall=x",
            "`undrained_area` parameter `minimum_fall`: `x` is no number of at least 0",
        ),
        (
            "above_terrain;terrain=original;of=top;reference=lowest",
            "`above_terrain` parameter `reference`: `lowest` is none of mean, beneath",
        ),
    )
    MEMBERS_REFUSED = (
        ("treads", "`treads` is no measured member list; known: alignment_elements, "),
        ("layers;rooms=IfcSpace", "`layers` takes no parameter `rooms`; it takes `spaces`"),
        ("zone_neighbours;kinds=road", "`zone_neighbours` needs `zone`"),
        (
            "line_spacing;members=IfcBeam;member_path=a;direction=1,0",
            "`line_spacing` parameter `direction`: `1,0` is no `x,y,z` direction",
        ),
    )

    def test_accepts_registry_names_and_parameters(self) -> None:
        for name in self.ACCEPTED:
            with self.subTest(name=name):
                self.assertIsNone(contracts.measured_name_error(name))
        for name in self.MEMBERS:
            with self.subTest(name=name):
                self.assertIsNone(contracts.measured_members_error(name))

    def test_refuses_with_the_engines_reason(self) -> None:
        for name, reason in self.REFUSED:
            with self.subTest(name=name):
                error = contracts.measured_name_error(name)
                self.assertIsNotNone(error)
                self.assertTrue(error.startswith(reason), error)
        for name, reason in self.MEMBERS_REFUSED:
            with self.subTest(name=name):
                error = contracts.measured_members_error(name)
                self.assertIsNotNone(error)
                self.assertTrue(error.startswith(reason), error)

    def test_member_lists_are_no_measured_values(self) -> None:
        self.assertTrue(
            contracts.measured_name_error("layers").startswith(
                "`layers` is no measured value"
            )
        )
        self.assertTrue(
            contracts.measured_members_error("slope").startswith(
                "`slope` is no measured member list"
            )
        )

    def test_polygons_are_simple(self) -> None:
        self.assertIsNone(contracts.polygon_problem([(0, 0), (1, 0), (0, 1)]))
        for vertices, problem in (
            ([(0, 0), (1, 0)], "it has 2 vertices, fewer than three"),
            ([(0, 0), (1, 0), (2, 0)], "it encloses no area"),
            ([(0, 0), (2, 2), (2, 0), (0, 1)], "edges 1 and 3 cross or touch"),
            ([(0, 0), (0, 0), (1, 1), (0, 1)], "vertex 2 repeats the one before it"),
            ([(0, 0), (2, 0), (1, 0), (1, 1)], "edges 1 and 2 overlap"),
            ([(0, 0), (float("inf"), 0), (0, 1)], "a coordinate is not finite"),
        ):
            with self.subTest(vertices=vertices):
                self.assertEqual(contracts.polygon_problem(vertices), problem)


class MeasuredBindingTests(unittest.TestCase):
    """A package reading a measured value binds; a wrong one is refused with
    the registry's reason wherever it is read."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.definitions = json.loads((EXAMPLE / "expected/definitions.json").read_text())
        cls.ruleset = json.loads((EXAMPLE / "expected/ruleset.json").read_text())

    def bind(self, left: dict, applicability: dict | None = None) -> None:
        ruleset = copy.deepcopy(self.ruleset)
        rule = ruleset["root"]["rules"][0]
        rule["parameters"]["requirement"]["value"]["left"] = left
        if applicability is not None:
            rule["applicability"]["operands"].append(applicability)
        validate.bind_ruleset(
            ruleset, [copy.deepcopy(self.definitions)], "test", asset_root=EXAMPLE
        )

    @staticmethod
    def measured(name: str) -> dict:
        return {"kind": "property", "propertySet": MEASURED_SET, "property": name}

    @staticmethod
    def selector(name: str) -> dict:
        return {
            "kind": "property",
            "propertySet": MEASURED_SET,
            "property": name,
            "operator": "exists",
        }

    def test_done_when_names_bind(self) -> None:
        for name in (SUM_WITHIN, "slope"):
            with self.subTest(name=name):
                self.bind(self.measured(name), self.selector(name))
        self.bind(
            {
                "kind": "aggregate",
                "function": "sum",
                "over": {"kind": "measured", "name": "layers;spaces=IfcSpace"},
                "value": {
                    "kind": "property",
                    "propertySet": "axioval:member",
                    "property": "thickness",
                },
            }
        )

    def test_misspelled_name_and_missing_radius_are_refused(self) -> None:
        for name, reason in (
            ("sum_withn;to=ex:extinguisher;value=ex:units;radius=15",
             "`sum_withn` is no measured value; known: "),
            ("sum_within;to=ex:extinguisher;value=ex:units",
             "`sum_within` needs `radius`"),
        ):
            for left, applicability in (
                (self.measured(name), None),
                (self.measured("slope"), self.selector(name)),
            ):
                with self.subTest(name=name, selector=applicability is not None):
                    with self.assertRaises(SystemExit) as failure:
                        self.bind(left, applicability)
                    self.assertIn(reason, str(failure.exception))
        with self.assertRaises(SystemExit) as failure:
            self.bind(
                {
                    "kind": "aggregate",
                    "function": "count",
                    "over": {"kind": "measured", "name": "zone_neighbours"},
                }
            )
        self.assertIn("`zone_neighbours` needs `zone`", str(failure.exception))


if __name__ == "__main__":
    unittest.main()
