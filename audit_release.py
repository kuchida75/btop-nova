"""Inspect release payloads for accidentally bundled local identity and runtime data.

Public repository URLs and upstream contributor/licence credits are intentional.
This check complements manual review; it cannot prove absence of every possible
secret or recognise personal details in arbitrary image pixels.
"""
import argparse
import getpass
import pathlib
import re
import socket
import subprocess
import tarfile
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent


def private_markers():
    markers = [('private home path', re.escape(str(pathlib.Path.home()).encode()))]
    user = getpass.getuser()
    if len(user) >= 4 and user not in ('root', 'user', 'runner', 'ubuntu'):
        markers.append(('local username', rb'(?<![\w])'+re.escape(user.encode())+rb'(?![\w])'))
    host = socket.gethostname()
    if len(host) >= 4 and host not in ('localhost', 'ubuntu'):
        markers.append(('local hostname', re.escape(host.encode())))
    contact = subprocess.run(['git', 'config', 'user.email'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if contact and not contact.endswith('@users.noreply.github.com'):
        markers.append(('private git contact', re.escape(contact.encode())))
    mountinfo = pathlib.Path('/proc/self/mountinfo')
    if mountinfo.exists():
        for line in mountinfo.read_text().splitlines():
            fields = line.split()
            if len(fields) > 4 and fields[4].startswith(('/mnt/', '/media/')):
                path = re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), fields[4])
                if path not in ('/mnt/data', '/media/data'):
                    markers.append(('local mount path', re.escape(path.encode())))
    return [(name, re.compile(pattern, re.I)) for name, pattern in markers]


def audit_paths(paths):
    markers = private_markers()
    failures = []
    checked = 0

    def check(name, data):
        nonlocal checked
        checked += 1
        for category, pattern in markers:
            if pattern.search(data): failures.append((name, category))
        parts = pathlib.PurePosixPath(name).parts
        if any(p in ('.git', '.env', 'obj', 'dist') for p in parts) or any(p.startswith('test-screen-') for p in parts) or name.endswith('btop.log'):
            failures.append((name, 'runtime or repository metadata'))
        if re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bgh[pousr]_[A-Za-z0-9]{30,}\b', data):
            failures.append((name, 'credential-like content'))
        if name.endswith(('packaging/default.conf', 'nova-config/btop/btop.conf', 'share/btop-nova/default.conf')):
            for key in ('disks_filter', 'io_graph_speeds', 'net_iface'):
                if not re.search(rb'^'+key.encode()+rb'\s*=\s*""\s*$', data, re.M):
                    failures.append((name, 'non-generic '+key))

    for path in map(pathlib.Path, paths):
        if path.name.endswith('.tar.gz'):
            with tarfile.open(path) as archive:
                for member in archive.getmembers():
                    if member.uname not in ('', 'root') or member.gname not in ('', 'root'):
                        failures.append((member.name, 'local archive ownership'))
                    if member.isfile(): check(member.name, archive.extractfile(member).read())
        elif path.suffix == '.deb':
            with tempfile.TemporaryDirectory(prefix='.nova-audit-', dir=ROOT) as folder:
                target = pathlib.Path(folder)
                subprocess.run(['dpkg-deb', '--extract', str(path.resolve()), str(target/'data')], check=True)
                subprocess.run(['dpkg-deb', '--control', str(path.resolve()), str(target/'control')], check=True)
                for file in target.rglob('*'):
                    if file.is_file() and not file.is_symlink(): check(file.relative_to(target).as_posix(), file.read_bytes())
        else:
            check(path.name, path.read_bytes())
    if failures:
        # Report categories and filenames without echoing personal values or secrets.
        raise SystemExit('Release privacy audit failed:\n'+'\n'.join(f'{name}: {category}' for name, category in sorted(set(failures))))
    print(f'Release privacy audit passed: {checked} payload files; local identity, home/mount paths, credentials, ownership and generic defaults checked.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=pathlib.Path, default=ROOT/'dist')
    args = parser.parse_args()
    paths = [p for p in args.dist.iterdir() if p.name.endswith(('.tar.gz', '.deb')) or p.name in ('release-manifest.json', 'SHA256SUMS')]
    if not paths: raise SystemExit('No release assets found.')
    audit_paths(paths)
