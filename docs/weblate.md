# Weblate Integration

Target repository:

`https://github.com/GALIAIS/Danbooru-Tag-Database`

## Recommended Weblate Setup

Create one Weblate project for `GALIAIS Danbooru Tag Database`.

Component 1: tag translations

- Version control: Git
- Repository URL: `https://github.com/GALIAIS/Danbooru-Tag-Database.git`
- File format: Gettext PO file
- File mask: `po/tags/*/*.po`
- New language: create new file from template is optional after template files
  are generated.

Component 2: taxonomy translations

- Version control: same repository
- File format: Gettext PO file
- File mask: `po/taxonomy/*.po`

## Notes

Weblate documentation lists many supported formats, including Gettext PO,
JSON/YAML variants, CSV, Android strings, Qt TS, XLIFF, and more. PO is the best
fit here because it supports message context and translator comments, which are
needed to distinguish tags, aliases, taxonomy labels, and descriptions.

Do not edit SQLite databases in Weblate. Rebuild SQLite from this repository
after translations or taxonomy files are changed.

Useful docs:

- [File formats](https://docs.weblate.org/zh-cn/latest/formats.html)
- [Gettext PO files](https://docs.weblate.org/zh-cn/latest/formats/gettext.html)
- [Project and component setup](https://docs.weblate.org/zh-cn/latest/admin/projects.html)
