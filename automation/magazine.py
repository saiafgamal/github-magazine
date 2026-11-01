#!/usr/bin/env python3
"""GitHub Magazine weekly generator, validator and index updater.

Standard library only. Run from the repository root:

    python3 automation/magazine.py status
    python3 automation/magazine.py preflight 2026-10-31
    python3 automation/magazine.py build 2026-10-31
    python3 automation/magazine.py validate 2026-10-31

Source: SnailDev/github-hot-hub weekly archive, section "近一周热门仓库".
Hard gates: 12 repositories from the source, a reviewed copy entry for
every one of them, canonical GitHub names, no fabricated data, and no
overwrite of a published issue without --force.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
AUTO = ROOT / "automation"
COPY_FILE = AUTO / "copy.json"
ISSUES_FILE = AUTO / "issues.json"
ARCHIVE_URL = "https://raw.githubusercontent.com/SnailDev/github-hot-hub/main/archives/{date}.md"
WEEKLY_HEADING = "## 近一周热门仓库"
REPO_COUNT = 12
FIRST_TRACKED_SATURDAY = dt.date(2026, 5, 16)
TZ = ZoneInfo("Europe/Istanbul")
DATE_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FORBIDDEN_VISIBLE = re.compile(r"\b(NaN|undefined|null|None)\b")
NO_LANGUAGE = {"", "无", "none", "null"}


class GateError(RuntimeError):
    pass


# ---------------------------------------------------------------- source

def fetch(url: str, accept: str | None = None) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "github-magazine-automation"})
    if accept:
        req.add_header("Accept", accept)
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token and "api.github.com" in url:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse_weekly(markdown: str) -> list[dict]:
    if WEEKLY_HEADING not in markdown:
        raise GateError(f"archive has no '{WEEKLY_HEADING}' section")
    section = markdown.split(WEEKLY_HEADING, 1)[1]
    section = re.split(r"^## ", section, maxsplit=1, flags=re.M)[0]
    entry = re.compile(
        r"^1\. \[(?P<owner>[^\]/]+?) / (?P<repo>[^\]]+?)\]\((?P<url>https://github\.com/[^)]+)\)\s*\n"
        r"\s+- (?P<desc>.*?)\n"
        r"\s+- language: \*\*(?P<lang>.*?)\*\*.*?stars: \*\*(?P<stars>[\d,]+)\*\*.*?`(?P<gain>[\d,]+) stars this week`",
        re.M,
    )
    repos = []
    for m in entry.finditer(section):
        repos.append({
            "archive_full_name": f"{m['owner'].strip()}/{m['repo'].strip()}",
            "stars": m["stars"],
            "gain": m["gain"],
            "language": m["lang"].strip(),
        })
    return repos


def canonical(full_name: str) -> dict:
    """Canonical GitHub metadata; follows renames. Raises GateError if unusable."""
    try:
        data = json.loads(fetch(f"https://api.github.com/repos/{full_name}", "application/vnd.github+json"))
    except urllib.error.HTTPError as exc:
        raise GateError(f"{full_name}: GitHub API HTTP {exc.code}") from exc
    if not data.get("full_name") or not data.get("name"):
        raise GateError(f"{full_name}: GitHub API returned no canonical name")
    return {"full_name": data["full_name"], "name": data["name"], "language": data.get("language") or ""}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def collect(date: str) -> tuple[list[dict], list[str]]:
    """Return the issue's 12 repos merged with copy, plus a list of gate problems."""
    try:
        markdown = fetch(ARCHIVE_URL.format(date=date))
    except urllib.error.HTTPError as exc:
        raise GateError(f"archive {date}.md: HTTP {exc.code}") from exc
    parsed = parse_weekly(markdown)
    if len(parsed) < REPO_COUNT:
        raise GateError(f"weekly section had only {len(parsed)} parsed repos (need {REPO_COUNT})")
    copy = load_json(COPY_FILE)
    lowered = {k.lower(): k for k in copy}
    repos, missing = [], []
    for item in parsed[:REPO_COUNT]:
        meta = canonical(item["archive_full_name"])
        key = lowered.get(meta["full_name"].lower())
        entry = copy.get(key) if key else None
        if not entry or not all(entry.get(f) for f in ("category", "description", "first_test")):
            missing.append(meta["full_name"])
            continue
        lang = item["language"]
        if lang.lower() in NO_LANGUAGE:
            lang = meta["language"] or "No primary language"
        repos.append({**item, **meta, **{k: entry[k] for k in ("category", "description", "first_test")}, "language": lang})
    return repos, missing


# ---------------------------------------------------------------- render

def long_date(date: str) -> str:
    d = dt.date.fromisoformat(date)
    return f"{d:%B} {d.day}, {d.year}"


