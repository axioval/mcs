# MCS container format

MCS version 0.1.0 is the deterministic transport container for an Axioval ruleset.
It carries reviewable Pkl authoring source and the declarative normalized JSON
that model-checking applications consume. It is not an executable plugin format.

## Commands

??? example "Show MCS commands"
    ```bash
    python3 scripts/mcs.py pack examples/minimal /tmp/minimal.mcs --repository-root .
    python3 scripts/mcs.py inspect /tmp/minimal.mcs
    python3 scripts/mcs.py verify /tmp/minimal.mcs
    ```

`pack` refuses a non-`.mcs` output name and an existing output unless `--force`
is supplied. `inspect` checks only the structure, metadata, inventory, and
embedded hashes; it does not authenticate a publisher. `verify` is
certification: it also safely materializes verified files,
evaluates Pkl in the existing sandbox, compares normalized JSON byte for byte,
and binds definitions and ruleset with their package assets.

## Byte contract

An MCS file is a ZIP archive with no archive comment. Its first local member is
exactly `mimetype`, stored rather than compressed, whose exact ASCII bytes are
`application/vnd.axioval.mcs+zip`. There is **no trailing newline**. The second
member is `META-INF/mcs.json`. Writers use a fixed timestamp, permissions,
platform, flags, compression level, canonical JSON, and sorted remaining names;
packing the same repository state twice produces identical bytes.

Metadata declares `sourceRoot`, `packageRoot`, the manifest path, the pinned Pkl
version, package identity, normalized source-module mapping, and a SHA-256/size/
role inventory for every payload. Source topology remains repository-relative
under `source/`; imports are never rewritten. Standard `pkl:` modules are not
archived.

## Acceptance boundary

Readers reject malformed or ambiguous ZIP structure before writing any file:
unsafe names, duplicates and Unicode/case collisions, links or special modes,
unsupported compression, encryption, data descriptors, oversized or high-ratio
members, unexpected payloads, and malformed metadata all fail closed. Files are
written directly into a bounded temporary directory, never through ZIP extraction
helpers. Version 0.1.0 permits at most 512 members, 10,000,000 bytes per
member, 64 MiB total compressed and uncompressed payload, 256 KiB metadata, and
a 100:1 per-member expansion ratio. `mimetype` uses `ZIP_STORED`; every other
member uses raw DEFLATE at level 9.

Packing includes the manifest, root `PklProject`, `.pkl-version`, and the
required `PklProject.deps.json` when the project declares package dependencies,
at least one direct root `LICENSE*` file, and the exact local
Pkl import/`amends`/`extends` closure, relative manifest schema, declared assets
(explanatory images and the table files of ruleset and definitions),
and direct package `README*`/`LICENSE*`/`NOTICE*` files. Dependency directives
must use one ordinary quoted literal on one line. Dynamic, globbed, custom-string,
external, escaping, or symlinked dependencies and all Pkl resource-read calls
(`read`, `read?`, `read*`, and `readGlob`) are rejected. A matching normalized
payload cannot bypass source evaluation, exact-closure checking, and binding.

A package import remains external only when its `@alias` exists in `PklProject`
and the lock binds that alias's exact `package:` URI to a checksum-bearing
`projectpackage:` entry. Packing resolves the copied project with an empty cache
and rejects missing, stale, or remotely invalid checksums. Full verification
repeats source evaluation and may access checksum-pinned package metadata and
release-asset endpoints because Pkl validates package resources during import.
It also proves that the archived project and lock are structurally bound and that
their exact bytes match the signed inventory. `inspect` remains the offline-only
structural operation and makes no remote-package reauthentication claim.
