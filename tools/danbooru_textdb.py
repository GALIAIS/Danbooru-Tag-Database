#!/usr/bin/env python3
"""Convert GALIAIS Danbooru dictionary SQLite databases to text files and back."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


NOW = lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
HEADER_RE = re.compile(r'^(msgctxt|msgid|msgstr)\s+"(.*)"$')
SAFE_SHARD_RE = re.compile(r"[^a-z0-9_]+")


def normalize_label(value: str) -> str:
    return str(value or "").strip().casefold()


def normalize_name(value: str) -> str:
    return str(value or "").strip().lower()


def json_dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def json_line(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def po_escape(value: str) -> str:
    text = str(value or "")
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def po_unescape(value: str) -> str:
    out = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        i += 1
        if i >= len(value):
            out.append("\\")
            break
        esc = value[i]
        if esc == "n":
            out.append("\n")
        elif esc in {'"', "\\"}:
            out.append(esc)
        else:
            out.append(esc)
        i += 1
    return "".join(out)


def po_quote(value: str) -> str:
    return f'"{po_escape(value)}"'


def shard_key(name: str, shard_len: int = 2) -> str:
    normalized = normalize_name(name).replace(" ", "_")
    if not normalized:
        return "__"
    first = normalized[0]
    if not first.isalnum():
        return "_symbols"
    raw = normalized[:shard_len].ljust(shard_len, "_")
    safe = SAFE_SHARD_RE.sub("_", raw).strip("_")
    return safe[:shard_len].ljust(shard_len, "_") if safe else "_symbols"


def clear_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    ensure_dir(path)


def remove_file(path: Path) -> None:
    if path.exists():
        path.unlink()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def connect_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def connect_rw(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def table_names(conn: sqlite3.Connection) -> set[str]:
    return {row["name"] for row in conn.execute("select name from sqlite_master where type='table'")}


def require_tables(conn: sqlite3.Connection, names: Iterable[str]) -> None:
    existing = table_names(conn)
    missing = [name for name in names if name not in existing]
    if missing:
        raise RuntimeError(f"database missing tables: {', '.join(missing)}")


def rows(conn: sqlite3.Connection, sql: str, params=()):
    for row in conn.execute(sql, params):
        yield dict(row)


def write_jsonl(path: Path, records: Iterable[dict]) -> int:
    ensure_dir(path.parent)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json_line(record))
            handle.write("\n")
            count += 1
    return count


def read_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            text = line.strip()
            if not text:
                continue
            try:
                yield json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSONL: {exc}") from exc


def export_metadata(conn: sqlite3.Connection, repo: Path) -> int:
    if "dictionary_metadata" not in table_names(conn):
        return 0
    remove_file(repo / "data" / "metadata.jsonl")
    return write_jsonl(
        repo / "data" / "metadata.jsonl",
        rows(conn, "select key, value, namespace, source, created_at, updated_at from dictionary_metadata order by namespace, key"),
    )


def export_taxonomy(conn: sqlite3.Connection, repo: Path) -> int:
    if "tag_taxonomy" not in table_names(conn):
        return 0
    remove_file(repo / "data" / "taxonomy" / "taxonomy.jsonl")
    return write_jsonl(
        repo / "data" / "taxonomy" / "taxonomy.jsonl",
        rows(
            conn,
            """
            select id, danbooru_category, domain, facet, group_key, leaf_key,
                   label_en, safety_scope, prompt_role, is_selectable, multi_select,
                   max_select, sort_order, created_at, updated_at
            from tag_taxonomy
            order by sort_order, id
            """,
        ),
    )


def tag_record(row: dict) -> dict:
    keys = [
        "id",
        "name",
        "normalized_name",
        "category",
        "post_count",
        "semantic_category_key",
        "semantic_category_source",
        "semantic_category_confidence",
        "semantic_category_updated_at",
        "created_at",
        "updated_at",
        "last_synced_at",
        "taxonomy_id",
        "taxonomy_source",
        "taxonomy_confidence",
        "is_nsfw",
        "taxonomy_domain",
        "taxonomy_facet",
        "taxonomy_group",
        "taxonomy_leaf",
        "safety_scope",
    ]
    return {key: row.get(key) for key in keys}


def export_tags(conn: sqlite3.Connection, repo: Path, limit: int = 0) -> int:
    clear_dir(repo / "data" / "tags")
    sql = """
        select * from danbooru_tags
        order by normalized_name, name
    """
    if limit:
        sql += " limit ?"
        iterator = rows(conn, sql, (limit,))
    else:
        iterator = rows(conn, sql)

    handles = {}
    count = 0
    try:
        for row in iterator:
            key = shard_key(row["name"])
            path = repo / "data" / "tags" / f"{key}.jsonl"
            if key not in handles:
                ensure_dir(path.parent)
                handles[key] = path.open("w", encoding="utf-8", newline="\n")
            handles[key].write(json_line(tag_record(row)))
            handles[key].write("\n")
            count += 1
    finally:
        for handle in handles.values():
            handle.close()
    return count


def localization_map(conn: sqlite3.Connection, locale: str, limit: int = 0) -> dict[str, list[dict]]:
    sql = """
        select l.*
        from danbooru_tag_localizations l
        join danbooru_tags t on t.name = l.tag_name
        where l.locale = ?
        order by t.normalized_name, l.tag_name, case l.kind when 'primary' then 0 else 1 end, l.id
    """
    params: tuple = (locale,)
    if limit:
        sql += " limit ?"
        params = (locale, limit * 4)
    output: dict[str, list[dict]] = {}
    for row in rows(conn, sql, params):
        output.setdefault(row["tag_name"], []).append(row)
    return output


def write_po_header(handle, *, project: str, language: str) -> None:
    now = NOW()
    header_lines = [
        'msgid ""',
        'msgstr ""',
        f'"Project-Id-Version: {po_escape(project)}\\n"',
        '"Report-Msgid-Bugs-To: \\n"',
        f'"POT-Creation-Date: {po_escape(now)}\\n"',
        f'"PO-Revision-Date: {po_escape(now)}\\n"',
        '"Last-Translator: \\n"',
        '"Language-Team: \\n"',
        f'"Language: {po_escape(language)}\\n"',
        '"MIME-Version: 1.0\\n"',
        '"Content-Type: text/plain; charset=UTF-8\\n"',
        '"Content-Transfer-Encoding: 8bit\\n"',
        '"Generated-By: GALIAIS Danbooru textdb\\n"',
        "",
    ]
    handle.write("\n".join(header_lines))
    handle.write("\n")


def write_po_entry(handle, *, context: str, msgid: str, msgstr: str, comments: list[str] | None = None) -> None:
    handle.write("\n")
    for comment in comments or []:
        handle.write(f"#. {comment}\n")
    handle.write(f"msgctxt {po_quote(context)}\n")
    handle.write(f"msgid {po_quote(msgid)}\n")
    handle.write(f"msgstr {po_quote(msgstr)}\n")


def export_tag_po(conn: sqlite3.Connection, repo: Path, locale: str, limit: int = 0) -> int:
    clear_dir(repo / "po" / "tags" / locale)
    locs = localization_map(conn, locale, limit=limit)
    tag_sql = """
        select name, normalized_name, category, post_count, taxonomy_id, is_nsfw, safety_scope
        from danbooru_tags
        order by normalized_name, name
    """
    params = ()
    if limit:
        tag_sql += " limit ?"
        params = (limit,)

    handles = {}
    count = 0
    try:
        for tag in rows(conn, tag_sql, params):
            key = shard_key(tag["name"])
            path = repo / "po" / "tags" / locale / f"{key}.po"
            if key not in handles:
                ensure_dir(path.parent)
                handle = path.open("w", encoding="utf-8", newline="\n")
                write_po_header(handle, project="GALIAIS Danbooru tags", language=locale)
                handles[key] = handle
            handle = handles[key]
            tag_locs = locs.get(tag["name"], [])
            primary = next((loc for loc in tag_locs if loc.get("kind") == "primary"), None)
            aliases = [loc for loc in tag_locs if loc.get("kind") == "alias"]
            comments = [
                f"danbooru-category: {tag.get('category')}",
                f"taxonomy-id: {tag.get('taxonomy_id') or ''}",
                f"safety: {'nsfw' if tag.get('is_nsfw') else tag.get('safety_scope') or 'sfw'}",
                f"post-count: {tag.get('post_count')}",
            ]
            if aliases:
                comments.append("aliases: " + ", ".join(alias.get("label", "") for alias in aliases if alias.get("label")))
            write_po_entry(
                handle,
                context=f"tag:{tag['name']}:primary",
                msgid=tag["name"],
                msgstr=primary.get("label", "") if primary else "",
                comments=comments,
            )
            count += 1
            for index, alias in enumerate(aliases, 1):
                write_po_entry(
                    handle,
                    context=f"tag:{tag['name']}:alias:{index}",
                    msgid=tag["name"],
                    msgstr=alias.get("label", ""),
                    comments=[f"alias-of: {tag['name']}", f"source: {alias.get('source', '')}"],
                )
                count += 1
    finally:
        for handle in handles.values():
            handle.close()
    return count


def export_taxonomy_po(conn: sqlite3.Connection, repo: Path, locale: str) -> int:
    path = repo / "po" / "taxonomy" / f"{locale}.po"
    remove_file(path)
    ensure_dir(path.parent)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        write_po_header(handle, project="GALIAIS Danbooru taxonomy", language=locale)
        for row in rows(conn, "select * from tag_taxonomy order by sort_order, id"):
            write_po_entry(
                handle,
                context=f"taxonomy:{row['id']}:label",
                msgid=row.get("label_en") or row["id"],
                msgstr=row.get("label_zh", "") if locale.lower().startswith("zh") else "",
                comments=[
                    f"id: {row['id']}",
                    f"path: {row['domain']}.{row['facet']}.{row['group_key']}.{row['leaf_key']}",
                    f"safety: {row['safety_scope']}",
                ],
            )
            count += 1
            if row.get("description"):
                write_po_entry(
                    handle,
                    context=f"taxonomy:{row['id']}:description",
                    msgid=row["description"],
                    msgstr="",
                    comments=[f"id: {row['id']}"],
                )
                count += 1
    return count


@dataclass
class PoEntry:
    context: str
    msgid: str
    msgstr: str


def parse_po(path: Path) -> list[PoEntry]:
    entries: list[PoEntry] = []
    current: dict[str, str] = {}
    active: str | None = None

    def flush():
        if current.get("msgid", None) == "":
            current.clear()
            return
        if "msgctxt" in current and "msgid" in current:
            entries.append(PoEntry(current.get("msgctxt", ""), current.get("msgid", ""), current.get("msgstr", "")))
        current.clear()

    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.rstrip("\n")
            if not line:
                flush()
                active = None
                continue
            if line.startswith("#"):
                continue
            match = HEADER_RE.match(line)
            if match:
                active = match.group(1)
                current[active] = po_unescape(match.group(2))
                continue
            if active and line.startswith('"') and line.endswith('"'):
                current[active] = current.get(active, "") + po_unescape(line[1:-1])
                continue
        flush()
    return entries


def collect_tag_translations(repo: Path) -> dict[tuple[str, str], list[tuple[str, str]]]:
    result: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for locale_dir in sorted((repo / "po" / "tags").glob("*")):
        if not locale_dir.is_dir():
            continue
        locale = locale_dir.name
        for path in sorted(locale_dir.glob("*.po")):
            for entry in parse_po(path):
                parts = entry.context.split(":")
                if len(parts) < 3 or parts[0] != "tag":
                    continue
                tag_name = parts[1]
                kind = parts[2]
                if not entry.msgstr.strip():
                    continue
                result.setdefault((tag_name, locale), []).append((kind, entry.msgstr.strip()))
    return result


def collect_taxonomy_translations(repo: Path) -> dict[tuple[str, str], dict[str, str]]:
    result: dict[tuple[str, str], dict[str, str]] = {}
    taxonomy_dir = repo / "po" / "taxonomy"
    if not taxonomy_dir.exists():
        return result
    for path in sorted(taxonomy_dir.glob("*.po")):
        locale = path.stem
        for entry in parse_po(path):
            parts = entry.context.split(":")
            if len(parts) != 3 or parts[0] != "taxonomy":
                continue
            taxonomy_id, field = parts[1], parts[2]
            if field not in {"label", "description"}:
                continue
            if not entry.msgstr.strip():
                continue
            result.setdefault((taxonomy_id, locale), {})[field] = entry.msgstr.strip()
    return result


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        create table danbooru_tags (
          id integer primary key,
          name text not null unique,
          normalized_name text not null default '',
          category integer,
          post_count integer not null default 0,
          semantic_category_key text,
          semantic_category_source text,
          semantic_category_confidence real,
          semantic_category_updated_at text,
          created_at text,
          updated_at text not null,
          last_synced_at text not null,
          taxonomy_id text,
          taxonomy_source text default 'textdb',
          taxonomy_confidence real,
          is_nsfw integer not null default 0,
          taxonomy_domain text,
          taxonomy_facet text,
          taxonomy_group text,
          taxonomy_leaf text,
          safety_scope text not null default 'unknown'
        );
        create table danbooru_tag_localizations (
          id integer primary key autoincrement,
          tag_name text not null,
          locale text not null default 'zh-CN',
          label text not null,
          normalized_label text not null,
          kind text not null default 'primary',
          source text not null default 'weblate',
          confidence real,
          manual integer not null default 1,
          created_at text not null,
          updated_at text not null,
          unique(tag_name, locale, label, kind)
        );
        create table tag_taxonomy (
          id text primary key,
          danbooru_category integer not null,
          domain text not null,
          facet text not null,
          group_key text not null,
          leaf_key text not null,
          label_zh text not null default '',
          label_en text not null default '',
          description text not null default '',
          safety_scope text not null default 'sfw',
          prompt_role text not null default 'positive',
          is_selectable integer not null default 1,
          multi_select integer not null default 0,
          max_select integer not null default 1,
          sort_order integer not null default 0,
          created_at text not null,
          updated_at text not null,
          unique(danbooru_category, domain, facet, group_key, leaf_key)
        );
        create table dictionary_metadata (
          key text primary key,
          value text not null default '',
          namespace text not null default 'galiais_textdb',
          source text not null default 'text',
          created_at text not null,
          updated_at text not null
        );
        create table prompt_templates (
          id text primary key,
          name text not null,
          description text not null default '',
          platform text not null default 'a1111',
          positive_template text not null default '',
          negative_template text not null default '',
          is_preset integer not null default 0,
          category text not null default 'general',
          tags text not null default '[]',
          created_at text not null,
          updated_at text not null
        );
        create index idx_danbooru_tags_normalized_name on danbooru_tags(normalized_name);
        create index idx_danbooru_tags_post_count on danbooru_tags(post_count desc, name collate nocase asc);
        create index idx_danbooru_tags_taxonomy on danbooru_tags(taxonomy_id);
        create index idx_danbooru_tags_nsfw on danbooru_tags(is_nsfw);
        create index idx_danbooru_tags_safety_scope on danbooru_tags(safety_scope);
        create index idx_danbooru_tag_localizations_lookup on danbooru_tag_localizations(locale, normalized_label, tag_name);
        create index idx_danbooru_tag_localizations_by_tag_locale on danbooru_tag_localizations(locale, tag_name, manual, kind, updated_at desc);
        """
    )


