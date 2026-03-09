# External Data Setup

This repository now treats large local datasets as external storage, not source-controlled assets.

## Goal

Keep these directories out of git:

- `Corpus`
- `acquittify-data`
- `Obsidian`
- `Acquittify Storage`
- `finetune`

## Option 1: Environment Variables (Recommended)

Set a single root:

```bash
export ACQUITTIFY_DATA_ROOT="$HOME/AcquittifyData"
```

Optional per-path overrides:

```bash
export ACQUITTIFY_CORPUS_ROOT="$ACQUITTIFY_DATA_ROOT/Corpus"
export CHROMA_DIR="$ACQUITTIFY_CORPUS_ROOT/Chroma"
export ACQUITTIFY_DATASET_DIR="$ACQUITTIFY_DATA_ROOT/acquittify-data"
export ACQUITTIFY_OBSIDIAN_ROOT="$ACQUITTIFY_DATA_ROOT/Obsidian"
export ACQUITTIFY_PRECEDENT_VAULT_ROOT="$ACQUITTIFY_OBSIDIAN_ROOT/Ontology/precedent_vault"
```

## Option 2: Symlink the Legacy Repo Paths

Run:

```bash
bash scripts/link_external_data_root.sh "$HOME/AcquittifyData"
```

The script moves legacy repo directories to the target root when safe, then creates symlinks back into the repo path.

## Notes For New Developers

- Do not commit corpus/raw data, model output, or dependency directories.
- Run `git status --short` before commits and verify no dataset/vendor paths are staged.
- Keep reproducible code/config in repo; keep mutable large data in external storage.
