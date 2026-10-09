"""Stage an upgrade and verify one-time layout migration and user preferences."""
import hashlib, json, pathlib, re, subprocess, sys, tempfile
root = pathlib.Path(__file__).resolve().parent
installed_config = pathlib.Path.home()/'.local/share/btop-nova/config/btop/btop.conf'
old = (root/'packaging/default.conf').read_text()
# Recreate an older profile even after the user's real installation is upgraded.
old = re.sub(r'^(nova_layout|show_zram)\s*=.*\n?', '', old, flags=re.M)
old += '\ncpu_logical_graphs = True\n'
for key in ('show_swap', 'swap_disk'):
    old = re.sub(r'^'+key+r'\s*=.*$', key+' = True', old, flags=re.M)

def values(text): return dict(re.findall(r'^(\w+)\s*=\s*(.*)$', text, re.M))
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
protected = [pathlib.Path('/usr/bin/btop'), pathlib.Path.home()/'.config/btop/btop.conf', pathlib.Path.home()/'.bashrc']
before = {str(path): digest(path) for path in protected}
with tempfile.TemporaryDirectory(prefix='.nova-install-', dir=root) as tmp:
    tmp = pathlib.Path(tmp); prefix = tmp/'local'; bashrc = tmp/'bashrc'
    conf = prefix/'share/btop-nova/config/btop/btop.conf'; conf.parent.mkdir(parents=True)
    conf.write_text(old)
    bashrc.write_text('# User shell settings\n')
    def install():
        output = subprocess.check_output([sys.executable, str(root/'install_nova.py'), '--prefix', str(prefix), '--bashrc', str(bashrc)], text=True)
        return json.loads(output)
    manifest = install()
    assert manifest['version'] == '1.3.0-nova-io11', manifest
    new = values(conf.read_text()); original = values(old)
    for key, value in original.items():
        if key == 'cpu_logical_graphs': continue
        assert new[key] == ('False' if key in ('show_swap', 'swap_disk') else value), (key, value, new[key])
    assert new['nova_layout'] == 'True' and new['show_zram'] == 'True'
    assert 'cpu_logical_graphs' not in new
    command = prefix/'bin/btop'
    assert '1.3.0-nova-io11' in subprocess.check_output([str(command), '--version'], text=True)
    assert values(conf.read_text())['io_mode'] == 'False'
    shell_hash = digest(bashrc)
    release = pathlib.Path(manifest['release'])/'bin/btop'
    binary_hash = digest(release)
    # A future upgrade must preserve a deliberately restored swap view and
    # disabled custom layout. Existing GPU and mount preferences also persist.
    text = conf.read_text()
    for key, value in {'show_swap':'True', 'swap_disk':'True', 'nova_layout':'False', 'proc_mounts':'False', 'gpu_processes':'False', 'show_zram':'False'}.items():
        text = re.sub(r'^'+key+r'\s*=.*$', key+' = '+value, text, flags=re.M)
    conf.write_text(text)
    install()
    assert conf.read_text() == text
    subprocess.check_call([str(command), '--version'], stdout=subprocess.DEVNULL)
    assert conf.read_text() == text
    assert digest(bashrc) == shell_hash and digest(release) == binary_hash
    # Repair a config saved by an older running build that omits the new key.
    conf.write_text(re.sub(r'^nova_layout\s*=.*\n?', '', text, flags=re.M))
    subprocess.check_call([str(command), '--version'], stdout=subprocess.DEVNULL)
    repaired = values(conf.read_text())
    assert repaired['nova_layout'] == 'True' and repaired['show_swap'] == 'False' and repaired['swap_disk'] == 'False'
    assert 'cpu_logical_graphs' not in repaired
    assert repaired['gpu_processes'] == repaired['proc_mounts'] == repaired['show_zram'] == 'False'
    conf.write_text(re.sub(r'^show_zram\s*=.*\n?', '', conf.read_text(), flags=re.M))
    subprocess.check_call([str(command), '--version'], stdout=subprocess.DEVNULL)
    assert values(conf.read_text())['show_zram'] == 'True'
    conf.write_text(conf.read_text() + '\ncpu_logical_graphs = True\n')
    subprocess.check_call([str(command), '--version'], stdout=subprocess.DEVNULL)
    assert 'cpu_logical_graphs' not in values(conf.read_text())
assert {str(path): digest(path) for path in protected} == before
print('Older profile → current release upgrade preserves CPU/GPU/mount and zram preferences; one-time layout migration, wrapper recovery and protected system files passed')
