# Weblate Component Reference

Use these masks when creating Weblate components:

```text
filemask: po/taxonomy/*.po
template: po/taxonomy/taxonomy.pot

filemask: po/tags/_symbols/*.po
template: po/tags/_symbols/_symbols.pot

filemask: po/tags/0/*.po
template: po/tags/0/0.pot
...
filemask: po/tags/9/*.po
template: po/tags/9/9.pot

filemask: po/tags/a/*.po
template: po/tags/a/a.pot
...
filemask: po/tags/z/*.po
template: po/tags/z/z.pot
```

Use `tools/weblate_setup.py` to create the project and all 38 components.

After a full export, this repository is ready to connect to Weblate.
