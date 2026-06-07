#!/usr/bin/env python3
"""Create Weblate project and components for this repository."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


DEFAULT_PROJECT_SLUG = "danbooru-tag-database"
DEFAULT_PROJECT_NAME = "GALIAIS Danbooru Tag Database"
REPOSITORY_URL = "https://github.com/GALIAIS/Danbooru-Tag-Database.git"
REPOSITORY_WEB = "https://github.com/GALIAIS/Danbooru-Tag-Database"
REPOWEB = "https://github.com/GALIAIS/Danbooru-Tag-Database/blob/{{branch}}/{{filename}}#L{{line}}"


@dataclass(frozen=True)
class ApiError(Exception):
    status: int
    body: str

    def __str__(self) -> str:
        return f"HTTP {self.status}: {self.body}"


def read_token(args: argparse.Namespace) -> str:
    if args.token:
        return args.token.strip()
    if args.token_file:
        return Path(args.token_file).read_text(encoding="utf-8").strip()
    token = os.environ.get("WEBLATE_TOKEN", "").strip()
    if token:
        return token
    raise SystemExit("missing token: pass --token-file, --token, or WEBLATE_TOKEN")


def api_request(
    base_url: str,
    token: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    retries: int = 4,
) -> Any:
    url = base_url.rstrip("/") + path
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "Authorization": f"Token {token}",
        "User-Agent": "GALIAIS-Danbooru-Weblate-Setup/1.0",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    for attempt in range(retries + 1):
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=180) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else None
        except HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            if exc.code not in {429, 500, 502, 503, 504} or attempt >= retries:
                raise ApiError(exc.code, body) from exc
            time.sleep(2**attempt)
        except (TimeoutError, ConnectionError, http.client.RemoteDisconnected, http.client.IncompleteRead) as exc:
            if attempt >= retries:
                raise RuntimeError(f"{method} {path} failed after retries: {exc}") from exc
            time.sleep(2**attempt)


def ensure_project(base_url: str, token: str, *, project_slug: str, project_name: str) -> dict[str, Any]:
    payload = {
        "name": project_name,
        "slug": project_slug,
        "web": REPOSITORY_WEB,
        "instructions": (
            "Danbooru tag and taxonomy translation database. Translate PO files in Weblate; "
            "rebuild SQLite from this repository with tools/danbooru_textdb.py after changes."
        ),
        "new_lang": "none",
        "language_code_style": "bcp",
        "commit_policy": 0,
        "enable_hooks": True,
    }
    try:
        return api_request(base_url, token, "POST", "/api/projects/", payload)
    except ApiError as exc:
        if exc.status != 400:
            raise
        try:
            return api_request(base_url, token, "GET", f"/api/projects/{project_slug}/")
        except ApiError:
            raise exc


def component_payload(name: str, slug: str, filemask: str, *, repo: str, priority: int, new_lang: str, new_base: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "slug": slug,
        "vcs": "git",
        "repo": repo,
        "filemask": filemask,
        "file_format": "po",
        "new_lang": new_lang,
        "new_base": new_base,
        "language_code_style": "bcp",
        "merge_style": "rebase",
        "push_on_commit": False,
        "commit_pending_age": 24,
        "enable_suggestions": True,
        "suggestion_voting": False,
        "suggestion_autoaccept": 0,
        "allow_translation_propagation": True,
        "manage_units": False,
        "restricted": False,
        "priority": priority,
        "check_flags": "ignore-same,ignore-inconsistent",
        "repoweb": REPOWEB,
    }
    if repo == REPOSITORY_URL:
        payload["branch"] = "main"
    return payload


def ensure_component(base_url: str, token: str, project_slug: str, payload: dict[str, Any]) -> dict[str, Any]:
    slug = payload["slug"]
    try:
        return api_request(base_url, token, "POST", f"/api/projects/{project_slug}/components/", payload)
    except ApiError as exc:
        if exc.status != 400:
            raise
        try:
            existing = api_request(base_url, token, "GET", f"/api/components/{project_slug}/{slug}/")
        except ApiError:
            raise exc
        patch_payload = {key: value for key, value in payload.items() if key not in {"vcs", "repo", "branch"}}
        return api_request(base_url, token, "PATCH", f"/api/components/{project_slug}/{slug}/", patch_payload) or existing


def repository_operation(base_url: str, token: str, project_slug: str, component_slug: str, operation: str) -> Any:
    return api_request(
        base_url,
        token,
        "POST",
        f"/api/components/{project_slug}/{component_slug}/repository/",
        {"operation": operation},
    )


def component_slug_for_group(group: str) -> str:
    suffix = "symbols" if group == "_symbols" else re.sub(r"[^a-z0-9-]+", "-", group.lower()).strip("-")
    return f"tags-{suffix}"


def discover_tag_groups(repo: Path) -> list[str]:
    tags_dir = repo / "po" / "tags"
    if not tags_dir.exists():
        return []
    return sorted(path.name for path in tags_dir.iterdir() if path.is_dir() and (path / "en.po").exists())


def parse_groups(value: str, available: list[str]) -> list[str]:
    if not value.strip():
        return []
    aliases = {"symbols": "_symbols", "_": "_symbols"}
    result = []
    for raw in value.split(","):
        item = aliases.get(raw.strip(), raw.strip())
        if item:
            result.append(item)
    invalid = [item for item in result if item not in available]
    if invalid:
        raise SystemExit(f"invalid groups: {', '.join(invalid)}")
    return result


def range_groups(value: str, available: list[str]) -> list[str]:
    if not value.strip():
        return []
    start, _, end = value.partition("-")
    if not end:
        return parse_groups(value, available)
    aliases = {"symbols": "_symbols", "_": "_symbols"}
    start = aliases.get(start.strip(), start.strip())
    end = aliases.get(end.strip(), end.strip())
    if start not in available or end not in available:
        raise SystemExit(f"invalid group range: {value}")
    start_index = available.index(start)
    end_index = available.index(end)
    if start_index > end_index:
        raise SystemExit(f"invalid descending group range: {value}")
    return available[start_index : end_index + 1]


def build_components(
    project_slug: str,
    groups: list[str] | None = None,
    *,
    include_taxonomy: bool = True,
    new_lang: str = "none",
    repo_path: Path = Path("."),
) -> list[dict[str, Any]]:
    components = []
    if include_taxonomy:
        components.append(
            component_payload(
                "Taxonomy",
                "taxonomy",
                "po/taxonomy/*.po",
                repo=REPOSITORY_URL,
                priority=60,
                new_lang=new_lang,
                new_base="po/taxonomy/en.po" if new_lang == "add" else "",
            )
        )
    linked_repo = f"weblate://{project_slug}/taxonomy"
    tag_groups = groups if groups is not None else discover_tag_groups(repo_path)
    for group in tag_groups:
        components.append(
            component_payload(
                f"Tags {group}",
                component_slug_for_group(group),
                f"po/tags/{group}/*.po",
                repo=linked_repo,
                priority=100,
                new_lang=new_lang,
                new_base=f"po/tags/{group}/en.po" if new_lang == "add" else "",
            )
        )
    return components


def task_state(base_url: str, token: str, task_url: str) -> dict[str, Any]:
    marker = "/api/tasks/"
    index = task_url.find(marker)
    path = task_url[index:] if index >= 0 else task_url
    return api_request(base_url, token, "GET", path, retries=1)


def component_translations(base_url: str, token: str, project_slug: str, component_slug: str) -> list[dict[str, Any]]:
    data = api_request(base_url, token, "GET", f"/api/components/{project_slug}/{component_slug}/translations/?page_size=20", retries=1)
    return list(data.get("results") or [])


def wait_for_component(base_url: str, token: str, project_slug: str, component_slug: str, *, max_wait: int, interval: int) -> dict[str, Any]:
    deadline = time.monotonic() + max_wait
    last: dict[str, Any] = {"slug": component_slug, "status": "pending"}
    while time.monotonic() < deadline:
        component = api_request(base_url, token, "GET", f"/api/components/{project_slug}/{component_slug}/", retries=1)
        task_url = component.get("task_url")
        task = task_state(base_url, token, task_url) if task_url else None
        translations = component_translations(base_url, token, project_slug, component_slug)
        languages = {item.get("language_code"): int(item.get("total") or 0) for item in translations}
        result = task.get("result") if task else None
        has_units = any(total > 0 for total in languages.values())
        last = {
            "slug": component_slug,
            "task": bool(task_url),
            "completed": task.get("completed") if task else None,
            "progress": task.get("progress") if task else None,
            "result": result,
            "languages": languages,
        }
        failed = False
        if task:
            status = str(task.get("status") or "").lower()
            failed = status in {"failed", "failure", "error"} or bool(task.get("error"))
        if isinstance(result, str) and result.strip():
            failed = True
        if failed:
            last["status"] = "failed"
            return last
        if has_units and (not task_url or (task and task.get("completed"))):
            last["status"] = "imported"
            return last
        if has_units:
            last["status"] = "importing"
            return last
        time.sleep(interval)
    last["status"] = "timeout"
    return last


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Weblate base URL, for example https://l10n.galiais.org")
    parser.add_argument("--token-file", help="Path to a Weblate API token file")
    parser.add_argument("--token", help="Weblate API token")
    parser.add_argument("--project-slug", default=DEFAULT_PROJECT_SLUG, help="Weblate project slug")
    parser.add_argument("--project-name", default=DEFAULT_PROJECT_NAME, help="Weblate project display name")
    parser.add_argument("--repo", type=Path, default=Path("."), help="Local repository path used to discover tag PO groups")
    parser.add_argument("--groups", default="", help="Comma-separated tag groups to create, for example symbols,0,1,a,b")
    parser.add_argument("--group-range", default="", help="Tag group range to create, for example 0-9 or a-f")
    parser.add_argument("--skip-taxonomy", action="store_true", help="Do not create or update the taxonomy component")
    parser.add_argument("--new-lang", choices=["none", "add", "contact", "url"], default="none", help="Weblate setting for adding new translations")
    parser.add_argument("--pull", action="store_true", help="Pull latest Git changes into the shared Weblate repository")
    parser.add_argument("--scan", action="store_true", help="Trigger Weblate file scan after component setup")
    parser.add_argument("--wait", action="store_true", help="Wait for created components to import before exiting")
    parser.add_argument("--max-wait", type=int, default=900, help="Maximum seconds to wait per component")
    parser.add_argument("--wait-interval", type=int, default=20, help="Polling interval in seconds")
    args = parser.parse_args(argv)

    token = read_token(args)
    project = ensure_project(args.url, token, project_slug=args.project_slug, project_name=args.project_name)
    if args.pull:
        repository_operation(args.url, token, args.project_slug, "taxonomy", "pull")
    available_groups = discover_tag_groups(args.repo)
    groups = parse_groups(args.groups, available_groups)
    groups.extend(group for group in range_groups(args.group_range, available_groups) if group not in groups)
    selected_groups = groups if groups else None
    created = []
    wait_slugs = []
    for payload in build_components(
        args.project_slug,
        selected_groups,
        include_taxonomy=not args.skip_taxonomy,
        new_lang=args.new_lang,
        repo_path=args.repo,
    ):
        component = ensure_component(args.url, token, args.project_slug, payload)
        if args.scan:
            repository_operation(args.url, token, args.project_slug, component["slug"], "file-scan")
        created.append(
            {
                "slug": component["slug"],
                "name": component["name"],
                "filemask": component["filemask"],
            }
        )
        print(json.dumps(created[-1], ensure_ascii=False), flush=True)
        wait_slugs.append(component["slug"])

    wait_results = []
    if args.wait:
        for slug in wait_slugs:
            result = wait_for_component(
                args.url,
                token,
                args.project_slug,
                slug,
                max_wait=args.max_wait,
                interval=args.wait_interval,
            )
            wait_results.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)

    print(json.dumps({"project": project["slug"], "components": len(created), "wait": wait_results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
