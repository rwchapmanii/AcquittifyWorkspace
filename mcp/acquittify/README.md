# Acquittify MCP Server

This MCP server exposes read-only Peregrine/Acquittify APIs so Ponner-Investigator can query matters and documents.

## Install

```bash
python3 -m pip install -r mcp/acquittify/requirements.txt
```

## Configure

Update `mcp/acquittify/ponner-investigator.mcp.json` if your API URL is not `http://localhost:8000`.

Set Ponner-Investigator to use the dedicated Obsidian vault inside `acquittify`:

```bash
export SMART_VAULT_PATH=/Users/ronaldchapman/Desktop/Acquittify/acquittify
```

Optional API auth:

```bash
export PEREGRINE_API_TOKEN=...    # or ACQUITTIFY_API_TOKEN
```

## Run (manual)

```bash
python3 mcp/acquittify/server.py
```

## Ponner-Investigator MCP config

Merge `mcp/acquittify/ponner-investigator.mcp.json` into the `.mcp.json` used by Ponner-Investigator.
