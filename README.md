# Danbooru Tag Database

Text-first source repository for the GALIAIS Danbooru tag dictionary.

The SQLite database is treated as a build artifact. Editable source data lives in
plain text files:

- `data/tags/*.jsonl`: tag metadata, taxonomy assignment, safety flags, counts.
- `data/taxonomy/taxonomy.jsonl`: taxonomy nodes and prompt selection metadata.
- `po/tags/<group>/<locale>.po`: Weblate-managed tag translations.
- `po/taxonomy/<locale>.po`: Weblate-managed taxonomy labels and descriptions.

Use `tools/danbooru_textdb.py` to export from SQLite, validate the text tree,
and rebuild a SQLite database.

Quick sample export:

```powershell
python tools/danbooru_textdb.py export `
  --db E:\WorkSpace\ComfyUI-Tools\danbooru-dictionary.next.db `
  --repo . `
  --locales zh-CN `
  --limit 1000
```

Full export:

```powershell
python tools/danbooru_textdb.py export `
  --db E:\WorkSpace\ComfyUI-Tools\danbooru-dictionary.next.db `
  --repo . `
  --locales zh-CN
```

Rebuild SQLite:

```powershell
python tools/danbooru_textdb.py import `
  --repo . `
  --output danbooru-dictionary.from-text.db
```

Validate:

```powershell
python tools/danbooru_textdb.py validate --repo .
```