def import_repo(repo: Path, output: Path) -> dict:
    if output.exists():
        output.unlink()
    conn = connect_rw(output)
    create_schema(conn)
    now = NOW()
    taxonomy_count = 0
    tag_count = 0

    taxonomy_path = repo / "data" / "taxonomy" / "taxonomy.jsonl"
    taxonomy_translations = collect_taxonomy_translations(repo)
    if taxonomy_path.exists():
        for record in read_jsonl(taxonomy_path):
            zh = taxonomy_translations.get((record["id"], "zh-CN"), {})
            conn.execute(
                """
                insert into tag_taxonomy (
                  id, danbooru_category, domain, facet, group_key, leaf_key,
                  label_zh, label_en, description, safety_scope, prompt_role, is_selectable, multi_select,
                  max_select, sort_order, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    int(record.get("danbooru_category") or 0),
                    record.get("domain") or "",
                    record.get("facet") or "",
                    record.get("group_key") or "",
                    record.get("leaf_key") or "",
                    zh.get("label", ""),
                    record.get("label_en") or "",
                    zh.get("description", ""),
                    record.get("safety_scope") or "sfw",
                    record.get("prompt_role") or "positive",
                    int(record.get("is_selectable", 1)),
                    int(record.get("multi_select", 0)),
                    int(record.get("max_select", 1)),
                    int(record.get("sort_order", 0)),
                    record.get("created_at") or now,
                    record.get("updated_at") or now,
                ),
            )
            taxonomy_count += 1

    for path in sorted((repo / "data" / "tags").glob("*.jsonl")):
        for record in read_jsonl(path):
            conn.execute(
                """
                insert into danbooru_tags (
                  id, name, normalized_name, category, post_count,
                  semantic_category_key, semantic_category_source,
                  semantic_category_confidence, semantic_category_updated_at,
                  created_at, updated_at, last_synced_at, taxonomy_id,
                  taxonomy_source, taxonomy_confidence, is_nsfw,
                  taxonomy_domain, taxonomy_facet, taxonomy_group,
                  taxonomy_leaf, safety_scope
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.get("id"),
                    record["name"],
                    record.get("normalized_name") or normalize_name(record["name"]),
                    record.get("category"),
                    int(record.get("post_count") or 0),
                    record.get("semantic_category_key"),
                    record.get("semantic_category_source"),
                    record.get("semantic_category_confidence"),
                    record.get("semantic_category_updated_at"),
                    record.get("created_at") or now,
                    record.get("updated_at") or now,
                    record.get("last_synced_at") or now,
                    record.get("taxonomy_id"),
                    record.get("taxonomy_source") or "textdb",
                    record.get("taxonomy_confidence"),
                    int(bool(record.get("is_nsfw"))),
                    record.get("taxonomy_domain"),
                    record.get("taxonomy_facet"),
                    record.get("taxonomy_group"),
                    record.get("taxonomy_leaf"),
                    record.get("safety_scope") or "unknown",
                ),
            )
            tag_count += 1

    localization_count = 0
    translations = collect_tag_translations(repo)
    for (tag_name, locale), values in translations.items():
        for kind, label in values:
            cursor = conn.execute(
                """
                insert or ignore into danbooru_tag_localizations (
                  tag_name, locale, label, normalized_label, kind,
                  source, confidence, manual, created_at, updated_at
                ) values (?, ?, ?, ?, ?, 'weblate', null, 1, ?, ?)
                """,
                (tag_name, locale, label, normalize_label(label), "primary" if kind == "primary" else "alias", now, now),
            )
            localization_count += cursor.rowcount

    metadata_path = repo / "data" / "metadata.jsonl"
    if metadata_path.exists():
        for record in read_jsonl(metadata_path):
            conn.execute(
                """
                insert or replace into dictionary_metadata
                (key, value, namespace, source, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?)
                """,
                (
                    record["key"],
                    record.get("value") or "",
                    record.get("namespace") or "galiais_textdb",
                    record.get("source") or "text",
                    record.get("created_at") or now,
                    record.get("updated_at") or now,
                ),
            )
    conn.execute(
        """
        insert or replace into dictionary_metadata
        (key, value, namespace, source, created_at, updated_at)
        values ('textdb_generated_by', 'GALIAIS', 'galiais_textdb', 'tool', ?, ?)
        """,
        (now, now),
    )
    conn.commit()
    conn.close()
    return {"tags": tag_count, "taxonomy": taxonomy_count, "localizations": localization_count, "output": str(output)}


