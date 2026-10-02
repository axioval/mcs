#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

if __package__:
    from .contracts import (
        QUALIFIED_ID,
        SEMVER,
        bind_ruleset,
        validate_definition_document,
    )
else:
    from contracts import (
        QUALIFIED_ID,
        SEMVER,
        bind_ruleset,
        validate_definition_document,
    )

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "manifestVersion",
    "kind",
    "id",
    "version",
    "schemaVersion",
    "entrypoint",
    "definitionEntrypoints",
}
ALLOWED = REQUIRED | {"$schema", "description", "license"}
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
    missing = REQUIRED - manifest.keys()
    unknown = manifest.keys() - ALLOWED
    if missing or unknown:
        fail(f"{path}: missing={sorted(missing)}, unknown={sorted(unknown)}")
    scalar_fields = REQUIRED - {"definitionEntrypoints"}
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
    if not PKL_ENTRYPOINT.fullmatch(manifest["entrypoint"]) or any(
        not PKL_ENTRYPOINT.fullmatch(entry) for entry in entries
    ):
        fail(f"{path}: entrypoints must be safe repository-relative .pkl paths")
    if (
        manifest["manifestVersion"] != "0.1.0"
        or manifest["schemaVersion"] != "0.1.0"
        or manifest["kind"] != "ruleset"
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


def main() -> None:
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
        module = local_module(manifest_path.parent, manifest["entrypoint"])
        definition_modules = [
            local_module(manifest_path.parent, entry)
            for entry in manifest["definitionEntrypoints"]
        ]
        validated_manifests.append(
            (manifest_path, manifest, module, definition_modules)
        )

    for manifest_path, manifest, module, definition_modules in validated_manifests:
        value = evaluate(module)
        package = value.get("package", {})
        if (
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
        bind_ruleset(
            value,
            definition_values,
            str(module.relative_to(ROOT)),
            asset_root=manifest_path.parent,
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
