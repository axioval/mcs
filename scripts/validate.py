#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import json
import re
import shutil
import subprocess
from pathlib import Path

if __package__:
    from .contracts import (
        QUALIFIED_ID,
        SEMVER,
        bind_definition_documents,
        bind_ruleset,
        validate_definition_document,
    )
else:
    from contracts import (
        QUALIFIED_ID,
        SEMVER,
        bind_definition_documents,
        bind_ruleset,
        validate_definition_document,
    )

ROOT = Path(__file__).resolve().parents[1]
# Fields every package kind requires. A rule-set package also requires its
# `entrypoint`; a definitions package must not have one.
REQUIRED = {
    "manifestVersion",
    "kind",
    "id",
    "version",
    "schemaVersion",
    "definitionEntrypoints",
}
KINDS = {"ruleset", "definitions"}
ALLOWED = REQUIRED | {"entrypoint", "$schema", "description", "license"}
PKL_ENTRYPOINT = re.compile(r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$)).+\.pkl$")
# Pkl checks metadata, the stable GitHub release URL, and its signed redirect even
# when package bytes are cached. Keep that transport access scoped to the two
# checksum-locked OpenBIM packages rather than granting package code arbitrary
# HTTPS reads.
PKL_PACKAGE_RESOURCE_ALLOWLIST = ",".join(
    (
        r"https://openbimrs\.github\.io/pkl/.*",
        r"https://github\.com/openbimrs/pkl/releases/download/.*",
        r"https://release-assets\.githubusercontent\.com/.*",
        "prop:pkl.outputFormat",
    )
)


def fail(message: str) -> None:
    raise SystemExit(f"validation failed: {message}")


def pkl_executable() -> str:
    executable = shutil.which("pkl")
    if executable is None:
        fail("pkl is not installed or not on PATH")
    return executable