def export_repo(db: Path, repo: Path, locales: list[str], limit: int = 0) -> dict:
    conn = connect_ro(db)
    require_tables(conn, ["danbooru_tags", "danbooru_tag_localizations"])
    summary = {
        "tags": export_tags(conn, repo, limit=limit),
        "metadata": export_metadata(conn, repo),
        "taxonomy": export_taxonomy(conn, repo),
        "tag_po_entries": {},
        "taxonomy_po_entries": {},
    }
    for locale in locales:
        summary["tag_po_entries"][locale] = export_tag_po(conn, repo, locale, limit=limit)
        summary["taxonomy_po_entries"][locale] = export_taxonomy_po(conn, repo, locale)
    conn.close()
    return summary


def validate_repo(repo: Path) -> dict:
    errors: list[str] = []
    tag_names: set[str] = set()
    taxonomy_ids: set[str] = set()

    taxonomy_path = repo / "data" / "taxonomy" / "taxonomy.jsonl"
    if taxonomy_path.exists():
        for record in read_jsonl(taxonomy_path):
            if not record.get("id"):
                errors.append(f"{taxonomy_path}: taxonomy record missing id")
            taxonomy_ids.add(record.get("id", ""))
    else:
        errors.append("missing data/taxonomy/taxonomy.jsonl")

    tag_files = sorted((repo / "data" / "tags").glob("*.jsonl"))
    if not tag_files:
        errors.append("missing data/tags/*.jsonl")
    for path in tag_files:
        for record in read_jsonl(path):
            name = record.get("name")
            if not name:
                errors.append(f"{path}: tag record missing name")
                continue
            if name in tag_names:
                errors.append(f"duplicate tag: {name}")
            tag_names.add(name)
            taxonomy_id = record.get("taxonomy_id")
            if taxonomy_id and taxonomy_ids and taxonomy_id not in taxonomy_ids:
                errors.append(f"{path}: unknown taxonomy_id {taxonomy_id} for {name}")
            if record.get("safety_scope") not in {"sfw", "mixed", "nsfw", "unknown", None}:
                errors.append(f"{path}: invalid safety_scope for {name}: {record.get('safety_scope')}")

    for po_path in sorted((repo / "po").rglob("*.po")):
        try:
            parse_po(po_path)
        except Exception as exc:
            errors.append(f"{po_path}: invalid PO: {exc}")

    return {"ok": not errors, "tags": len(tag_names), "taxonomy": len(taxonomy_ids), "errors": errors[:200], "error_count": len(errors)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_export = sub.add_parser("export", help="export SQLite database to text repository")
    p_export.add_argument("--db", required=True, type=Path)
    p_export.add_argument("--repo", required=True, type=Path)
    p_export.add_argument("--locales", nargs="+", default=["zh-CN"])
    p_export.add_argument("--limit", type=int, default=0, help="sample limit for fast tests")

    p_import = sub.add_parser("import", help="build SQLite database from text repository")
    p_import.add_argument("--repo", required=True, type=Path)
    p_import.add_argument("--output", required=True, type=Path)

    p_validate = sub.add_parser("validate", help="validate text repository")
    p_validate.add_argument("--repo", required=True, type=Path)

    args = parser.parse_args(argv)
    if args.command == "export":
        result = export_repo(args.db, args.repo, args.locales, limit=args.limit)
    elif args.command == "import":
        result = import_repo(args.repo, args.output)
    elif args.command == "validate":
        result = validate_repo(args.repo)
    else:
        parser.error("unknown command")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
