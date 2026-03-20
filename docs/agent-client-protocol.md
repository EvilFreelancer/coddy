# Agent Client Protocol (ACP) in Coddy

## What is ACP

The **Agent Client Protocol (ACP)** is an open standard for communication between code editors or automation (the **client**) and coding agents (the **agent**). It is designed to reduce one-off integrations and lock-in, similar in spirit to how the Language Server Protocol (LSP) standardized language servers.

- **Official documentation (introduction)**: [agentclientprotocol.com](https://agentclientprotocol.com/)
- **Protocol schema (types and messages)**: [agentclientprotocol.com/protocol/schema](https://agentclientprotocol.com/protocol/schema)
- **GitHub organization** (spec, SDKs, registry): [github.com/agentclientprotocol](https://github.com/agentclientprotocol)

Local agents typically run as a subprocess and exchange messages over **JSON-RPC on stdio**. Remote transports (HTTP, WebSocket) are part of the broader ecosystem; Coddy uses the **local stdio** path.

## How Coddy uses ACP

The worker does not embed a specific vendor SDK for Cursor or OpenCode. It depends on the official Python package **`agent-client-protocol`** ([PyPI](https://pypi.org/project/agent-client-protocol/)), which implements the client side of the protocol.

- **`ACPAgent`** (`coddy/worker/agents/acp_agent.py`) spawns the configured agent binary with `spawn_agent_process`, negotiates `initialize`, opens a session, and sends a `prompt` with the task text (planning, implementation, or review).
- **`_LocalACPClient`** implements the ACP **client** interface for this process: it exposes **read/write text files**, **terminals** (async subprocess), and merges streamed **assistant message** and **plan** updates so the substantive output is not lost when agents split content across update types.
- **Permissions**: interactive permission prompts are not used in the headless worker; the client responds with the first allowed option when the agent requests permission.

The backend command is **fully configurable** (`acp.command` in YAML). Examples include `agent acp` (Cursor Agent) or `opencode acp` (OpenCode). Any binary that speaks ACP over stdio can be used if it matches the deployed SDK version expectations.

## Configuration

| Setting | Description |
|--------|-------------|
| `acp.command` | argv for the agent: first element is the executable, rest are subcommands (default `["agent", "acp"]`) |
| `acp.timeout` | Per-prompt timeout in seconds (default `600`; override with env `ACP_TIMEOUT`) |
| `acp.env` | Extra environment variables for the agent process |

Tokens for backends that expect Cursor-style credentials are resolved from `CURSOR_AGENT_TOKEN` or `CURSOR_AGENT_TOKEN_FILE` and merged into the agent environment (as `CURSOR_AGENT_TOKEN`, `CURSOR_API_KEY`, and `CURSOR_AGENT_TOKEN_FILE` when applicable). See `make_acp_agent` in `acp_agent.py`.

## Tests

ACP-related behavior is covered in `tests/test_agents_acp.py` (local client text merging, plan generation wiring, PR report and review reply reading, env forwarding).

## See also

- [Architecture](architecture.md) - worker agents layer
- [System specification](system-specification.md) - workflow and configuration
