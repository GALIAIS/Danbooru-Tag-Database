# Weblate Integration

Target repository:

`https://github.com/GALIAIS/Danbooru-Tag-Database`

## Recommended Weblate Setup

Create one Weblate project for `GALIAIS Danbooru Tag Database`.

Component 1: taxonomy translations

- Version control: Git
- Repository URL: `https://github.com/GALIAIS/Danbooru-Tag-Database.git`
- File format: Gettext PO file
- File mask: `po/taxonomy/*.po`
- Template for new translations: `po/taxonomy/taxonomy.pot`
- Adding new translation: disabled unless template files are added later.

Components 2-38: tag translations

- Version control: same repository, preferably linked to the taxonomy component
  with `weblate://danbooru-tag-database/taxonomy`
- File format: Gettext PO file
- File masks:
  - `po/tags/_symbols/*.po`
  - `po/tags/0/*.po` through `po/tags/9/*.po`
  - `po/tags/a/*.po` through `po/tags/z/*.po`
- Templates:
  - `po/tags/_symbols/_symbols.pot`
  - `po/tags/0/0.pot` through `po/tags/9/9.pot`
  - `po/tags/a/a.pot` through `po/tags/z/z.pot`
- Adding new translation: disabled unless template files are added later.

Do not use one `po/tags/*/*.po` component. Weblate treats `*` as the language
code and rejects the layout because each language contains multiple tag PO
files.

The API setup helper can create the project and all components:

```powershell
python tools/weblate_setup.py `
  --url https://l10n.galiais.org `
  --token-file E:\WorkSpace\ComfyUI-Tools\weblate.txt
```

## Notes

Weblate documentation lists many supported formats, including Gettext PO,
JSON/YAML variants, CSV, Android strings, Qt TS, XLIFF, and more. PO is the best
fit here because it supports message context and translator comments, which are
needed to distinguish tags, aliases, taxonomy labels, and descriptions.

Tag contexts can contain `:` inside the tag name. Tools parse contexts from the
right side, so `tag:<tag>:primary`, `tag:<tag>:primary:<n>`, and
`tag:<tag>:alias:<n>` are all safe for Danbooru tag names.

Do not edit SQLite databases in Weblate. Rebuild SQLite from this repository
after translations or taxonomy files are changed.

Useful docs:

- [File formats](https://docs.weblate.org/zh-cn/latest/formats.html)
- [Gettext PO files](https://docs.weblate.org/zh-cn/latest/formats/gettext.html)
- [Project and component setup](https://docs.weblate.org/zh-cn/latest/admin/projects.html)
