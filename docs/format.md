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

## `po/tags/<group>/<group>.pot` and `po/tags/<group>/<locale>.po`

Tag PO files are grouped by the first normalized tag character:

- `_symbols`
- `0` through `9`
- `a` through `z`

This keeps Weblate to 37 tag components instead of one component per JSONL
shard. A Weblate component file mask should look like `po/tags/a/*.po`; the
template should be `po/tags/a/a.pot`; the `*` is the locale code.

The `.pot` file is the English source template. Locale `.po` files such as
`zh-CN.po` hold translations.

Each PO entry uses:

- `msgctxt`: `tag:<tag_name>:primary` for the first primary label.
- `msgid`: original Danbooru tag name.
- `msgstr`: translated label.
- `#.` comments: category, taxonomy id, safety, post count, aliases.

Additional primary labels use `msgctxt` `tag:<tag_name>:primary:<index>`.
Aliases use `msgctxt` `tag:<tag_name>:alias:<index>`.

## `data/taxonomy/taxonomy.jsonl`

Each line is one taxonomy node. The `id` field is the stable key referenced by
tag records.

## `po/taxonomy/taxonomy.pot` and `po/taxonomy/<locale>.po`

Taxonomy translations use context keys:

- `taxonomy:<taxonomy_id>:label`
- `taxonomy:<taxonomy_id>:description`

`msgid` is the English label or description, and `msgstr` is the translated text.

## Weblate Components

Recommended components:

- `tags-a` through `tags-z`, `tags-0` through `tags-9`, and `tags-symbols`:
  file masks `po/tags/<group>/*.po`, templates `po/tags/<group>/<group>.pot`
- `taxonomy`: file mask `po/taxonomy/*.po`, template `po/taxonomy/taxonomy.pot`

The source language is English-like tag text from Danbooru. For the initial
repository, `zh-CN` can be imported as the first translated locale.
