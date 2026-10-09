"""Install Nova btop as an isolated user command; retain the packaged fallback."""
import argparse, hashlib, json, os, pathlib, re, shlex, shutil, subprocess, time

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--prefix',type=pathlib.Path,default=pathlib.Path.home()/'.local')
parser.add_argument('--bashrc',type=pathlib.Path,default=pathlib.Path.home()/'.bashrc')
args=parser.parse_args()
source=pathlib.Path(__file__).resolve().parent
prefix=args.prefix.resolve(); bashrc=args.bashrc.resolve()
binary=source/'bin/btop'
version=subprocess.check_output([str(binary),'--version'],text=True).strip().split()[-1]
assert re.fullmatch(r'[0-9a-zA-Z._-]+',version),version
digest=hashlib.sha256(binary.read_bytes()).hexdigest()
install=prefix/'share/btop-nova'; release=install/'releases'/f'{version}-{digest[:12]}'
command=prefix/'bin/btop'
marker='# Nova btop user command'
begin='# BEGIN NOVA BTOP'; end='# END NOVA BTOP'
old_bashrc=bashrc.read_text() if bashrc.exists() else ''
if re.search(r'^\s*alias\s+btop=',re.sub(r'# BEGIN NOVA BTOP.*?# END NOVA BTOP\n?', '',old_bashrc,flags=re.S),flags=re.M):
    raise SystemExit('An existing btop alias must be resolved before installation.')
if command.exists() or command.is_symlink():
    if command.is_symlink() or marker not in command.read_text(errors='replace'):
        raise SystemExit(f'An unrelated command already exists at {command}; preserving it.')
backups=install/'backups';backups.mkdir(parents=True,exist_ok=True)
backup=backups/f'bashrc-{time.time_ns()}'
if bashrc.exists():shutil.copy2(bashrc,backup)
(release/'bin').mkdir(parents=True,exist_ok=True)
installed_binary=release/'bin/btop'
if not installed_binary.exists():
    shutil.copy2(binary,installed_binary)
elif hashlib.sha256(installed_binary.read_bytes()).hexdigest()!=digest:
    raise SystemExit('The existing versioned binary has unexpected content; preserving it.')
shutil.copy2(source/'NOVA.txt',release/'NOVA.txt')
config=install/'config/btop';config.mkdir(parents=True,exist_ok=True)
if not (config/'btop.conf').exists():
    default=source/'packaging/default.conf'
    shutil.copy2(default if default.exists() else source/'nova-config/btop/btop.conf',config/'btop.conf')
# Keep the upstream relative theme lookup inside each versioned release.
for themes in (source/'share/btop/themes',source/'themes'):
    if themes.is_dir():
        shutil.copytree(themes,release/'share/btop/themes',dirs_exist_ok=True)
        break
# Enable new preferences once, preserving later choices across upgrades.
config_file=config/'btop.conf'
config_text=config_file.read_text()
# Remove the retired grid preference; retain the normal CPU graph choices.
config_text=re.sub(r'^cpu_logical_graphs\s*=.*\n?', '', config_text, flags=re.M)
# Apply the requested swap-display change once, alongside the new layout.
# Subsequent upgrades keep the user's choices, including re-enabled swap.
if not re.search(r'^nova_layout\s*=',config_text,flags=re.M):
    for key in ('show_swap', 'swap_disk'):
        line=f'{key} = False'
        config_text=re.sub(r'^'+key+r'\s*=.*$',line,config_text,flags=re.M) if re.search(r'^'+key+r'\s*=',config_text,flags=re.M) else config_text+'\n'+line+'\n'
