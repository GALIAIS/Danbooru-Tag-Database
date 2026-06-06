#!/usr/bin/env python3
"""Create Weblate project and components for this repository."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


PROJECT_SLUG = "danbooru-tag-database"
PROJECT_NAME = "GALIAIS Danbooru Tag Database"
REPOSITORY_URL = "https://github.com/GALIAIS/Danbooru-Tag-Database.git"
REPOSITORY_WEB = "https://github.com/GALIAIS/Danbooru-Tag-Database"
REPOWEB = "https://github.com/GALIAIS/Danbooru-Tag-Database/blob/{{branch}}/{{filename}}#L{{line}}"
TAG_GROUPS = ["_symbols", *list("0123456789"), *list("abcdefghijklmnopqrstuvwxyz")]


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


def api_request(base_url: str, token: str, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    url = base_url.rstrip("/") + path
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json", "Authorization": f"Token {token}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=120) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else None
    except HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise ApiError(exc.code, body) from exc


def ensure_project(base_url: str, token: str) -> dict[str, Any]:
    payload = {
        "name": PROJECT_NAME,
        "slug": PROJECT_SLUG,
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
            return api_request(base_url, token, "GET", f"/api/projects/{PROJECT_SLUG}/")
        except ApiError:
            raise exc


def component_payload(name: str, slug: str, filemask: str, *, repo: str, priority: int) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "slug": slug,
        "vcs": "git",
        "repo": repo,
        "filemask": filemask,
        "file_format": "po",
        "new_lang": "none",
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


def ensure_component(base_url: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
    slug = payload["slug"]
    try:
        return api_request(base_url, token, "POST", f"/api/projects/{PROJECT_SLUG}/components/", payload)
    except ApiError as exc:
        if exc.status != 400:
            raise
        try:
            existing = api_request(base_url, token, "GET", f"/api/components/{PROJECT_SLUG}/{slug}/")
        except ApiError:
            raise exc
        patch_payload = {key: value for key, value in payload.items() if key not in {"vcs", "repo", "branch"}}
        return api_request(base_url, token, "PATCH", f"/api/components/{PROJECT_SLUG}/{slug}/", patch_payload) or existing


def build_components() -> list[dict[str, Any]]:
    components = [
        component_payload("Taxonomy", "taxonomy", "po/taxonomy/*.po", repo=REPOSITORY_URL, priority=60),
    ]
    linked_repo = f"weblate://{PROJECT_SLUG}/taxonomy"
    for group in TAG_GROUPS:
        suffix = "symbols" if group == "_symbols" else group
        components.append(
            component_payload(
                f"Tags {group}",
                f"tags-{suffix}",
                f"po/tags/{group}/*.po",
                repo=linked_repo,
                priority=100,
            )
        )
    return components


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Weblate base URL, for example https://l10n.galiais.org")
    parser.add_argument("--token-file", help="Path to a Weblate API token file")
    parser.add_argument("--token", help="Weblate API token")
    args = parser.parse_args(argv)

    token = read_token(args)
    project = ensure_project(args.url, token)
    created = []
    for payload in build_components():
        component = ensure_component(args.url, token, payload)
        created.append({"slug": component["slug"], "name": component["name"], "filemask": component["filemask"]})
        print(json.dumps(created[-1], ensure_ascii=False), flush=True)

    print(json.dumps({"project": project["slug"], "components": len(created)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
