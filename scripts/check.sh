#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
export PATH="$HOME/.local/bin:$PATH"

# Re-resolve a copied project with an empty cache and require its generated lock
# to match the committed bytes. The validation checkout remains read-only.
python3 -c 'from pathlib import Path; from scripts.mcs_archive import _fresh_resolve_dependency_lock; _fresh_resolve_dependency_lock(Path.cwd())'

python3 -m unittest discover -s tests -v
python3 scripts/validate.py
pkl test \
  --root-dir "$repo_root" \
  --allowed-modules 'file:,pkl:,package:,projectpackage:' \
  --allowed-resources 'https://openbimrs\.github\.io/pkl/.*,https://github\.com/openbimrs/pkl/releases/download/.*,https://release-assets\.githubusercontent\.com/.*,prop:pkl.outputFormat' \
  --timeout 30 \
  tests/pkl/adapters.pkl \
  tests/pkl/expressions.pkl

# Exercise the distributable MCS transport without retaining binary artifacts.
mcs_tmp="$(mktemp -d)"
trap 'rm -rf "$mcs_tmp"' EXIT
python3 scripts/mcs.py pack examples/minimal "$mcs_tmp/one.mcs" --repository-root "$repo_root"
python3 scripts/mcs.py pack examples/minimal "$mcs_tmp/two.mcs" --repository-root "$repo_root"
cmp "$mcs_tmp/one.mcs" "$mcs_tmp/two.mcs"
sha256sum "$mcs_tmp/one.mcs" "$mcs_tmp/two.mcs"
python3 scripts/mcs.py verify "$mcs_tmp/one.mcs"
