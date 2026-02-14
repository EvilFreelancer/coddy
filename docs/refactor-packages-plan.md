# Refactoring plan: packages observer, worker, utils

## Target structure (updated)

- **observer** – platform adapters, issues, PR (review), planner, webhook, scheduler, daemon.
- **worker** – run loop, ralph_loop, **agents** (всё, что запускает агентов).
- **utils** – branch, issue_to_markdown, **git_runner**.
- **service** – не создаём; всё распределено по observer / worker / utils.
- **task_file** – отказываемся от .md, переход на YAML; модуль пока оставляем (в worker) до миграции, затем удаляем.

---

## Final layout

```
coddy/
├── __init__.py
├── main.py
├── config.py
│
├── observer/
│   ├── __init__.py
│   ├── models/             # базовые модели данных (Pydantic), один класс — один файл
│   │   ├── __init__.py
│   │   ├── issue.py
│   │   ├── comment.py
│   │   ├── pr.py
│   │   └── review_comment.py
│   ├── queue.py            # в корне observer (не в issues)
│   ├── adapters/           # GitHub / GitLab / Bitbucket
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── github.py
│   ├── issues/             # issue_file, issue_store, issue_state (без queue)
│   │   ├── __init__.py
│   │   ├── issue_file.py
│   │   ├── issue_store.py
│   │   └── issue_state.py
│   ├── pr/                 # всё, что связано с PR (ревью и т.д.)
│   │   ├── __init__.py
│   │   └── review_handler.py
│   ├── planner.py          # план, подтверждение пользователя
│   ├── webhook/
│   │   ├── __init__.py
│   │   ├── server.py
│   │   └── handlers.py
│   ├── scheduler.py
│   └── daemon.py
│
├── worker/
│   ├── __init__.py
│   ├── run.py              # текущий worker.py
│   ├── ralph_loop.py       # из services/ralph_loop
│   ├── agents/             # только base + cursor (stub_agent удалён)
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── cursor_cli_agent.py
│   └── task_yaml.py        # задача и PR report в YAML (вместо task_file .md)
│
├── utils/
│   ├── __init__.py
│   ├── branch.py           # sanitize_branch_name, is_valid_branch_name
│   ├── issue_to_markdown.py
│   └── git_runner.py       # из services/git_runner
│
└── scripts/
    └── issue_to_markdown.py  # CLI: load issue, print markdown
```

---

## Summary of moves

| Что | Куда |
|-----|------|
| adapters (base, github) | observer/adapters/ |
| issue_file, issue_store, issue_state | observer/issues/ |
| queue | observer/queue.py (корень observer) |
| models (Issue, Comment, PR, ReviewComment) | observer/models/ (по одному файлу на класс, Pydantic) |
| review_handler | observer/pr/ |
| planner | observer/ |
| webhook, scheduler, daemon | observer/ |
| worker.py → run.py, ralph_loop | worker/ |
| agents/ | worker/agents/ |
| utils (branch) + issue_to_markdown + git_runner | utils/ |
| task_file | удалён; заменён на worker/task_yaml.py (YAML) |
| stub_agent | удалён; только base + cursor_cli |
| issue_processor | нигде не вызывается; перенести в observer или удалить по желанию |

Папка **services** после рефакторинга не остаётся.

---

## Execution order (short)

1. Create **utils/** and move branch helpers, issue_to_markdown, git_runner; update imports.
2. Create **observer/**, **observer/issues/**, **observer/adapters/**, **observer/pr/**; move adapters, issue_*, queue; move review_handler into observer/pr/; move planner, webhook, scheduler, daemon into observer/; update imports.
3. Create **worker/**; move worker run logic to worker/run.py, ralph_loop to worker/; move **agents/** into worker/agents/; move task_file into worker/ (temporary); update imports.
4. main.py: import daemon from observer, worker from worker; ensure `coddy daemon` / `coddy worker` and `python -m coddy.daemon` / `python -m coddy.worker` work (optional re-export stubs in root).
5. Update all tests and docs; run full test suite and pre-commit.
6. Remove obsolete files from root and old services/.

---

## issue_processor

Сейчас нигде не вызывается (только упоминание в docs). Варианты: перенести в observer (например observer/issue_processor.py) как запасной поток или удалить; при рефакторинге можно не трогать до решения.

---

## task_file заменён на YAML

Модуль task_file удалён. Вместо него используется worker/task_yaml.py: задача и PR report хранятся в .coddy/task-{n}.yaml и .coddy/pr-{n}.yaml. Тесты task_file заменены на test_task_yaml.py.
