"""Validate release archives and extracted installation in temporary directories only."""
import hashlib
import json
import os
import pathlib
import re
import subprocess
import tarfile
import tempfile
from audit_release import audit_paths

root = pathlib.Path(__file__).resolve().parent
dist = root/'dist'
manifest = json.loads((dist/'release-manifest.json').read_text())
version = manifest['version']


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def values(path): return dict(re.findall(r'^(\w+)\s*=\s*(.*)$', path.read_text(), re.M))
def command(*args, **kwargs): return subprocess.check_output(args, text=True, **kwargs)


protected = [pathlib.Path('/usr/bin/btop'), pathlib.Path.home()/'.config/btop/btop.conf', pathlib.Path.home()/'.bashrc']
for path in (pathlib.Path.home()/'.local/bin/btop', pathlib.Path.home()/'.local/share/btop-nova/config/btop/btop.conf'):
    if path.exists(): protected.append(path)
before = {str(p):digest(p) for p in protected}
subprocess.run(['sha256sum','-c','SHA256SUMS'], cwd=dist, check=True)
for item in manifest['assets']:
    path = dist/item['name']
    assert path.stat().st_size == item['size'] and digest(path) == item['sha256']
assert manifest['binary_sha256'] == digest(root/'bin/btop')
deb = next(dist/item['name'] for item in manifest['assets'] if item['name'].endswith('.deb'))
portable = next(dist/item['name'] for item in manifest['assets'] if item['name'].endswith('amd64.tar.gz'))
source = next(dist/item['name'] for item in manifest['assets'] if item['name'].endswith('source.tar.gz'))
audit_paths([portable, deb, source, dist/'release-manifest.json', dist/'SHA256SUMS'])

with tempfile.TemporaryDirectory(prefix='.nova-package-test-', dir=root) as tmp:
    tmp = pathlib.Path(tmp)
    extracted = tmp/'deb'; extracted.mkdir()
    control = tmp/'control'; control.mkdir()
    subprocess.run(['dpkg-deb','--extract',str(deb),str(extracted)], check=True)
    subprocess.run(['dpkg-deb','--control',str(deb),str(control)], check=True)
    metadata = (control/'control').read_text()
    assert 'Package: btop-nova\n' in metadata and 'Architecture: amd64\n' in metadata
    assert 'Depends: '+manifest['depends'] in metadata
    assert set(p.name for p in control.iterdir()) == {'control','md5sums'} # no maintainer scripts
    assert not (extracted/'usr/bin/btop').exists() and not (extracted/'etc').exists()
    subprocess.run(['md5sum','-c',str(control/'md5sums')], cwd=extracted, check=True, stdout=subprocess.DEVNULL)
    lookup = extracted/'usr/lib/btop-nova/share/btop/themes'
    assert lookup.is_dir() and lookup.resolve() == (extracted/'usr/share/btop-nova/themes').resolve()
    home = tmp/'home'; home.mkdir()
    env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(tmp/'profile'))
    wrapper = extracted/'usr/bin/btop-nova'
    assert version in command(str(wrapper),'--version',env=env)
    conf = tmp/'profile/btop-nova/btop/btop.conf'
    assert values(conf)['disks_filter'] == '""' and values(conf)['gpu_nvtop_graph'] == 'True'
    conf.write_text(conf.read_text()+'\n# Keep this user preference\n')
    saved = conf.read_text()
    command(str(wrapper),'--version',env=env)
    assert conf.read_text() == saved
    print('Debian package: correct dependencies, separate command, portable defaults, themes, user preference preservation and no maintainer scripts passed',flush=True)

    with tarfile.open(portable) as tar:
        assert all(not name.startswith('/') and '..' not in pathlib.PurePosixPath(name).parts for name in tar.getnames())
        tar.extractall(tmp/'portable', filter='data')
    folder = next((tmp/'portable').iterdir())
    assert digest(folder/'bin/btop') == manifest['binary_sha256']
    user = tmp/'fresh user'; user.mkdir()
    prefix = user/'local'; bashrc = user/'bashrc'
    bashrc.write_text('# User shell\n')
    install = ['python3',str(folder/'install_nova.py'),'--prefix',str(prefix),'--bashrc',str(bashrc)]
    command(*install)
    fresh_conf = prefix/'share/btop-nova/config/btop/btop.conf'
    assert values(fresh_conf)['disks_filter'] == '""'
    assert version in command(str(prefix/'bin/btop'),'--version')
    assert any((prefix/'share/btop-nova/releases').glob('*/share/btop/themes/*.theme'))
    saved = fresh_conf.read_text()
    saved = re.sub(r'^cpu_logical_graphs = .*$', 'cpu_logical_graphs = False', saved, flags=re.M)
    fresh_conf.write_text(saved)
    command(*install)
    assert fresh_conf.read_text() == saved
    assert bashrc.read_text().count('# BEGIN NOVA BTOP') == 1
    command('python3',str(folder/'rollback_nova.py'),'--prefix',str(prefix),'--bashrc',str(bashrc))
    assert not (prefix/'bin/btop').exists() and fresh_conf.read_text() == saved
    assert bashrc.read_text() == '# User shell\n\n'
    print('Portable package: executable checksum, themes, paths with spaces, fresh/install/upgrade/rollback and retained configuration passed',flush=True)

    with tarfile.open(source) as tar:
        names = tar.getnames(); top = 'btop-nova-'+version+'-source/'
        for name in ('Makefile','package_nova.py','README_NOVA.md','LICENSE','packaging/default.conf','src/btop_gpu_history.hpp','src/btop_zram.hpp'):
            assert top+name in names, name
        assert not any('/bin/btop' in name or '/dist/' in name or 'test-screen-' in name for name in names)
        assert tar.extractfile(top+'src/btop.cpp').read() == (root/'src/btop.cpp').read_bytes()
    print('Source archive: committed production source, build tools, defaults and licences present; binaries and runtime/test artifacts excluded',flush=True)

assert {str(p):digest(p) for p in protected} == before
print('Packaged upstream btop, original profile, live Nova command/profile and shell settings unchanged',flush=True)
