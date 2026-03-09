# Agent Instructions (Internal LLM)

Ponner-Investigator uses a local Ollama Deepseek 8B model for all LLM reasoning.

## Ponner Obsidian Tools
Available tools:
- `obsidian_vault_info`
- `obsidian_list_notes`
- `obsidian_read_note`
- `obsidian_search`
- `obsidian_create_note`
- `obsidian_update_note`
- `obsidian_delete_note`
- `obsidian_move_note`
- `obsidian_get_frontmatter`
- `obsidian_set_frontmatter`
- `obsidian_update_tags`
- `obsidian_search_replace`

## Behavior
- When a user asks to search or document in Obsidian, explicitly list the tools above and ask which one they want.
- Use `obsidian_search_replace` for global edits (default is `dry_run=true`).
