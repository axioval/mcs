"""Fail-closed v0.1 reader and writer for Axioval MCS containers.

MCS is a deterministic ZIP transport for reviewed Pkl sources plus declarative
normalized JSON.  The mimetype member has no trailing newline.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import struct

# The executable below is resolved with shutil.which, not archive input.
import subprocess  # nosec B404
import tempfile
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

try:
    from . import validate
    from .contracts import (
        QUALIFIED_ID,
        SEMVER,
        bind_ruleset,
        validate_definition_document,
    )
except ImportError:  # direct CLI execution
    import validate
    from contracts import (
        QUALIFIED_ID,
        SEMVER,
        bind_ruleset,
        validate_definition_document,
    )

MIMETYPE = b"application/vnd.axioval.mcs+zip"
FORMAT = "axioval.mcs"
VERSION = "0.1.0"
METADATA = "META-INF/mcs.json"
TIMESTAMP = (1980, 1, 1, 0, 0, 0)
MAX_ENTRIES = 512
# Existing explanatory-image contract permits exactly 10,000,000 bytes.
MAX_FILE = 10_000_000
MAX_TOTAL = 64 * 1024 * 1024
MAX_COMPRESSED = 64 * 1024 * 1024
MAX_RATIO = 100
MAX_METADATA = 256 * 1024
NAME_MAX = 240
SHA256 = re.compile(r"[0-9a-f]{64}")
PACKAGE_URI = re.compile(
    r"package://(?P<path>[^@\s]+)@(?P<major>0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
)
PACKAGE_LOCK_KEY = re.compile(r"package://[^@\s]+@(0|[1-9][0-9]*)")
DIRECTIVE = re.compile(r"^\s*(import\*?|amends|extends)\b(.*)$")
LITERAL_DIRECTIVE = re.compile(
    r'^\s*(import|amends|extends)\s+"([^"\\]+)"(?:\s+as\s+[A-Za-z_][A-Za-z0-9_]*)?\s*(?://.*)?$'
)
RESOURCE_READ = re.compile(r"(?<![A-Za-z0-9_])read(?:\?|\*|Glob)?(?![A-Za-z0-9_])")


class MCSError(ValueError):
    pass


def _fail(message: str) -> None:
    raise MCSError(message)


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _strict_json(data: bytes, context: str) -> Any:
    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail(f"{context}: duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail(f"{context}: invalid JSON: {exc}")


def _expected_lock_binding(uri: str) -> tuple[str, str]:
    match = PACKAGE_URI.fullmatch(uri)
    if match is None:
        _fail(f"Pkl dependency must use an exact package version: {uri!r}")
    path = match.group("path")
    major = match.group("major")
    return f"package://{path}@{major}", "project" + uri


def _validate_lock_entry(key: str, entry: Any) -> None:
    if (
        type(key) is not str
        or PACKAGE_LOCK_KEY.fullmatch(key) is None
        or type(entry) is not dict
        or set(entry) != {"type", "uri", "checksums"}
        or entry.get("type") != "remote"
        or type(entry.get("uri")) is not str
        or not entry["uri"].startswith("projectpackage://")
        or PACKAGE_URI.fullmatch(entry["uri"].removeprefix("project")) is None
    ):
        _fail(f"invalid Pkl lock entry: {key!r}")
    checksums = entry["checksums"]
    if (
        type(checksums) is not dict
        or set(checksums) != {"sha256"}
        or type(checksums.get("sha256")) is not str
        or SHA256.fullmatch(checksums["sha256"]) is None
    ):
        _fail(f"invalid Pkl lock checksum: {key!r}")


def _validate_dependency_lock(root: Path, dependencies: dict[str, str]) -> set[str]:
    if not dependencies:
        return set()
    lock_file = _inside(root, root / "PklProject.deps.json", "Pkl dependency lock")
    lock = _strict_json(lock_file.read_bytes(), str(lock_file))
    if (
        type(lock) is not dict
        or set(lock) != {"schemaVersion", "resolvedDependencies"}
        or lock.get("schemaVersion") != 1
    ):
        _fail("invalid Pkl dependency lock envelope")
    resolved = lock["resolvedDependencies"]
    if type(resolved) is not dict:
        _fail("invalid Pkl resolvedDependencies")
    for key, entry in resolved.items():
        _validate_lock_entry(key, entry)
    for alias, uri in dependencies.items():
        key, resolved_uri = _expected_lock_binding(uri)
        entry = resolved.get(key)
        if entry is None or entry["uri"] != resolved_uri:
            _fail(f"Pkl dependency lock does not bind alias {alias!r}")
    return set(dependencies)


def _project_dependencies(root: Path) -> dict[str, str]:
    project = _inside(root, root / "PklProject", "Pkl project")
    command = [
        validate.pkl_executable(),
        "eval",
        "-f",
        "json",
        "--root-dir",
        str(root),
        "--allowed-modules",
        "file:,pkl:",
        "--allowed-resources",
        "prop:pkl.outputFormat",
        "--timeout",
        "10",
        str(project),
    ]
    result = subprocess.run(
        command, cwd=root, text=False, capture_output=True, check=False
    )  # nosec B603
    if result.returncode:
        _fail(
            "cannot evaluate PklProject: "
            + result.stderr.decode(errors="replace").strip()
        )
    value = _strict_json(result.stdout, "PklProject evaluation")
    raw = value.get("dependencies") if type(value) is dict else None
    if type(raw) is not dict:
        _fail("PklProject dependencies must be an object")
    dependencies: dict[str, str] = {}
    for alias, item in raw.items():
        if (
            type(alias) is not str
            or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", alias) is None
        ):
            _fail(f"invalid Pkl dependency alias: {alias!r}")
        if (
            type(item) is not dict
            or set(item) != {"uri"}
            or type(item.get("uri")) is not str
        ):
            _fail(f"invalid Pkl dependency declaration: {alias!r}")
        _expected_lock_binding(item["uri"])
        dependencies[alias] = item["uri"]
    return dependencies


def _fresh_resolve_dependency_lock(root: Path) -> None:
    lock = _inside(root, root / "PklProject.deps.json", "Pkl dependency lock")
    expected = lock.read_bytes()
    with tempfile.TemporaryDirectory(prefix="mcs-pkl-lock-") as temporary:
        project_root = Path(temporary) / "project"
        project_root.mkdir()
        shutil.copy2(root / "PklProject", project_root / "PklProject")
        shutil.copy2(lock, project_root / "PklProject.deps.json")
        command = [
            validate.pkl_executable(),
            "project",
            "resolve",
            "--cache-dir",
            str(Path(temporary) / "cache"),
            "--root-dir",
            str(project_root),
            "--allowed-modules",
            "file:,pkl:,package:,projectpackage:",
            "--allowed-resources",
            validate.PKL_PACKAGE_RESOURCE_ALLOWLIST,
            "--timeout",
            "30",
            ".",
        ]
        result = subprocess.run(
            command, cwd=project_root, text=True, capture_output=True, check=False
        )  # nosec B603
        if result.returncode:
            _fail(
                "fresh Pkl dependency resolution failed: "
                + (result.stderr or result.stdout).strip()
            )
        if (project_root / "PklProject.deps.json").read_bytes() != expected:
            _fail("Pkl dependency lock is stale or does not match PklProject")


def _safe_name(name: str) -> None:
    path = PurePosixPath(name)
    if (
        not name
        or len(name) > NAME_MAX
        or "\\" in name
        or "\x00" in name
        or any(ord(c) < 32 for c in name)
        or name != unicodedata.normalize("NFC", name)
        or name != path.as_posix()
        or path.is_absolute()
        or any(p in {"", ".", ".."} for p in path.parts)
    ):
        _fail(f"unsafe member name {name!r}")


def _inside(root: Path, path: Path, context: str) -> Path:
    root = root.resolve()
    try:
        relative = Path(os.path.normpath(path.absolute())).relative_to(root)
    except ValueError:
        _fail(f"{context}: missing or escaping file: {path}")
    cursor = root
    for component in relative.parts:
        cursor /= component
        if cursor.is_symlink():
            _fail(f"{context}: symlinks are forbidden: {cursor}")
    resolved = path.resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        _fail(f"{context}: missing or escaping file: {path}")
    return resolved


def _directory_inside(root: Path, path: Path, context: str) -> Path:
    root = root.resolve()
    try:
        relative = Path(os.path.normpath(path.absolute())).relative_to(root)
    except ValueError:
        _fail(f"{context}: missing or escaping directory: {path}")
    cursor = root
    for component in relative.parts:
        cursor /= component
        if cursor.is_symlink():
            _fail(f"{context}: symlinks are forbidden: {cursor}")
    resolved = path.resolve()
    if not resolved.is_relative_to(root) or not resolved.is_dir():
        _fail(f"{context}: missing or escaping directory: {path}")
    return resolved


def _source_name(root: Path, file: Path) -> str:
    return "source/" + file.resolve().relative_to(root.resolve()).as_posix()


def _pkl_closure(
    root: Path, starts: list[Path], declared_aliases: set[str] | None = None
) -> set[Path]:
    declared_aliases = declared_aliases or set()
    pending, found = list(starts), set()
    while pending:
        current = _inside(root, pending.pop(), "Pkl dependency")
        if current in found:
            continue
        found.add(current)
        try:
            text = current.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            _fail(f"Pkl dependency is not UTF-8: {current}: {exc}")
        if RESOURCE_READ.search(text):
            _fail(f"Pkl resource reads are not supported: {current.relative_to(root)}")
        for line_number, line in enumerate(text.splitlines(), 1):
            directive = DIRECTIVE.match(line)
            if not directive:
                continue
            literal = LITERAL_DIRECTIVE.fullmatch(line)
            if not literal:
                _fail(
                    f"{current.relative_to(root)}:{line_number}: unsupported Pkl dependency directive"
                )
            target = literal.group(2)
            # pkl: is a standard module and deliberately not archived.
            if target.startswith("pkl:"):
                continue
            # Declared project dependencies are checksum-locked in the archived
            # PklProject.deps.json and remain external to the source closure.
            if target.startswith("@"):
                parts = PurePosixPath(target).parts
                if (
                    len(parts) < 2
                    or re.fullmatch(r"@[A-Za-z_][A-Za-z0-9_-]*", parts[0]) is None
                    or any(
                        part in {"", ".", ".."}
                        or re.fullmatch(r"[A-Za-z0-9_.-]+", part) is None
                        for part in parts[1:]
                    )
                ):
                    _fail(f"unsafe Pkl package reference {target!r} in {current}")
                alias = parts[0][1:]
                if alias not in declared_aliases:
                    _fail(f"undeclared Pkl package alias {alias!r} in {current}")
                continue
            if ":" in target or target.startswith("/") or "\\" in target:
                _fail(
                    f"unsupported external/dynamic Pkl reference {target!r} in {current}"
                )
            candidate = current.parent / target
            if candidate.suffix != ".pkl":
                _fail(
                    f"unsupported non-Pkl local module reference {target!r} in {current}"
                )
            pending.append(_inside(root, candidate, "Pkl dependency"))
    return found


def _support_files(root: Path, package: Path, require_lock: bool = False) -> set[Path]:
    files = {
        _inside(root, root / "PklProject", "Pkl project"),
        _inside(root, root / ".pkl-version", "Pkl version"),
    }
    lock = root / "PklProject.deps.json"
    if lock.exists() or lock.is_symlink():
        files.add(_inside(root, lock, "Pkl dependency lock"))
    elif require_lock:
        _fail("PklProject.deps.json is required for declared package dependencies")
    licenses = sorted(path for path in root.glob("LICENSE*") if path.is_file())
    if not licenses:
        _fail("repository root must contain license text")
    files.update(_inside(root, path, "repository license") for path in licenses)
    for pattern in ("README*", "LICENSE*", "NOTICE*"):
        files.update(
            _inside(root, path, "package documentation")
            for path in sorted(package.glob(pattern))
            if path.is_file() or path.is_symlink()
        )
    return files


def _asset_paths(value: Any, package_root: Path, root: Path) -> set[Path]:
    found: set[Path] = set()
    if isinstance(value, dict):
        # Explanatory images and the data files table values name.
        if (
            set(value) >= {"path", "mediaType"} or value.get("type") == "tableFile"
        ) and isinstance(value.get("path"), str):
            candidate = package_root / value["path"]
            found.add(_inside(package_root, candidate, "asset"))
        for item in value.values():
            found |= _asset_paths(item, package_root, root)
    elif isinstance(value, list):
        for item in value:
            found |= _asset_paths(item, package_root, root)
    return found


def _pkl_version(root: Path) -> str:
    version = (
        _inside(root, root / ".pkl-version", "Pkl version")
        .read_text(encoding="utf-8")
        .strip()
    )
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        _fail("invalid .pkl-version")
    return version


def _check_pkl_version(expected: str) -> None:
    executable = shutil.which("pkl")
    if executable is None:
        _fail("pkl is not installed or not on PATH")
    # The command is a constant option vector and the executable came from PATH lookup.
    result = subprocess.run(  # nosec B603
        [executable, "--version"], text=True, capture_output=True, check=False
    )
    if result.returncode or not result.stdout.startswith(f"Pkl {expected} "):
        _fail(
            f"expected Pkl {expected}, got {result.stdout.strip() or result.stderr.strip()}"
        )


def _zipinfo(name: str, compression: int = zipfile.ZIP_DEFLATED) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=TIMESTAMP)
    info.compress_type = compression
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    info.flag_bits = 0
    return info


def pack(
    package_dir: Path, output: Path, repository_root: Path, force: bool = False
) -> dict[str, Any]:
    if output.suffix != ".mcs":
        _fail("output must use the .mcs extension")
    if output.exists() and not force:
        _fail("refusing to overwrite existing output; use --force")
    root = repository_root.resolve()
    package = _directory_inside(root, package_dir, "package directory")
    manifest_file = _inside(root, package / "axioval.json", "manifest")
    manifest = _strict_json(manifest_file.read_bytes(), str(manifest_file))
    try:
        manifest = validate.validate_manifest(manifest, manifest_file)
        ruleset_module = validate.local_module(package, manifest["entrypoint"])
        definition_modules = [
            validate.local_module(package, item)
            for item in manifest["definitionEntrypoints"]
        ]
    except SystemExit as exc:
        _fail(str(exc))
    _check_pkl_version(_pkl_version(root))
    dependencies = _project_dependencies(root)
    declared_aliases = _validate_dependency_lock(root, dependencies)
    if dependencies:
        _fresh_resolve_dependency_lock(root)
    closure = _pkl_closure(
        root, [ruleset_module, *definition_modules], declared_aliases
    )
    # The manifest schema is a source dependency even when its declared path changes.
    schema_value = manifest.get("$schema")
    if not isinstance(schema_value, str) or ":" in schema_value:
        _fail("manifest must declare a local JSON-schema target")
    schema_file = _inside(root, package / schema_value, "manifest schema")
    if schema_file.suffix != ".json":
        _fail("manifest schema target must be JSON")
    ruleset = validate.evaluate(ruleset_module, root)
    definitions = [validate.evaluate(module, root) for module in definition_modules]
    if (
        ruleset.get("schemaVersion") != manifest["schemaVersion"]
        or ruleset.get("package", {}).get("id") != manifest["id"]
        or ruleset.get("package", {}).get("version") != manifest["version"]
    ):
        _fail("manifest and evaluated ruleset identity disagree")
    try:
        for module, value in zip(definition_modules, definitions, strict=True):
            if value.get("schemaVersion") != manifest["schemaVersion"]:
                _fail(f"definition schema version disagrees: {module}")
            validate_definition_document(
                value, str(module.relative_to(root)), asset_root=package
            )
        bind_ruleset(
            ruleset,
            definitions,
            str(ruleset_module.relative_to(root)),
            asset_root=package,
        )
    except SystemExit as exc:
        _fail(str(exc))
    assets = _asset_paths([ruleset, *definitions], package, root)
    source_files = (
        closure
        | {manifest_file, schema_file}
        | assets
        | _support_files(root, package, require_lock=bool(dependencies))
    )
    members: dict[str, tuple[bytes, str]] = {}
    for file in source_files:
        members[_source_name(root, file)] = (file.read_bytes(), "source")
    ruleset_name = "normalized/ruleset.json"
    members[ruleset_name] = (_json_bytes(ruleset), "ruleset")
    mappings: dict[str, str] = {manifest["entrypoint"]: ruleset_name}
    for module, value in zip(definition_modules, definitions, strict=True):
        name = (
            "normalized/definitions/"
            + hashlib.sha256(
                module.relative_to(package).as_posix().encode()
            ).hexdigest()[:16]
            + ".json"
        )
        members[name] = (_json_bytes(value), "definition")
        mappings[module.relative_to(package).as_posix()] = name
    inventory = [
        {
            "path": name,
            "role": role,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        for name, (data, role) in sorted(members.items())
    ]
    metadata = {
        "format": FORMAT,
        "formatVersion": VERSION,
        "mediaType": MIMETYPE.decode(),
        "sourceRoot": "source",
        "packageRoot": _source_name(root, package),
        "manifest": _source_name(root, manifest_file),
        "pklVersion": _pkl_version(root),
        "package": {
            "id": manifest["id"],
            "version": manifest["version"],
            "schemaVersion": manifest["schemaVersion"],
        },
        "normalized": mappings,
        "inventory": inventory,
    }
    meta_bytes = _json_bytes(metadata)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.is_symlink():
        _fail("refusing to replace a symlink output")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(
            temporary,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
            allowZip64=False,
        ) as archive:
            archive.writestr(_zipinfo("mimetype", zipfile.ZIP_STORED), MIMETYPE)
            archive.writestr(_zipinfo(METADATA), meta_bytes)
            for name, (data, _) in sorted(members.items()):
                archive.writestr(_zipinfo(name), data)
        os.chmod(temporary, 0o644)
        if force:
            os.replace(temporary, output)
        else:
            try:
                os.link(temporary, output)
            except FileExistsError:
                _fail("refusing to overwrite existing output; use --force")
            temporary.unlink()
    finally:
        temporary.unlink(missing_ok=True)
    return metadata


def _metadata(value: Any) -> dict[str, Any]:
    if type(value) is not dict:
        _fail("metadata must be an object")
    required = {
        "format",
        "formatVersion",
        "mediaType",
        "sourceRoot",
        "packageRoot",
        "manifest",
        "pklVersion",
        "package",
        "normalized",
        "inventory",
    }
    if set(value) != required:
        _fail("metadata has missing or unknown keys")
    if (
        value["format"] != FORMAT
        or value["formatVersion"] != VERSION
        or value["mediaType"] != MIMETYPE.decode()
        or value["sourceRoot"] != "source"
    ):
        _fail("invalid metadata constants")
    package_root = value["packageRoot"]
    manifest_path = value["manifest"]
    if (
        type(package_root) is not str
        or package_root == "source"
        or not package_root.startswith("source/")
        or package_root.endswith("/")
    ):
        _fail("invalid metadata packageRoot")
    _safe_name(package_root)
    if (
        type(manifest_path) is not str
        or manifest_path != package_root + "/axioval.json"
    ):
        _fail("invalid metadata manifest")
    _safe_name(manifest_path)
    if type(value["pklVersion"]) is not str or not re.fullmatch(
        r"[0-9]+\.[0-9]+\.[0-9]+", value["pklVersion"]
    ):
        _fail("invalid metadata pklVersion")
    package = value["package"]
    if (
        type(package) is not dict
        or set(package) != {"id", "version", "schemaVersion"}
        or any(type(package[k]) is not str for k in package)
        or not QUALIFIED_ID.fullmatch(package["id"])
        or not SEMVER.fullmatch(package["version"])
        or not SEMVER.fullmatch(package["schemaVersion"])
    ):
        _fail("invalid metadata package")
    if type(value["normalized"]) is not dict or type(value["inventory"]) is not list:
        _fail("invalid metadata normalized/inventory")
    return value


def _validate_zip_structure(raw: bytes, infos: list[zipfile.ZipInfo]) -> None:
    if len(raw) < 22:
        _fail("truncated ZIP archive")
    eocd_offset = len(raw) - 22
    eocd = struct.unpack_from("<4s4H2LH", raw, eocd_offset)
    (
        signature,
        disk,
        central_disk,
        disk_entries,
        total_entries,
        size,
        offset,
        comment,
    ) = eocd
    if (
        signature != b"PK\x05\x06"
        or disk != 0
        or central_disk != 0
        or disk_entries != len(infos)
        or total_entries != len(infos)
        or comment != 0
        or offset in {0xFFFFFFFF}
        or size in {0xFFFFFFFF}
        or offset + size != eocd_offset
        or size
        != sum(
            46
            + len(info.filename.encode("utf-8" if info.flag_bits & 0x800 else "cp437"))
            for info in infos
        )
    ):
        _fail("non-canonical ZIP end record or trailing data")
    if infos != sorted(infos, key=lambda info: info.header_offset):
        _fail("central and local member order disagree")
    cursor = 0
    for info in infos:
        if info.header_offset != cursor or cursor + 30 > offset:
            _fail("ZIP contains a preamble, gap, or overlapping local member")
        local = struct.unpack_from("<4s5H3L2H", raw, cursor)
        (
            local_signature,
            needed,
            flags,
            compression,
            _time,
            _date,
            crc,
            compressed,
            uncompressed,
            name_length,
            extra_length,
        ) = local
        name_start = cursor + 30
        data_start = name_start + name_length + extra_length
        expected_name = info.filename.encode("utf-8" if flags & 0x800 else "cp437")
        if (
            local_signature != b"PK\x03\x04"
            or needed != 20
            or flags != info.flag_bits
            or compression != info.compress_type
            or _time != 0
            or _date != 33
            or crc != info.CRC
            or compressed != info.compress_size
            or uncompressed != info.file_size
            or extra_length != 0
            or raw[name_start : name_start + name_length] != expected_name
        ):
            _fail("non-canonical ZIP local header")
        cursor = data_start + info.compress_size
    if cursor != offset:
        _fail("ZIP contains data outside declared local members")
    central_cursor = offset
    for info in infos:
        central = struct.unpack_from("<4s6H3L5H2L", raw, central_cursor)
        (
            central_signature,
            made_by,
            needed,
            flags,
            compression,
            timestamp,
            datestamp,
            crc,
            compressed,
            uncompressed,
            name_length,
            extra_length,
            comment_length,
            disk_start,
            internal_attributes,
            external_attributes,
            local_offset,
        ) = central
        name_start = central_cursor + 46
        expected_name = info.filename.encode("utf-8" if flags & 0x800 else "cp437")
        if (
            central_signature != b"PK\x01\x02"
            or made_by != (3 << 8) | 20
            or needed != 20
            or flags != info.flag_bits
            or compression != info.compress_type
            or timestamp != 0
            or datestamp != 33
            or crc != info.CRC
            or compressed != info.compress_size
            or uncompressed != info.file_size
            or extra_length != 0
            or comment_length != 0
            or disk_start != 0
            or internal_attributes != 0
            or external_attributes != (stat.S_IFREG | 0o644) << 16
            or local_offset != info.header_offset
            or raw[name_start : name_start + name_length] != expected_name
        ):
            _fail("non-canonical ZIP central header")
        central_cursor = name_start + name_length
    if central_cursor != eocd_offset:
        _fail("ZIP central directory contains undeclared data")


def _read_verified(path: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    if (
        path.suffix != ".mcs"
        or not path.is_file()
        or path.is_symlink()
        or path.stat().st_size > MAX_COMPRESSED
    ):
        _fail("archive must be a bounded regular .mcs file")
    raw = path.read_bytes()
    try:
        with zipfile.ZipFile(path) as archive:
            if archive.comment:
                _fail("archive comments are forbidden")
            infos = archive.infolist()
            if not 3 <= len(infos) <= MAX_ENTRIES:
                _fail("invalid archive entry count")
            _validate_zip_structure(raw, infos)
            names: set[str] = set()
            folded: set[str] = set()
            total = compressed = 0
            for index, info in enumerate(infos):
                _safe_name(info.filename)
                nfc = unicodedata.normalize("NFC", info.filename)
                if info.filename in names or nfc.casefold() in folded:
                    _fail("duplicate or casefold-colliding member")
                names.add(info.filename)
                folded.add(nfc.casefold())
                expected_flags = 0x800 if not info.filename.isascii() else 0
                expected_compression = (
                    zipfile.ZIP_STORED if index == 0 else zipfile.ZIP_DEFLATED
                )
                if (
                    info.is_dir()
                    or info.compress_type != expected_compression
                    or info.flag_bits != expected_flags
                    or info.create_system != 3
                    or info.create_version != 20
                    or info.extract_version != 20
                    or info.external_attr != (stat.S_IFREG | 0o644) << 16
                    or info.internal_attr != 0
                    or bool(info.extra)
                    or bool(info.comment)
                ):
                    _fail("non-canonical or unsupported ZIP member metadata")
                if info.file_size > MAX_FILE or info.compress_size > MAX_FILE:
                    _fail("archive member exceeds size limit")
                if (
                    info.compress_size
                    and info.file_size / info.compress_size > MAX_RATIO
                ):
                    _fail("archive compression ratio exceeds limit")
                total += info.file_size
                compressed += info.compress_size
                if total > MAX_TOTAL or compressed > MAX_COMPRESSED:
                    _fail("archive total exceeds limit")
                if info.date_time != TIMESTAMP or info.create_system != 3:
                    _fail("non-deterministic ZIP metadata")
                if index == 0 and (
                    info.filename != "mimetype"
                    or info.compress_type != zipfile.ZIP_STORED
                ):
                    _fail("mimetype must be first and stored")
                if index == 1 and (
                    info.filename != METADATA or info.file_size > MAX_METADATA
                ):
                    _fail("metadata must be second and bounded")
            data = {info.filename: archive.read(info) for info in infos}
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        _fail(f"invalid ZIP archive: {exc}")
    if data["mimetype"] != MIMETYPE:
        _fail("invalid mimetype payload")
    metadata = _metadata(_strict_json(data[METADATA], METADATA))
    declared: dict[str, dict[str, Any]] = {}
    for entry in metadata["inventory"]:
        if type(entry) is not dict or set(entry) != {"path", "role", "size", "sha256"}:
            _fail("invalid inventory entry")
        name, role = entry["path"], entry["role"]
        if (
            type(name) is not str
            or type(role) is not str
            or role not in {"source", "ruleset", "definition"}
            or type(entry["size"]) is not int
            or entry["size"] < 0
            or entry["size"] > MAX_FILE
            or type(entry["sha256"]) is not str
            or not SHA256.fullmatch(entry["sha256"])
        ):
            _fail("invalid inventory types")
        _safe_name(name)
        expected_role = (
            "source"
            if name.startswith("source/")
            else (
                "ruleset"
                if name == "normalized/ruleset.json"
                else (
                    "definition"
                    if re.fullmatch(r"normalized/definitions/[0-9a-f]{16}\.json", name)
                    else None
                )
            )
        )
        if expected_role != role:
            _fail("invalid inventory member topology or role")
        if name in declared or name not in data or name in {"mimetype", METADATA}:
            _fail("missing, duplicate, or reserved inventory member")
        if (
            len(data[name]) != entry["size"]
            or hashlib.sha256(data[name]).hexdigest() != entry["sha256"]
        ):
            _fail("inventory size/hash mismatch")
        declared[name] = entry
    if list(declared) != sorted(declared):
        _fail("inventory must be sorted by path")
    if set(data) != {"mimetype", METADATA, *declared}:
        _fail("archive contains undeclared or missing payload")
    package_root = metadata["packageRoot"]
    manifest = metadata["manifest"]
    if (
        not manifest.startswith(package_root + "/")
        or manifest != package_root + "/axioval.json"
        or manifest not in declared
        or declared[manifest]["role"] != "source"
        or "source/.pkl-version" not in declared
        or declared["source/.pkl-version"]["role"] != "source"
        or "source/PklProject" not in declared
        or declared["source/PklProject"]["role"] != "source"
        or not any(
            name.startswith("source/LICENSE")
            and "/" not in name.removeprefix("source/")
            and entry["role"] == "source"
            for name, entry in declared.items()
        )
    ):
        _fail("invalid source package topology")
    mapping = metadata["normalized"]
    normalized_names = {name for name in declared if name.startswith("normalized/")}
    mapped_names: set[str] = set()
    ruleset_mappings = 0
    for module, normalized in mapping.items():
        if (
            type(module) is not str
            or type(normalized) is not str
            or not module.endswith(".pkl")
        ):
            _fail("invalid normalized mapping")
        _safe_name(module)
        source_module = package_root + "/" + module
        if (
            source_module not in declared
            or declared[source_module]["role"] != "source"
            or normalized not in declared
            or normalized in mapped_names
        ):
            _fail("missing or duplicate normalized mapping")
        mapped_names.add(normalized)
        role = declared[normalized]["role"]
        if role == "ruleset":
            if normalized != "normalized/ruleset.json":
                _fail("invalid normalized ruleset path")
            ruleset_mappings += 1
        elif role != "definition":
            _fail("normalized mapping points to a non-normalized role")
    if list(mapping) != sorted(mapping):
        _fail("normalized mapping must be sorted by source module")
    if mapped_names != normalized_names or ruleset_mappings != 1:
        _fail("incomplete normalized mapping")
    return metadata, data


def inspect(path: Path) -> dict[str, Any]:
    metadata, _ = _read_verified(path)
    return metadata


def verify(path: Path) -> dict[str, Any]:
    metadata, data = _read_verified(path)
    _check_pkl_version(metadata["pklVersion"])
    with tempfile.TemporaryDirectory(prefix="axioval-mcs-", dir=path.parent) as temp:
        root = Path(temp)
        for entry in metadata["inventory"]:
            target = root / entry["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output:
                output.write(data[entry["path"]])
        source_root = root / "source"
        if (source_root / ".pkl-version").read_text().strip() != metadata["pklVersion"]:
            _fail("source .pkl-version disagrees with metadata")
        dependencies = _project_dependencies(source_root)
        declared_aliases = _validate_dependency_lock(source_root, dependencies)
        manifest_path = root / metadata["manifest"]
        manifest = _strict_json(manifest_path.read_bytes(), "manifest")
        try:
            manifest = validate.validate_manifest(manifest, manifest_path)
            package_root = root / metadata["packageRoot"]
            ruleset_module = validate.local_module(package_root, manifest["entrypoint"])
            defs = [
                validate.local_module(package_root, x)
                for x in manifest["definitionEntrypoints"]
            ]
            declared_modules = {
                manifest["entrypoint"],
                *manifest["definitionEntrypoints"],
            }
            if set(metadata["normalized"]) != declared_modules:
                _fail("normalized mapping disagrees with manifest entrypoints")
            schema_reference = manifest.get("$schema")
            if (
                type(schema_reference) is not str
                or ":" in schema_reference
                or schema_reference.startswith(("/", "\\"))
            ):
                _fail("manifest schema must be a relative archive member")
            schema_file = _inside(
                source_root,
                manifest_path.parent / schema_reference,
                "manifest schema",
            )
            ruleset = validate.evaluate(ruleset_module, source_root)
            definition_values = [validate.evaluate(x, source_root) for x in defs]
            if (
                ruleset.get("package", {}).get("id") != metadata["package"]["id"]
                or ruleset.get("package", {}).get("version")
                != metadata["package"]["version"]
                or ruleset.get("schemaVersion") != metadata["package"]["schemaVersion"]
            ):
                _fail("evaluated package identity disagrees with metadata")
            mapping = metadata["normalized"]
            if mapping.get(manifest["entrypoint"]) != "normalized/ruleset.json":
                _fail("invalid normalized ruleset mapping")
            if _json_bytes(ruleset) != data["normalized/ruleset.json"]:
                _fail("normalized ruleset does not exactly match evaluated source")
            for module, value in zip(defs, definition_values, strict=True):
                mapped = mapping.get(module.relative_to(package_root).as_posix())
                if (
                    not isinstance(mapped, str)
                    or mapped not in data
                    or _json_bytes(value) != data[mapped]
                ):
                    _fail(
                        "normalized definition does not exactly match evaluated source"
                    )
                validate_definition_document(
                    value,
                    str(module.relative_to(source_root)),
                    asset_root=package_root,
                )
            bind_ruleset(
                ruleset,
                definition_values,
                str(ruleset_module.relative_to(source_root)),
                asset_root=package_root,
            )
            expected_source_files = (
                _pkl_closure(source_root, [ruleset_module, *defs], declared_aliases)
                | {manifest_path, schema_file}
                | _asset_paths(
                    [ruleset, *definition_values], package_root, source_root
                )
                | _support_files(
                    source_root, package_root, require_lock=bool(dependencies)
                )
            )
            expected_source_names = {
                _source_name(source_root, file) for file in expected_source_files
            }
            declared_source_names = {
                entry["path"]
                for entry in metadata["inventory"]
                if entry["role"] == "source"
            }
            if declared_source_names != expected_source_names:
                _fail(
                    "archive source payload is not the exact declared dependency closure"
                )
        except SystemExit as exc:
            _fail(str(exc))
    return metadata
