#!/bin/sh
# Compile translations and package the plugin; --install also installs it into calibre.
set -eu
cd "$(dirname "$0")"
LC_ALL=C.UTF-8 xgettext --from-code=UTF-8 -L Python --keyword=_ --keyword=ngettext:1,2 \
    --no-wrap --no-location --package-name='AI metadata' -o translations/messages.pot ./*.py
for po in translations/*.po; do
    msgfmt --check-format -o "${po%.po}.mo" "$po"
done
rm -f ai_metadata.zip
zip -q ai_metadata.zip ./*.py plugin-import-name-ai_metadata.txt translations/*.mo
if [ "${1:-}" = --install ]; then
    calibre-customize -a ai_metadata.zip
fi
