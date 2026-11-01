# GitHub Magazine automation (runbook)

Owner: Claude, as a scheduled cloud routine. This replaced the Codex automation `github-top-repo-magazine`, which is paused, on 2026-11-01.
Schedule: Saturday 22:15 Europe/Istanbul (19:15 UTC).
Publishes only to `saiafgamal/github-magazine` on `main`, at the repository root, served by GitHub Pages.

- Index: https://saiafgamal.github.io/github-magazine/
- Issue: https://saiafgamal.github.io/github-magazine/YYYY-MM-DD/
- Source: https://raw.githubusercontent.com/SnailDev/github-hot-hub/main/archives/YYYY-MM-DD.md, section `## 近一周热门仓库`

## Files

| File | Purpose |
|---|---|
| `magazine.py` | status / preflight / build / validate (standard-library Python 3.9+) |
| `copy.json` | Reviewed copy, keyed by canonical `owner/repo`: `name`, `category`, `description`, `first_test` |
| `issues.json` | Per-issue index topic line, e.g. `{"2026-10-31": {"topic": "..."}}` |
| `template_head.html`, `template_tail.html` | Issue page shell, taken verbatim from the 2026-10-24 issue |

## Weekly procedure

1. `python3 automation/magazine.py status` lists every Saturday since 2026-05-16 that has no issue folder. Work through them oldest first.
2. Run `python3 automation/magazine.py preflight DATE` for each date.
   - `ready`: go to step 3.
   - `needs_copy`: for each repo in `missing_copy`, read its README on GitHub and add a `copy.json` entry. The entry needs a short factual `description` (what it is and does, with no hype or trend commentary), a bounded `first_test` (one small, disposable, verifiable step), and a `category`. Reuse an existing category: Agent Ops, Open Source, Creative Systems, Infrastructure, Security, Data & Research, Productivity, Business Tools, Code Intelligence. Also add a short `topic` for DATE to `issues.json` (three themes, like "Design skills, SEO audits, agent methods"). Then re-run preflight.
   - `blocked`: the archive is missing or malformed, or it has fewer than 12 weekly repos. Do **not** fabricate data or skip repos. Report the exact error and leave that date for the next run.
3. `python3 automation/magazine.py build DATE` writes `DATE/index.html`, validates it (14 pages, 12 distinct repo links, SnailDev attribution, no visible NaN/undefined/null/None) and updates the root `index.html`. It refuses to overwrite an existing issue. Use `--force` only when Saiaf explicitly asks.
4. Commit only `DATE/index.html`, `index.html`, and any `automation/copy.json` or `automation/issues.json` changes. Use the message `Publish GitHub magazine DATE`. Push to `main`.
5. Poll `gh api repos/saiafgamal/github-magazine/pages/builds/latest` until the status is no longer `queued` or `building`. If `gh` is unavailable, check the URLs below for HTTP 200 for up to 10 minutes.
6. Verify `https://saiafgamal.github.io/github-magazine/?v=SHA` and `.../DATE/?v=SHA` return HTTP 200 and contain the new issue. If Pages lags, report the commit SHA and build status rather than claiming the page is live.

Report: the issue date(s), written or skipped, the commit SHA, both URLs, and any failures.

## Do not

- Publish anywhere else, push to any other repository, or send messages.
- Edit published issue pages, or change their fonts or design, without an explicit request.
- Weaken the 12-repo gate or the copy gate.

## History

- 2026-10-17 was published (on 2026-10-24) with 10 repos, because the source's weekly section had only 10 that week.
- Earlier issues show "Stars total / None" for repos with no primary language. From 2026-10-31 the generator prints "No primary language".
- Regression check: `build 2026-10-24 --force --generator Codex --no-index` in a scratch copy reproduces the published page byte for byte.
