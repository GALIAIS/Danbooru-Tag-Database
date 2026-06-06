# Weblate Component Reference

Use these masks when creating Weblate components:

```text
filemask: po/taxonomy/*.po

filemask: po/tags/_symbols/*.po

filemask: po/tags/0/*.po
...
filemask: po/tags/9/*.po

filemask: po/tags/a/*.po
...
filemask: po/tags/z/*.po
```

Each component includes `en.po` as the source-language file and `zh-CN.po` as
the Chinese translation file. Do not configure a `.pot` template for Weblate PO
components.

Use `tools/weblate_setup.py` to create the project and all 38 components.

After a full export, this repository is ready to connect to Weblate.
