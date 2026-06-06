# Text Database Format

## Why This Layout

Weblate should edit translation units, not SQLite rows. This repository separates
source structure from translations:

- JSONL is used for structured database records because it is stable in Git,
  streamable for one million tags, and easy to review line by line.
- Gettext PO is used for translations because Weblate has first-class support for
  PO files, translator comments, message context, fuzzy states, and plural-safe
  tooling.

## `data/tags/*.jsonl`

Each line is one tag record. Files are sharded by normalized tag prefix to keep
Git diffs and editor performance manageable.

Required fields:

- `name`: Danbooru tag name.
- `id`: Danbooru tag id when known.
- `category`: Danbooru numeric category.
- `post_count`: current post count.
- `taxonomy_id`: finest taxonomy leaf id.
- `is_nsfw`: boolean.
- `safety_scope`: `sfw`, `mixed`, `nsfw`, or `unknown`.

Optional fields preserve classifier provenance and sync metadata.

## `po/tags/<locale>/*.po`

Each PO entry uses:

- `msgctxt`: `tag:<tag_name>:primary` for primary label.
- `msgid`: original Danbooru tag name.
- `msgstr`: translated label.
- `#.` comments: category, taxonomy id, safety, post count, aliases.

Aliases use `msgctxt` `tag:<tag_name>:alias:<index>`.

## `data/taxonomy/taxonomy.jsonl`

Each line is one taxonomy node. The `id` field is the stable key referenced by
tag records.

## `po/taxonomy/<locale>.po`

Taxonomy translations use context keys:

- `taxonomy:<taxonomy_id>:label`
- `taxonomy:<taxonomy_id>:description`

`msgid` is the English label or description, and `msgstr` is the translated text.

## Weblate Components

Recommended components:

- `tags`: file mask `po/tags/*/*.po`
- `taxonomy`: file mask `po/taxonomy/*.po`

The source language is English-like tag text from Danbooru. For the initial
repository, `zh-CN` can be imported as the first translated locale.
