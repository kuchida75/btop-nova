"""Create Nova portable, Debian and committed-source release assets without installation."""
import argparse
import gzip
import hashlib
import io
import json
import math
import os
import pathlib
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent


def run(*args, cwd=ROOT):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def archive(directory, destination, epoch):
    """Stable owner, mode, ordering and timestamps for the same payload."""
    with destination.open('wb') as output, gzip.GzipFile(fileobj=output, mode='wb', filename='', mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w', format=tarfile.PAX_FORMAT) as tar:
            for path in [directory, *sorted(directory.rglob('*'))]:
                name = path.relative_to(directory.parent).as_posix()
                info = tar.gettarinfo(str(path), name)
                info.uid = info.gid = 0
                info.uname = info.gname = 'root'
                info.mtime = epoch
                info.mode = 0o755 if path.is_dir() or os.access(path, os.X_OK) else 0o644
                with path.open('rb') if path.is_file() else io.BytesIO() as data:
                    tar.addfile(info, data if path.is_file() else None)


def dependencies(binary, temporary):
    metadata = temporary/'dependency-metadata'
    (metadata/'debian').mkdir(parents=True)
    (metadata/'debian/control').write_text(
        'Source: btop-nova\nSection: utils\nPriority: optional\n'
        'Maintainer: kuchida75 <153719495+kuchida75@users.noreply.github.com>\n\n'
        'Package: btop-nova\nArchitecture: amd64\nDescription: Nova btop resource monitor\n')
    result = run('dpkg-shlibdeps', '-O', '-e'+str(binary), cwd=metadata)
    return next(line.partition('=')[2] for line in result.splitlines() if line.startswith('shlibs:Depends='))


def package(args):
    if platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'amd64'):
        raise SystemExit('This packaging target currently supports Linux amd64 only.')
    for command in ('git', 'dpkg-deb', 'dpkg-shlibdeps'):
        if not shutil.which(command): raise SystemExit('Missing package build tool: '+command)
    binary = args.binary.resolve()
    version = run(str(binary), '--version').split()[-1]
    match = re.fullmatch(r'(\d+\.\d+\.\d+)-nova-io(\d+)', version)
    if not match: raise SystemExit('Unrecognized Nova binary version: '+version)
    source_ref = run('git', 'rev-parse', args.source_ref+'^{commit}')
    epoch = int(run('git', 'show', '-s', '--format=%ct', source_ref))
    # The live checkout profile may be user-edited; release defaults are separate.
    dirty = run('git', 'diff', '--name-only', source_ref, '--', '.', ':(exclude)nova-config/btop/btop.conf')
    if dirty: raise SystemExit('Commit release source changes before packaging:\n'+dirty)
    untracked = run('git', 'ls-files', '--others', '--exclude-standard')
    if untracked: raise SystemExit('Commit or ignore untracked release files before packaging:\n'+untracked)
    inputs = run('git', 'ls-files', 'src', 'include', 'Makefile').splitlines()
    if any((ROOT/path).stat().st_mtime > binary.stat().st_mtime for path in inputs):
        raise SystemExit('Build the binary again after the latest source edits.')
    declared_version = run('git', 'show', source_ref+':src/btop.cpp')
    if 'Version = "'+version+'"' not in declared_version:
        raise SystemExit('Binary version does not match the committed source revision.')
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    deb_version = match[1]+'+nova.io'+match[2]+'-1'
    stem = 'btop-nova-'+version
    with tempfile.TemporaryDirectory(prefix='.nova-package-', dir=ROOT) as name:
        temporary = pathlib.Path(name)
        depends = dependencies(binary, temporary)
        portable = temporary/(stem+'-linux-amd64')
        (portable/'bin').mkdir(parents=True)
        shutil.copy2(binary, portable/'bin/btop')
        for filename in ('install_nova.py', 'rollback_nova.py', 'NOVA.txt', 'README_NOVA.md', 'LICENSE'):
            shutil.copy2(ROOT/filename, portable/filename)
        (portable/'packaging').mkdir()
        shutil.copy2(ROOT/'packaging/default.conf', portable/'packaging/default.conf')
        (portable/'Img').mkdir()
        shutil.copy2(ROOT/'Img/nova-gpu-dots.png', portable/'Img/nova-gpu-dots.png')
        shutil.copytree(ROOT/'themes', portable/'share/btop/themes')
        (portable/'licenses').mkdir()
        shutil.copy2(ROOT/'include/fmt/LICENSE.rst', portable/'licenses/fmt.txt')
        shutil.copy2(ROOT/'packaging/licenses/widecharwidth.txt', portable/'licenses/widecharwidth.txt')
        (portable/'BUILD.json').write_text(json.dumps(dict(version=version, source_commit=source_ref,
            binary_sha256=digest(binary), architecture='amd64', depends=depends), indent=2)+'\n')
        tar_path = output/(portable.name+'.tar.gz')
        archive(portable, tar_path, epoch)

        deb = temporary/'deb'
        (deb/'DEBIAN').mkdir(parents=True)
        (deb/'usr/lib/btop-nova/bin').mkdir(parents=True)
        shutil.copy2(binary, deb/'usr/lib/btop-nova/bin/btop')
        (deb/'usr/bin').mkdir(parents=True)
        shutil.copy2(ROOT/'packaging/btop-nova', deb/'usr/bin/btop-nova')
        (deb/'usr/bin/btop-nova').chmod(0o755)
        data = deb/'usr/share/btop-nova'; data.mkdir(parents=True)
        shutil.copy2(ROOT/'packaging/default.conf', data/'default.conf')
        shutil.copytree(ROOT/'themes', data/'themes')
        lookup = deb/'usr/lib/btop-nova/share/btop'; lookup.mkdir(parents=True)
        (lookup/'themes').symlink_to('../../../../share/btop-nova/themes')
        doc = deb/'usr/share/doc/btop-nova'; doc.mkdir(parents=True)
        for filename in ('NOVA.txt', 'README_NOVA.md', 'LICENSE'):
            shutil.copy2(ROOT/filename, doc/filename)
        shutil.copy2(ROOT/'include/fmt/LICENSE.rst', doc/'fmt-license.txt')
        shutil.copy2(ROOT/'packaging/licenses/widecharwidth.txt', doc/'widecharwidth-license.txt')
        copyright_text = (
            'btop upstream: Aristocratos and contributors; see source copyright notices.\n'
            'Nova modifications: Copyright 2026 Nova btop contributors.\n'
            'License: Apache-2.0; see LICENSE.\n'
            'Bundled fmt: Victor Zverovich and contributors; see fmt-license.txt.\n'
            'Bundled widechar_width: ridiculous_fish, CC0; see widecharwidth-license.txt.\n')
        (doc/'copyright').write_text(copyright_text)
        size = math.ceil(sum(p.stat().st_size for p in (deb/'usr').rglob('*') if p.is_file() and not p.is_symlink())/1024)
        (deb/'DEBIAN/control').write_text(
            f'Package: btop-nova\nVersion: {deb_version}\nArchitecture: amd64\n'
            'Maintainer: kuchida75 <153719495+kuchida75@users.noreply.github.com>\n'
            f'Installed-Size: {size}\nDepends: {depends}\nSection: utils\nPriority: optional\n'
            'Homepage: https://github.com/kuchida75/btop-nova\n'
            'Description: Nova btop with disk throughput and fine GPU histories\n'
            ' Live per-disk read/write rates, logical CPU graphs, coloured GPU histories,\n'
            ' NVIDIA processes, mounted filesystem summary and automatic zram statistics.\n'
            ' Installs a separate btop-nova command and preserves the upstream btop.\n')
        checks = []
        for path in sorted((deb/'usr').rglob('*')):
            if path.is_file() and not path.is_symlink():
                checks.append(hashlib.md5(path.read_bytes()).hexdigest()+'  '+path.relative_to(deb).as_posix())
            if not path.is_symlink():
                path.chmod(0o755 if path.is_dir() or os.access(path, os.X_OK) else 0o644)
                os.utime(path, (epoch, epoch))
        (deb/'DEBIAN/md5sums').write_text('\n'.join(checks)+'\n')
        deb_path = output/f'btop-nova_{deb_version}_amd64.deb'
        subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(deb), str(deb_path)], check=True,
                       env=dict(os.environ, SOURCE_DATE_EPOCH=str(epoch)))

        source_path = output/(stem+'-source.tar.gz')
        raw = subprocess.check_output(['git', 'archive', '--format=tar', '--prefix='+stem+'-source/', source_ref], cwd=ROOT)
        with source_path.open('wb') as file, gzip.GzipFile(fileobj=file, mode='wb', filename='', mtime=0) as compressed:
            compressed.write(raw)
        assets = [tar_path, deb_path, source_path]
        manifest = output/'release-manifest.json'
        manifest.write_text(json.dumps(dict(version=version, tag='v'+version, source_commit=source_ref,
            upstream_commit='36842a3bccfb78f5c27642435bff387b42f7d13b', architecture='amd64',
            binary_sha256=digest(binary), depends=depends,
            assets=[dict(name=p.name, size=p.stat().st_size, sha256=digest(p)) for p in assets]), indent=2)+'\n')
        assets.append(manifest)
        (output/'SHA256SUMS').write_text(''.join(digest(p)+'  '+p.name+'\n' for p in assets))
    print(json.dumps(dict(version=version, depends=depends, output=str(output), assets=[p.name for p in assets]+['SHA256SUMS']), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=pathlib.Path, default=ROOT/'dist')
    parser.add_argument('--binary', type=pathlib.Path, default=ROOT/'bin/btop')
    parser.add_argument('--source-ref', default='HEAD')
    package(parser.parse_args())
