# Title (for GitHub/GitLab issue)

**Add PR merged webhook: pull from default branch and restart server**

---

# Description (paste into issue body)

## Goal

- Handle webhooks that indicate a **PR was merged**. On merge: **pull** from the default branch and **restart** the webhook/API server (works in console and Docker).
- Add a **config option for the default branch** and use it instead of determining it from the API where possible.
- Optionally: run the webhook server with **uvicorn** so `--reload` is available in development.

## Tasks

- [ ] Handle "PR merged" events (e.g. GitHub `pull_request` with `action: closed` and `merged: true`).
- [ ] On merge: run `git pull origin <default_branch>` in the bot working directory, then restart the server (document behavior for console and Docker).
- [ ] Add config option for default branch (e.g. `bot.default_branch: "main"`); use it for pull and for PR/branch operations; remove or reduce `get_default_branch` usage where redundant.
- [ ] (Optional) Add uvicorn, serve webhook app with it, support `--reload` for development.
- [ ] Update tests and docs (config example, README).

## References

- Current webhook: `coddy/observer/webhook/server.py`, `coddy/observer/webhook/handlers.py`
- Config: `coddy/config.py`; default branch: `coddy/observer/adapters/github.py` `get_default_branch`
- Git pull: `coddy/services/git` (`run_git_pull`)