def short_date(date: str) -> str:
    d = dt.date.fromisoformat(date)
    return f"{d:%b} {d.day}, {d.year}"


def weekly_dirs() -> list[str]:
    return sorted(p.name for p in ROOT.iterdir() if p.is_dir() and DATE_DIR.match(p.name))


def issue_number(date: str) -> int:
    return len([d for d in weekly_dirs() if d < date]) + 1


def render(date: str, repos: list[dict], generator: str) -> str:
    e = lambda s: html.escape(s, quote=True)
    number = issue_number(date)
    head = (AUTO / "template_head.html").read_text(encoding="utf-8")
    head = head.replace("{{WIDTH}}", str((len(repos) + 2) * 100)).replace("{{LONG_DATE}}", long_date(date))
    cover = f"""<section class="page cover">
  <div>
    <div class="cover-kicker">GitHub Trending Weekly</div>
    <h1 class="cover-title">GitHub Repo Briefing</h1>
  </div>
  <div>
    <div class="cover-subtitle">Twelve weekly trending repositories, summarized by what they do and how to test them</div>
    <div class="cover-date">{long_date(date)}</div>
    <div class="cover-issue">Issue {number:02d}</div>
  </div>
</section>
"""
    pages = []
    for i, r in enumerate(repos, 1):
        pages.append(f"""<section class="page repo-page {'light' if i % 2 else 'dark'}">
  <div class="repo-left">
    <div class="rank">{i:02d}</div>
    <div class="category">{e(r['category'])}</div>
    <h2 class="repo-headline">{e(r['name'])}</h2>
    <p class="repo-path"><a href="https://github.com/{e(r['full_name'])}" target="_blank" rel="noopener">{e(r['full_name'])}</a></p>
    <p class="repo-description">{e(r['description'])}</p>
  </div>
  <div class="repo-right">
    <div class="star-count">{e(r['stars'])}</div>
    <div class="repo-meta">Stars total / {e(r['language'])}</div>
    <div class="weekly-gain">{e(r['gain'])} stars this week</div>
    <div class="callout">
      <p class="callout-title">A first test</p>
      <p class="callout-text">{e(r['first_test'])}</p>
    </div>
  </div>
</section>""")
    back = f"""
<section class="page back">
  <div class="cover-kicker">End of Issue</div>
  <div class="back-title">Check the links. Test one repo.</div>
  <div class="back-meta">GitHub Trending Weekly / Issue {number:02d}<br>Generated by {e(generator)} from SnailDev github-hot-hub weekly archive: {ARCHIVE_URL.format(date=date)}</div>
</section>
"""
    tail = (AUTO / "template_tail.html").read_text(encoding="utf-8")
    return head + cover + "".join(pages) + back + tail


# ---------------------------------------------------------------- validate

class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts: list[str] = []
        self.pages = 0
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style"):
            self.skip += 1
        if tag == "section" and "page" in (a.get("class") or "").split():
            self.pages += 1
        if tag == "a" and re.match(r"^https://github\.com/[^/]+/[^/]+$", a.get("href") or ""):
            self.links.append(a["href"])

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def validate(path: Path, expect_repos: int = REPO_COUNT) -> list[str]:
    text = path.read_text(encoding="utf-8")
    p = _Text()
    p.feed(text)
    visible = " ".join(p.parts)
    errors = []
    if p.pages != expect_repos + 2:
        errors.append(f"expected {expect_repos + 2} pages, found {p.pages}")
    if len(set(p.links)) != expect_repos:
        errors.append(f"expected {expect_repos} distinct GitHub repo links, found {len(set(p.links))}")
    if "SnailDev github-hot-hub" not in visible:
        errors.append("missing SnailDev attribution")
    bad = sorted(set(FORBIDDEN_VISIBLE.findall(visible)))
    if bad:
        errors.append(f"visible forbidden tokens: {bad}")
    if "{{" in text:
        errors.append("unrendered template placeholder")
    return errors


# ---------------------------------------------------------------- index

