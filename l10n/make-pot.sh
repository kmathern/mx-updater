#!/bin/bash

# creates amx-updater.pot file 

PY=(
    $(grep -l -E 'gettext|_\(|_tn\(' ../libexec/mx-updater/*[a-z].py)
    )
    declare -p PY

DESKTOP=(
    ../xdg/mx-updater-autostart.desktop.in
    ../xdg/mx-updater.desktop.in
    )
    declare -p DESKTOP

POLICY=(
    $(ls -1 ../polkit/actions/org.mxlinux.mx-updater.*.policy )
    )
    declare -p POLICY

PKGNAME=mx-updater
POTFILE=mx-updater.pot

touch $POTFILE.pot
echodo() { local run="$1"; shift; echo "$run" "${@@Q}"; "$run" "$@"; }

OPTS="--no-wrap --sort-output --no-location --package-name=$PKGNAME"
echodo xgettext $OPTS -L Python -cTRANSLATORS: -o $POTFILE "${PY[@]}"

OPTS="--no-wrap --join-existing --no-location --package-name=$PKGNAME"
echodo xgettext $OPTS --add-comments -L Desktop -o $POTFILE "${DESKTOP[@]}"
sed -i 's/charset=CHARSET/charset=UTF-8/'  $POTFILE

for P in "${POLICY[@]}"; do
    msgid="$(grep -m1 -oP '<message[^>]*>\K[^<]+' $P)"
    [[ -n $msgid ]] &&  printf '\nmsgid "%s"\nmsgstr ""\n' "$msgid" | tee -a $POTFILE
done

# put addtionaly msgid's into en-extra.pot
EXTRA=en-extra.pot
TEMPO=$EXTRA.tmp

OPTS="--no-wrap --sort-output --no-location --package-name=$PKGNAME"
echodo xgettext $OPTS --add-comments -kComment -L Desktop -o $TEMPO "${DESKTOP[@]}"
sed -i 's/charset=CHARSET/charset=UTF-8/'  $TEMPO

for P in "${POLICY[@]}"; do
    msgid="$(grep -m1 -oP '<message[^>]*>\K[^<]+' $P)"
    [[ -n $msgid ]] &&  printf '\nmsgid "%s"\nmsgstr ""\n' "$msgid" | tee -a $TEMPO
done

msggrep -v --no-wrap -K -e '^MX Updater$' -o $EXTRA $TEMPO
#rm $TEMPO