def evaluate(module: Path, root: Path = ROOT) -> dict:
    root = root.resolve()
    # Pkl resolves declared @aliases to projectpackage: URIs even when their
    # lockfile entries are checksum-pinned remote package: dependencies.
    command = [
        pkl_executable(),
        "eval",
        "-f",
        "json",
        "--root-dir",
        str(root),
        "--allowed-modules",
        "file:,pkl:,package:,projectpackage:",
        "--allowed-resources",
        PKL_PACKAGE_RESOURCE_ALLOWLIST,
        "--timeout",
        "10",
        str(module),
    ]
    proc = subprocess.run(
        command, cwd=module.parent, text=True, capture_output=True, check=False
    )
    if proc.returncode:
        fail(f"{module.relative_to(root)}: Pkl evaluation failed\n{proc.stderr}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        fail(f"{module.relative_to(root)} did not render JSON: {exc}")


def evaluate_project(root: Path = ROOT) -> None:
    root = root.resolve()
    command = [
        pkl_executable(),
        "eval",
        "--root-dir",
        str(root),
        "--allowed-modules",
        "file:,pkl:",
        "--allowed-resources",
        "prop:pkl.outputFormat",
        "--timeout",
        "10",
        str(root / "PklProject"),
    ]
    proc = subprocess.run(
        command, cwd=root, text=True, capture_output=True, check=False
    )
    if proc.returncode:
        fail(f"PklProject evaluation failed\n{proc.stderr}")


def local_module(base: Path, value: str) -> Path:
    if (
        not value.endswith(".pkl")
        or Path(value).is_absolute()
        or ".." in Path(value).parts
    ):
        fail(f"unsafe Pkl entrypoint: {value!r}")
    target = (base / value).resolve()
    if not target.is_relative_to(base.resolve()) or not target.is_file():
        fail(f"missing or escaping Pkl entrypoint: {value!r}")
    return target


def check_snapshot(module: Path, value: dict) -> None:
    snapshot = module.parent / "expected" / f"{module.stem}.json"
    if snapshot.is_file() and json.loads(snapshot.read_text()) != value:
        fail(f"{snapshot.relative_to(ROOT)} is stale")


def validate_manifest(manifest: object, path: Path) -> dict:
    if type(manifest) is not dict:
        fail(f"{path}: manifest must be an object")
    # Anything but a definitions package is held to the rule-set contract, so
    # a missing or unknown kind still reports the rule-set fields.
    definitions_only = manifest.get("kind") == "definitions"
    required = REQUIRED if definitions_only else REQUIRED | {"entrypoint"}
    allowed = ALLOWED - {"entrypoint"} if definitions_only else ALLOWED
    missing = required - manifest.keys()
    unknown = manifest.keys() - allowed
    if missing or unknown:
        fail(f"{path}: missing={sorted(missing)}, unknown={sorted(unknown)}")
    scalar_fields = required - {"definitionEntrypoints"}
    if any(type(manifest[field]) is not str for field in scalar_fields):
        fail(f"{path}: manifest scalar fields must be strings")
    entries = manifest["definitionEntrypoints"]
    if (
        type(entries) is not list
        or not entries
        or any(type(entry) is not str for entry in entries)
        or len(entries) != len(set(entries))
    ):
        fail(f"{path}: definitionEntrypoints must be non-empty unique strings")
    if (
        not definitions_only and not PKL_ENTRYPOINT.fullmatch(manifest["entrypoint"])
    ) or any(not PKL_ENTRYPOINT.fullmatch(entry) for entry in entries):
        fail(f"{path}: entrypoints must be safe repository-relative .pkl paths")
    if (
        manifest["manifestVersion"] != "0.1.0"
        or manifest["schemaVersion"] != "0.1.0"
        or manifest["kind"] not in KINDS
        or not QUALIFIED_ID.fullmatch(manifest["id"])
        or not SEMVER.fullmatch(manifest["version"])
    ):
        fail(f"{path}: invalid manifest constants, package identity, or version")
    if "$schema" in manifest and type(manifest["$schema"]) is not str:
        fail(f"{path}: $schema must be a string")
    for field in ("description", "license"):
        if field in manifest and (
            type(manifest[field]) is not str or not manifest[field]
        ):
            fail(f"{path}: {field} must be a non-empty string")
    return manifest


def ruleset_entrypoint(manifest: dict) -> str | None:
    """Return a validated manifest's rule-set entrypoint, or None for definitions."""
    return manifest["entrypoint"] if manifest["kind"] == "ruleset" else None


def bind_definitions_package(
    manifest: dict,
    definition_values: list[dict],
    context: str,
    *,
    asset_root: Path | None = None,
) -> None:
    """Bind a definitions package, which has no rule set, on its own.

    Its documents must bind together as a rule set would load them, and the
    manifest identity must be the package identity of exactly one of them.
    """
    bind_definition_documents(definition_values, context, asset_root=asset_root)
    matches = [
        value
        for value in definition_values
        if value["package"]["id"] == manifest["id"]
        and value["package"]["version"] == manifest["version"]
    ]
    if len(matches) != 1:
        fail(
            f"{context}: manifest identity {manifest['id']}@{manifest['version']} "
            "is not the package identity of one definition document"
        )


def repository_root(package: Path) -> Path:
    """Return the nearest directory at or above a package holding a PklProject.

    A package directory's modules amend the schema of the repository it lives
    in, so they evaluate with that repository as the Pkl root.
    """
    for candidate in (package, *package.parents):
        if (candidate / "PklProject").is_file():
            return candidate
    fail(f"{package}: no PklProject at or above the package directory")


def load_definitions_directory(package_dir: Path) -> list[tuple[dict, Path]]:
    """Evaluate and bind a supplied definitions package directory.

    The directory must hold a definitions-kind `axioval.json`. Its definition
    modules are evaluated, validated and bound on their own, as for any
    definitions package; the documents are returned with the package
    directory as their asset root, for a rule set to resolve from.
    """
    if package_dir.is_symlink() or not package_dir.is_dir():
        fail(f"{package_dir}: supplied definitions must be a package directory")
    package = package_dir.resolve()
    manifest_path = package / "axioval.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        fail(f"{package_dir}: supplied definitions package has no axioval.json")
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"{manifest_path}: invalid JSON: {exc}")
    manifest = validate_manifest(raw, manifest_path)
    if manifest["kind"] != "definitions":
        fail(f"{manifest_path}: a supplied package must be a definitions package")
    root = repository_root(package)
    values = []
    for entry in manifest["definitionEntrypoints"]:
        module = local_module(package, entry)
        value = evaluate(module, root)
        if type(value) is not dict or value.get("schemaVersion") != manifest[
            "schemaVersion"
        ]:
            fail(f"{module}: schema version disagrees with manifest")
        validate_definition_document(value, str(module), asset_root=package)
        values.append(value)
    bind_definitions_package(manifest, values, str(manifest_path), asset_root=package)
    return [(value, package) for value in values]


