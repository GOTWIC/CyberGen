#!/bin/bash
# Runs one vehicle script in Blender, one job at a time on this machine.
#
#   vehicles/blender.sh vehicles/cars/vanta_r.py --out DIR --preview
#
# Several sessions share this Mac, so every vehicle build goes through this wrapper: it
# takes a lock ($HOME/.cache/cybergen/blender.lock, a directory made atomically, with the
# holder's process ids inside), waits while another build holds it, takes over a lock whose
# holder is dead, and lets go on exit, error or interrupt.
# BLENDER=/path/to/blender picks another Blender.

BL="${BLENDER:-/Applications/Blender 5.2.app/Contents/MacOS/Blender}"
LOCK="$HOME/.cache/cybergen/blender.lock"

if [ $# -lt 1 ]; then
    echo "usage: vehicles/blender.sh SCRIPT.py [--out DIR] [--preview] [--sheet] [...]" >&2
    exit 2
fi
if [ ! -x "$BL" ]; then
    echo "blender.sh: no Blender at $BL (set BLENDER)" >&2
    exit 2
fi
script="$1"
shift
mkdir -p "$(dirname "$LOCK")"

alive() {       # is any process named in the lock still running?
    local p
    for p in $(cat "$LOCK/pid" 2>/dev/null); do
        kill -0 "$p" 2>/dev/null && return 0
    done
    return 1
}

mine=0
child=""
release() {
    [ -n "$child" ] && kill "$child" 2>/dev/null
    [ "$mine" = 1 ] && rm -rf "$LOCK"
    mine=0
}
trap release EXIT
trap 'release; exit 130' INT TERM HUP

waited=0
dead=0
until mkdir "$LOCK" 2>/dev/null; do
    if alive; then
        dead=0
    else
        dead=$((dead + 1))
    fi
    # dead twice in a row (a new holder gets a moment to write its ids): the lock is stale,
    # and one waiter at a time checks again and clears it
    if [ "$dead" -ge 2 ]; then
        if mkdir "$LOCK.break" 2>/dev/null; then
            alive || { echo "blender.sh: clearing a stale lock" >&2; rm -rf "$LOCK"; }
            rmdir "$LOCK.break"
            dead=0
            continue
        elif [ "$dead" -ge 20 ]; then
            rmdir "$LOCK.break" 2>/dev/null
        fi
    fi
    if [ $((waited % 30)) = 0 ]; then
        echo "blender.sh: waiting for another Blender job (pid $(cat "$LOCK/pid" 2>/dev/null | tr '\n' ' '))" >&2
    fi
    sleep 3
    waited=$((waited + 3))
done
mine=1
echo $$ > "$LOCK/pid"

"$BL" -b --python-exit-code 1 -P "$script" -- "$@" &
child=$!
echo "$child" >> "$LOCK/pid"
wait "$child"
rc=$?
child=""
exit $rc