new_preferences = {
    'show_zram': ('True', 'Zram compression, actual RAM cost and net savings; Shift+Z toggles.'),
    'nova_layout': ('True', 'More GPU height, compact memory and a full-width bottom mount table.'),
    'proc_mounts': ('True', 'Live local mount table below processes; Shift+M toggles.'),
    'show_boot_disks': ('False', 'Show mounted boot/EFI partitions; Shift+B toggles.'),
    'gpu_always_visible': ('True', 'Keep the first detected GPU panel visible across presets.'),
    'gpu_nvtop_graph': ('True', 'Coloured GPU/VRAM/clock histories; Shift+N toggles.'),
    'gpu_processes': ('True', 'GPU processes below the chart; Shift+U toggles.'),
    'gpu_split_vram': ('True', 'GPU load above, allocated VRAM histogram below; Shift+V toggles.'),
}
for key, (value, description) in new_preferences.items():
    if not re.search(r'^'+key+r'\s*=',config_text,flags=re.M):
        config_text=config_text.rstrip()+f'\n\n#* {description}\n{key} = {value}\n'
config_file.write_text(config_text)
# Build the stable command completely before publishing it by rename.
launcher=f'''#!/bin/sh
{marker}
set -eu
export XDG_CONFIG_HOME={shlex.quote(str(install/'config'))}
sed -i 's/^io_mode = .*/io_mode = False/' "$XDG_CONFIG_HOME/btop/btop.conf"
sed -i '/^cpu_logical_graphs[[:space:]]*=/d' "$XDG_CONFIG_HOME/btop/btop.conf"
if ! grep -q '^show_zram[[:space:]]*=' "$XDG_CONFIG_HOME/btop/btop.conf"; then
    printf '\\n#* Zram compression and actual RAM cost.\\nshow_zram = True\\n' >> "$XDG_CONFIG_HOME/btop/btop.conf"
fi
if ! grep -q '^nova_layout[[:space:]]*=' "$XDG_CONFIG_HOME/btop/btop.conf"; then
    sed -i -e 's/^show_swap = .*/show_swap = False/' -e 's/^swap_disk = .*/swap_disk = False/' "$XDG_CONFIG_HOME/btop/btop.conf"
    printf '\\n#* More GPU height, compact memory and a full-width mount table.\\nnova_layout = True\\n' >> "$XDG_CONFIG_HOME/btop/btop.conf"
fi
if ! grep -q '^proc_mounts[[:space:]]*=' "$XDG_CONFIG_HOME/btop/btop.conf"; then
    printf '\\n#* Live local mount table below processes.\\nproc_mounts = True\\n' >> "$XDG_CONFIG_HOME/btop/btop.conf"
fi
if ! grep -q '^gpu_always_visible[[:space:]]*=' "$XDG_CONFIG_HOME/btop/btop.conf"; then
    printf '\\n#* Keep the first detected GPU panel visible.\\ngpu_always_visible = True\\n' >> "$XDG_CONFIG_HOME/btop/btop.conf"
fi
if ! grep -q '^gpu_nvtop_graph[[:space:]]*=' "$XDG_CONFIG_HOME/btop/btop.conf"; then
    printf '\\n#* Coloured GPU/VRAM/clock histories.\\ngpu_nvtop_graph = True\\n' >> "$XDG_CONFIG_HOME/btop/btop.conf"
fi
if ! grep -q '^gpu_processes[[:space:]]*=' "$XDG_CONFIG_HOME/btop/btop.conf"; then
    printf '\\n#* GPU processes below the chart.\\ngpu_processes = True\\n' >> "$XDG_CONFIG_HOME/btop/btop.conf"
fi
exec {shlex.quote(str(release/'bin/btop'))} "$@"
'''
command.parent.mkdir(parents=True,exist_ok=True)
staged=command.with_name('.btop-nova-staged');staged.write_text(launcher);staged.chmod(0o755);staged.replace(command)
text=re.sub(r'# BEGIN NOVA BTOP.*?# END NOVA BTOP\n?', '',old_bashrc,flags=re.S)
new_bashrc=text.rstrip()+f'\n\n{begin}\nalias btop={shlex.quote(str(command))}\n{end}\n'
if new_bashrc!=old_bashrc:
    bashrc.write_text(new_bashrc)
manifest=dict(version=version,binary_sha256=digest,release=str(release),command=str(command),bashrc=str(bashrc),bashrc_backup=str(backup),packaged_fallback='/usr/bin/btop')
(install/'installation.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest,indent=2))
