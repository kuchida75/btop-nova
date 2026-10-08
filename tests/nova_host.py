"""Discover integration-test mounts without recording a development host's paths."""
import pathlib
import subprocess
import tempfile


def mounted_filesystems():
    root = pathlib.Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='.nova-host-', dir=root) as folder:
        binary = pathlib.Path(folder)/'mounts'
        subprocess.run(['g++', '-std=c++20', str(root/'tests/nova_mounts.cpp'),
                        str(root/'src/btop_mounts.cpp'), '-o', str(binary)], check=True)
        lines = subprocess.check_output([str(binary), '--dump'], text=True).splitlines()
    mounts = {}
    for line in lines:
        path, total, used, available, kind, device = line.split('\t')
        mounts[path] = dict(total=int(total), used=int(used), available=int(available),
                            kind=kind, device=device)
    return mounts
