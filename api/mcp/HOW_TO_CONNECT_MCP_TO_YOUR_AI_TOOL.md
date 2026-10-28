# Connect the MCP server to Codex

This project includes a minimal MCP server using the stdio transport. It exposes one tool, `greet`, so you can confirm Codex can start the server, discover its tool, and run it.

## 1. Confirm the server works locally

You can also start the server directly:

```bash
uv run python -m api.mcp.app
```

The server uses stdio. It waits for an MCP client to communicate over its standard input and output. Stop this manual run with Ctrl+C before continuing; Codex will start its own server process when it connects.

## 2. Register the server with Codex

Install and sign in to the Codex CLI if you have not already. From the repository root, add this server to your user-level Codex configuration:

```bash
codex mcp add lab-data-integrations -- uv --directory "$PWD" run python -m api.mcp.app
```

`$PWD` is expanded by your shell to the current directory. Run the command from this repository's root so `uv` can find `pyproject.toml` and the `api.mcp.app` Python module. This configuration is stored by Codex in `~/.codex/config.toml` and is shared with the Codex IDE extension.

Check that Codex has registered it:

```bash
codex mcp list
codex mcp get lab-data-integrations
```

## 3. Try it in Codex

Restart Codex or start a new Codex session so it reloads the MCP configuration. Ask Codex:

> Use the `greet` tool from `lab-data-integrations` with the name `researcher`.

The expected tool result is:

```text
Hello, researcher! The MCP server is working.
```

Codex starts the stdio server as needed; do not start a second server in another terminal for this step.

## Remove the Codex entry

To disconnect this server from Codex later:

```bash
codex mcp remove lab-data-integrations
```

For current Codex MCP options and configuration details, see the [OpenAI Codex MCP documentation](https://developers.openai.com/codex/mcp/).
