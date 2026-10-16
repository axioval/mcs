# MCS container format

MCS version 0.1.0 is the deterministic transport container for an Axioval ruleset
or definitions package. It carries reviewable Pkl authoring source and the declarative normalized JSON
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

## Package kinds

The kind is the archived `axioval.json`'s; metadata keeps the same shape for
both kinds, and rule-set archives are written exactly as before.

- A `ruleset` package archive carries exactly one `normalized/ruleset.json` and
  one `normalized/definitions/*.json` per definition module.
- A `definitions` package archive carries only `normalized/definitions/*.json`
  and **no** `normalized/ruleset.json`. `verify` re-evaluates the definition
  modules only and binds them together.

`inspect` already refuses a definitions archive that carries a rule set, a
rule-set archive without one, and metadata whose package identity is not the
archived manifest's. It also requires, offline:

- the normalized mapping to cover exactly the archived manifest's entrypoints:
  a rule set's `entrypoint` maps to `normalized/ruleset.json` and every
  `definitionEntrypoints` module to a normalized definition document;
- the normalized rule set's package `id`, `version` and `schemaVersion` to be
  the metadata's, and its `definitionPackages` to declare every definition
  package the archive carries;
- every normalized definition document to have the metadata's
  `schemaVersion`, and, in a definitions archive, exactly one of them to carry
  the metadata's package identity.

## Supplied definitions packages

A rule set may declare a definition package it does not carry, such as an
installed template library. `pack` and `verify` then take the definitions
packages to resolve it from with `--definitions PATH`, repeatable:

??? example "Show commands for a rule set with an installed library"
    ```bash
    python3 scripts/mcs.py pack examples/template-library /tmp/library.mcs
    python3 scripts/mcs.py pack examples/installed-library /tmp/rules.mcs \
      --definitions /tmp/library.mcs
    python3 scripts/mcs.py verify /tmp/rules.mcs --definitions /tmp/library.mcs
    ```

A supplied `.mcs` archive is verified before use and refused unless it is a
definitions package; a supplied directory needs a definitions-kind
`axioval.json` and is evaluated and bound on its own. The resolution rules are
the [package contract's](package-contract.md#package-kinds). A supplied
package is never archived, so the rule set's archive bytes do not depend on
which form supplied it; without it, `pack` and `verify` fail closed and name
the unresolved ID, while `inspect` still checks the archive's structure.

!!! warning
    Run `verify` on an archive from an untrusted registry before installing
    it. `inspect` makes no claim about the source's evaluation or binding.

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
