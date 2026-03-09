# Peregrine (Local-Only)

Peregrine is a local-only agent that searches and answers questions over the Obsidian vault using an internal Ollama model. It does not require internet access once the models are present.

## Requirements

- Ollama running locally
- Model `Qwen_peregrine` created (see below)
- Embedding model available locally (default: `nomic-embed-text`)

## Create the local model

```bash
ollama create Qwen_peregrine -f peregrine_local/Modelfile
```

This uses `qwen2.5:32b-instruct` as the base model. You can edit `peregrine_local/Modelfile` to change the base.

## Configure

Environment variables (optional):

- `PEREGRINE_VAULT_PATH` (default: `~/AcquittifyData/Obsidian` unless legacy in-repo data folders exist)
- `PEREGRINE_OLLAMA_URL` (default: `http://localhost:11434`)
- `PEREGRINE_MODEL` (default: `Qwen_peregrine`)
- `PEREGRINE_EMBED_MODEL` (default: `nomic-embed-text`)
- `PEREGRINE_INDEX_INTERVAL` (default: `300` seconds)

## Install deps

```bash
python3 -m pip install -r peregrine_local/requirements.txt
```

## Index the vault

```bash
python3 -m peregrine_local index
```

Rebuild from scratch:

```bash
python3 -m peregrine_local index --rebuild
```

## Continuous indexing

```bash
python3 -m peregrine_local watch --interval 300
```

## Search

```bash
python3 -m peregrine_local search "savani"
```

## Ask a question (RAG)

```bash
python3 -m peregrine_local chat "Which documents mention Savani?"
```

## Local API

```bash
uvicorn peregrine_local.api:app --host 127.0.0.1 --port 8765
```

Endpoints:

- `GET /health`
- `GET /status`
- `POST /index`
- `POST /search`
- `POST /chat`

## Offline mode

Once models are local and the vault is indexed, the system runs without internet access.
