#!/usr/bin/env python3
"""Upload existing zh-CN PO files to Weblate zh_Hans translations."""

from __future__ import annotations

import argparse
import json
import mimetypes
import http.client
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def read_token(args: argparse.Namespace) -> str:
    if args.token:
        return args.token.strip()
    if args.token_file:
        return Path(args.token_file).read_text(encoding="utf-8").strip()
    token = os.environ.get("WEBLATE_TOKEN", "").strip()
    if token:
        return token
    raise SystemExit("missing token: pass --token-file, --token, or WEBLATE_TOKEN")


def api_json(base_url: str, token: str, method: str, path: str, payload: dict[str, Any] | None = None, timeout: int = 120) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Token {token}",
        "Accept": "application/json",
        "User-Agent": "GALIAIS-Danbooru-Weblate-Upload/1.0",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request(base_url.rstrip("/") + path, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else None
    except HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {exc.code} {path}: {body}") from exc


def api_multipart_once(base_url: str, token: str, path: str, file_path: Path, fields: dict[str, str], timeout: int) -> Any:
    boundary = "----galiais-" + uuid.uuid4().hex
    parts: list[bytes] = []
    for key, value in fields.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
        parts.append(str(value).encode("utf-8"))
        parts.append(b"\r\n")
    mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'.encode())
    parts.append(f"Content-Type: {mime}\r\n\r\n".encode())
    parts.append(file_path.read_bytes())
    parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    data = b"".join(parts)
    request = Request(
        base_url.rstrip("/") + path,
        data=data,
        headers={
            "Authorization": f"Token {token}",
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "GALIAIS-Danbooru-Weblate-Upload/1.0",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else None
    except HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {exc.code} {path}: {body}") from exc


def api_multipart(base_url: str, token: str, path: str, file_path: Path, fields: dict[str, str], timeout: int = 600, retries: int = 3) -> Any:
    for attempt in range(retries + 1):
        try:
            return api_multipart_once(base_url, token, path, file_path, fields, timeout)
        except (TimeoutError, ConnectionError, http.client.RemoteDisconnected, http.client.IncompleteRead) as exc:
            if attempt >= retries:
                raise
            time.sleep(2**attempt)
        except RuntimeError as exc:
            text = str(exc)
            if not any(code in text for code in ("HTTP 429", "HTTP 500", "HTTP 502", "HTTP 503", "HTTP 504")) or attempt >= retries:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("multipart upload retry loop exited unexpectedly")


def discover_tag_groups(repo: Path) -> list[str]:
    tags_dir = repo / "po" / "tags"
    if not tags_dir.exists():
        return []
    return sorted(path.name for path in tags_dir.iterdir() if path.is_dir() and (path / "zh-CN.po").exists())


def parse_groups(value: str, available: list[str]) -> list[str]:
    if not value.strip():
        return available
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


def tag_slug(group: str) -> str:
    suffix = "symbols" if group == "_symbols" else re.sub(r"[^a-z0-9-]+", "-", group.lower()).strip("-")
    return f"tags-{suffix}"


def upload_component(base_url: str, token: str, project: str, slug: str, file_path: Path, *, timeout: int, retries: int) -> dict[str, Any]:
    try:
        api_json(base_url, token, "POST", f"/api/components/{project}/{slug}/translations/", {"language_code": "zh_Hans"}, timeout=120)
    except RuntimeError as exc:
        text = str(exc)
        if "already exists" not in text and "already" not in text and "400" not in text:
            raise
    result = api_multipart(
        base_url,
        token,
        f"/api/translations/{project}/{slug}/zh_Hans/file/",
        file_path,
        {
            "method": "replace",
            "conflicts": "replace-translated",
            "author_name": "GALIAIS",
            "author_email": "z67x8c99b@gmail.com",
        },
        timeout=timeout,
        retries=retries,
    )
    return {"slug": slug, "file": str(file_path), "result": result}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--token-file")
    parser.add_argument("--token")
    parser.add_argument("--project", required=True)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--groups", default="")
    parser.add_argument("--include-taxonomy", action="store_true")
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args(argv)

    token = read_token(args)
    uploads = []
    if args.include_taxonomy:
        uploads.append(("taxonomy", args.repo / "po" / "taxonomy" / "zh-CN.po"))
    for group in parse_groups(args.groups, discover_tag_groups(args.repo)):
        uploads.append((tag_slug(group), args.repo / "po" / "tags" / group / "zh-CN.po"))

    results = []
    for slug, path in uploads:
        if not path.exists():
            results.append({"slug": slug, "file": str(path), "error": "missing file"})
            continue
        try:
            result = upload_component(args.url, token, args.project, slug, path, timeout=args.timeout, retries=args.retries)
            results.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
        except Exception as exc:
            error = {"slug": slug, "file": str(path), "error": str(exc)}
            results.append(error)
            print(json.dumps(error, ensure_ascii=False), flush=True)
        time.sleep(args.delay)
    print(json.dumps({"project": args.project, "uploads": len(results)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