def main(arguments: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="validate.py", description="Validate the example packages."
    )
    parser.add_argument(
        "--definitions",
        action="append",
        default=[],
        type=Path,
        metavar="PATH",
        help=(
            "a definitions package (.mcs archive or package directory) a rule "
            "set may resolve its uncarried definitionPackages from; repeatable"
        ),
    )
    args = parser.parse_args(arguments)
    if __package__:
        from . import mcs_archive
    else:
        import mcs_archive
    with contextlib.ExitStack() as stack:
        try:
            supplied = stack.enter_context(
                mcs_archive.supplied_definitions(args.definitions)
            )
        except mcs_archive.MCSError as exc:
            fail(str(exc))
        validate_examples(supplied)


def validate_examples(supplied: list[tuple[dict, Path | None]]) -> None:
    expected_version = (ROOT / ".pkl-version").read_text().strip()
    version = subprocess.run(
        [pkl_executable(), "--version"], text=True, capture_output=True, check=True
    ).stdout
    if not version.startswith(f"Pkl {expected_version} "):
        fail(f"expected Pkl {expected_version}, got {version.strip()}")
    json.loads((ROOT / "schema/registry-manifest.schema.json").read_text())
    manifests = sorted((ROOT / "examples").glob("**/axioval.json"))
    if not manifests:
        fail("no example package manifests found")
    validated_manifests = []
    for manifest_path in manifests:
        manifest = validate_manifest(
            json.loads(manifest_path.read_text()), manifest_path
        )
        entrypoint = ruleset_entrypoint(manifest)
        module = (
            None
            if entrypoint is None
            else local_module(manifest_path.parent, entrypoint)
        )
        definition_modules = [
            local_module(manifest_path.parent, entry)
            for entry in manifest["definitionEntrypoints"]
        ]
        validated_manifests.append(
            (manifest_path, manifest, module, definition_modules)
        )

    for manifest_path, manifest, module, definition_modules in validated_manifests:
        value = None if module is None else evaluate(module)
        package = {} if value is None else value.get("package", {})
        if value is not None and (
            value.get("schemaVersion") != manifest["schemaVersion"]
            or package.get("id") != manifest["id"]
            or package.get("version") != manifest["version"]
        ):
            fail(f"{manifest_path}: manifest and evaluated package disagree")
        definition_values = []
        for definition in definition_modules:
            definitions = evaluate(definition)
            if definitions.get("schemaVersion") != manifest["schemaVersion"]:
                fail(f"{definition}: schema version disagrees with manifest")
            validate_definition_document(
                definitions,
                str(definition.relative_to(ROOT)),
                asset_root=manifest_path.parent,
            )
            definition_values.append(definitions)
            check_snapshot(definition, definitions)
        if module is None:
            bind_definitions_package(
                manifest,
                definition_values,
                str(manifest_path.relative_to(ROOT)),
                asset_root=manifest_path.parent,
            )
            continue
        bind_ruleset(
            value,
            definition_values,
            str(module.relative_to(ROOT)),
            asset_root=manifest_path.parent,
            supplied_definitions=supplied,
        )
        check_snapshot(module, value)
    for module in ROOT.glob("**/*.pkl"):
        if "examples" not in module.relative_to(ROOT).parts and re.search(
            r"new\s+(?:RuleSets\.)?RuleInstance", module.read_text()
        ):
            fail(
                f"concrete rule instance outside examples/: {module.relative_to(ROOT)}"
            )
    evaluate_project(ROOT)
    print(f"validated {len(manifests)} example package(s) with Pkl {expected_version}")


if __name__ == "__main__":
    main()