def update_index(date: str, topic: str) -> None:
    path = ROOT / "index.html"
    src = path.read_text(encoding="utf-8")
    number = issue_number(date)
    title = f"Top GitHub Repositories - {long_date(date)}"
    row = (f'        <a class="issue-link" href="./{date}/">\n'
           f'          <span class="issue-number">Issue {number:02d}</span>\n'
           f'          <span class="issue-date">{short_date(date)}</span>\n'
           f'          <span class="issue-title">{title}</span>\n'
           f'          <span class="issue-topic">{html.escape(topic, quote=False)}</span>\n'
           f'        </a>\n')
    if f'href="./{date}/"' in src.split('<nav class="issue-list"', 1)[1]:
        return  # already listed
    # insert in date order among dated rows
    nav_start = src.index('<nav class="issue-list"')
    insert_at = None
    for m in re.finditer(r'        <a class="issue-link" href="\./([^/]+)/">', src[nav_start:]):
        if m.group(1) < date:
            insert_at = nav_start + m.start()
            break
    if insert_at is None:
        insert_at = src.index("      </nav>", nav_start)
    src = src[:insert_at] + row + src[insert_at:]
    latest = max(weekly_dirs() + [date])
    if latest == date:
        src = re.sub(r'<a class="latest" href="\./[^/]+/" aria-label="Read issue, [^"]+">',
                     f'<a class="latest" href="./{date}/" aria-label="Read issue, {long_date(date)}">', src, count=1)
        src = re.sub(r'<span class="latest-title">[^<]*</span>', f'<span class="latest-title">{title}</span>', src, count=1)
        src = re.sub(r'<span class="latest-meta">Issue \d+\.', f'<span class="latest-meta">Issue {number:02d}.', src, count=1)
    editions = len(re.findall(r'<a class="issue-link" href=', src))
    src = re.sub(r"<p>\d+ editions</p>", f"<p>{editions} editions</p>", src, count=1)
    path.write_text(src, encoding="utf-8")


# ---------------------------------------------------------------- commands

def saturdays_through(today: dt.date) -> list[str]:
    last = today - dt.timedelta(days=(today.weekday() - 5) % 7)
    out, d = [], FIRST_TRACKED_SATURDAY
    while d <= last:
        out.append(d.isoformat())
        d += dt.timedelta(days=7)
    return out


def cmd_status(args) -> int:
    today = dt.datetime.now(TZ).date()
    missing = [d for d in saturdays_through(today) if not (ROOT / d / "index.html").exists()]
    print(json.dumps({"today_istanbul": today.isoformat(), "missing": missing}))
    return 0


def cmd_preflight(args) -> int:
    try:
        repos, missing = collect(args.date)
        problems = []
        if not load_json(ISSUES_FILE).get(args.date, {}).get("topic"):
            problems.append(f"automation/issues.json has no topic for {args.date}")
        status = "ready" if not missing and not problems else "needs_copy"
        print(json.dumps({"date": args.date, "status": status, "missing_copy": missing,
                          "errors": problems, "repos": [r["full_name"] for r in repos]}, ensure_ascii=False))
        return 0 if status == "ready" else 2
    except GateError as exc:
        print(json.dumps({"date": args.date, "status": "blocked", "error": str(exc)}, ensure_ascii=False))
        return 3


def cmd_build(args) -> int:
    out = ROOT / args.date / "index.html"
    if out.exists() and not args.force:
        print(f"{out.relative_to(ROOT)} exists; refusing to overwrite without --force", file=sys.stderr)
        return 1
    repos, missing = collect(args.date)
    if missing:
        raise GateError(f"missing reviewed copy for: {', '.join(missing)}")
    topic = load_json(ISSUES_FILE).get(args.date, {}).get("topic")
    if not topic and not args.no_index:
        raise GateError(f"automation/issues.json has no topic for {args.date}")
    page = render(args.date, repos, args.generator)
    tmp = AUTO / f".{args.date}.tmp.html"
    tmp.write_text(page, encoding="utf-8")
    errors = validate(tmp)
    if errors:
        raise GateError("validation failed: " + "; ".join(errors) + f" (draft kept at {tmp})")
    out.parent.mkdir(exist_ok=True)
    tmp.replace(out)
    if not args.no_index:
        update_index(args.date, topic)
    print(json.dumps({"date": args.date, "written": str(out.relative_to(ROOT)),
                      "issue": issue_number(args.date), "repos": [r["full_name"] for r in repos]}))
    return 0


def cmd_validate(args) -> int:
    errors = validate(ROOT / args.date / "index.html", args.repos)
    print(json.dumps({"date": args.date, "ok": not errors, "errors": errors}))
    return 0 if not errors else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    p = sub.add_parser("preflight"); p.add_argument("date"); p.set_defaults(fn=cmd_preflight)
    p = sub.add_parser("build"); p.add_argument("date")
    p.add_argument("--force", action="store_true", help="overwrite an existing issue (manual runs only)")
    p.add_argument("--generator", default="Claude")
    p.add_argument("--no-index", action="store_true")
    p.set_defaults(fn=cmd_build)
    p = sub.add_parser("validate"); p.add_argument("date"); p.add_argument("--repos", type=int, default=REPO_COUNT)
    p.set_defaults(fn=cmd_validate)
    args = ap.parse_args()
    try:
        return args.fn(args)
    except GateError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
