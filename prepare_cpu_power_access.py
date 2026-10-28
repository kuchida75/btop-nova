"""Prepare a per-group udev rule for CPU package energy read access.

Run as your normal user. Only the requested output directory is written;
install.sh is the explicit administrator step. No btop settings change.
"""
import argparse
import grp
import hashlib
import os
import pathlib
import re
import shlex
import subprocess

RULE_NAME = '99-nova-btop-cpu-power.rules'
MARKER = '# Nova btop CPU package energy read access'


def rules_for(group):
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]*\$?', group):
        raise ValueError('Group name is not suitable for a udev command')
    return (MARKER + '\n'
            '# Read access only: package energy, never limits or other controls.\n'
            'ACTION=="add|change", SUBSYSTEM=="powercap", '
            'KERNEL=="intel-rapl:*|amd-rapl:*", ATTR{name}=="package-*", '
            f'RUN+="/usr/bin/chgrp {group} /sys%p/energy_uj", '
            'RUN+="/usr/bin/chmod g+r /sys%p/energy_uj"\n')


def installer_for(group, digest):
    rules_for(group)
    return '''#!/bin/sh
# Nova btop CPU package energy read access: explicit administrator setup.
set -eu
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
[ "$(id -u)" -eq 0 ] || { echo 'Run this installer with sudo.' >&2; exit 1; }
rule_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
rule_file="$rule_dir/99-nova-btop-cpu-power.rules"
target=/etc/udev/rules.d/99-nova-btop-cpu-power.rules
access_group='@GROUP@'
expected='@DIGEST@'
[ "$(sha256sum "$rule_file" | cut -d ' ' -f 1)" = "$expected" ] || { echo 'Prepared rule changed; regenerate it before installing.' >&2; exit 1; }
getent group "$access_group" >/dev/null
udevadm verify "$rule_file"
if [ -L "$target" ]; then
    echo 'Existing rule is a symlink; preserving it.' >&2; exit 1
fi
if [ -e "$target" ]; then
    grep -Fxq '# Nova btop CPU package energy read access' "$target" || { echo 'Existing unmanaged rule preserved.' >&2; exit 1; }
    if ! cmp -s "$rule_file" "$target"; then
        mkdir -p /var/backups/nova-btop-cpu-power
        cp -p "$target" "/var/backups/nova-btop-cpu-power/$(date +%Y%m%d-%H%M%S)-$$.rules"
    fi
fi
counter_paths=''
for zone in /sys/class/powercap/intel-rapl:* /sys/class/powercap/intel-rapl/intel-rapl:* /sys/class/powercap/amd-rapl:* /sys/class/powercap/amd-rapl/amd-rapl:*; do
    [ -r "$zone/name" ] || continue
    case "$(cat "$zone/name")" in
        package-*)
            counter=$(readlink -f "$zone/energy_uj")
            [ -f "$counter" ] || continue
            case " $counter_paths " in
                *" $counter "*) ;;
                *) counter_paths="$counter_paths $counter" ;;
            esac
            ;;
    esac
done
[ -n "$counter_paths" ] || { echo 'No RAPL package energy counters found.' >&2; exit 1; }
mkdir -p /etc/udev/rules.d
staged=$(mktemp /etc/udev/rules.d/.nova-btop-power.XXXXXX)
test_active=0
restore_access() {
    if [ "$test_active" -eq 1 ]; then
        for counter in $counter_paths; do
            chgrp "$access_group" "$counter" || true
            chmod g+r "$counter" || true
        done
    fi
    rm -f "$staged"
}
trap restore_access EXIT
trap 'exit 130' INT
trap 'exit 143' HUP TERM
install -o root -g root -m 0644 "$rule_file" "$staged"
mv -T "$staged" "$target"
udevadm control --reload-rules
# Recreate boot-time ownership, then prove udev restores access. Only file
# permissions change; energy and CPU limits are never written.
test_active=1
for counter in $counter_paths; do
    chgrp 0 "$counter"
    chmod g-r "$counter"
    udevadm trigger --action=change "${counter%/energy_uj}"
done
udevadm settle --timeout=15
for counter in $counter_paths; do
    actual_group=$(stat -c %G "$counter")
    mode=$(stat -c %a "$counter")
    [ "$actual_group" = "$access_group" ] && [ "$((0$mode & 040))" -ne 0 ] || {
        echo 'udev did not restore access; current read access will be restored.' >&2; exit 1
    }
    stat -c '%A %U:%G %n' "$counter"
done
test_active=0
printf '%s\\n' 'PASS: udev restored CPU package read access after a boot-permission simulation.'
printf '%s\\n' "Installed $target. Future RAPL package add/change events use this rule."
'''.replace('@GROUP@', group).replace('@DIGEST@', digest)


def prepare(directory, group):
    directory = pathlib.Path(directory).resolve()
    rule = rules_for(group)
    installer = installer_for(group, hashlib.sha256(rule.encode()).hexdigest())
    directory.mkdir(parents=True, exist_ok=True)
    outputs = ((directory / RULE_NAME, rule, 0o644), (directory / 'install.sh', installer, 0o755))
    for path, text, mode in outputs:
        if path.is_symlink():
            raise ValueError('Refusing to overwrite an output symlink')
        if path.exists() and path.read_text() != text:
            raise ValueError('Output already differs; choose a fresh output directory')
    for path, text, mode in outputs:
        path.write_text(text)
        path.chmod(mode)
    subprocess.run(['sh', '-n', str(directory / 'install.sh')], check=True)
    subprocess.run(['udevadm', 'verify', str(directory / RULE_NAME)], check=True)
    return directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    parser.add_argument('--group', default=grp.getgrgid(os.getgid()).gr_name)
    args = parser.parse_args()
    if os.geteuid() == 0:
        parser.error("Prepare as your normal user; only install.sh needs sudo")
    grp.getgrnam(args.group)
    directory = prepare(args.output, args.group)
    print('Prepared rule and installer:', directory)
    print('Review both files, then run on the target PC:')
    print('sudo sh ' + shlex.quote(str(directory / 'install.sh')))
    print('The selected group receives RAPL package energy read access only.')


if __name__ == '__main__':
    main()
