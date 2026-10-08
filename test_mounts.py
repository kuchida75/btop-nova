"""PTY coverage for native mount summary, process bounds, details and resizing."""
import codecs, fcntl, json, os, pathlib, pty, re, select, struct, subprocess, sys, tempfile, termios, time
sys.path.insert(0, '/tmp/nova-terminal-test')
import pyte
root = pathlib.Path(__file__).resolve().parent
base = (root / 'packaging/default.conf').read_text()
for key, value in [('nova_layout', 'False'), ('gpu_nvtop_graph', 'False'), ('gpu_processes', 'False'), ('io_mode', 'False'), ('proc_mounts', 'True'), ('gpu_always_visible', 'False'), ('show_boot_disks', 'False'), ('update_ms', '500')]:
    base = re.sub(r'^' + key + r'\s*=.*$', key + ' = ' + value, base, flags=re.M)

class Terminal:
    def __init__(self, config, home, width=200, height=60, extra=None):
        self.conf = pathlib.Path(home) / 'btop/btop.conf'
        self.conf.parent.mkdir(exist_ok=True)
        self.conf.write_text(config)
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', height, width, 0, 0))
        env = dict(os.environ, TERM='xterm-256color', XDG_CONFIG_HOME=str(home))
        if extra: env.update(extra)
        self.proc = subprocess.Popen([str(root / 'bin/btop'), '--utf-force'], stdin=slave, stdout=slave, stderr=slave, env=env, start_new_session=True)
        os.close(slave)
        self.screen = pyte.Screen(width, height); self.stream = pyte.Stream(self.screen)
        self.decoder = codecs.getincrementaldecoder('utf-8')()
        self.drain(1.5)
    def drain(self, seconds):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            if select.select([self.master], [], [], .05)[0]:
                try: self.stream.feed(self.decoder.decode(os.read(self.master, 65536)))
                except OSError: break
        assert self.proc.poll() is None, self.text()
    def text(self): return '\n'.join(self.screen.display)
    def key(self, key): os.write(self.master, key); self.drain(.6)
    def resize(self, width, height):
        self.screen.resize(height, width)
        fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack('HHHH', height, width, 0, 0))
        self.drain(.8)
    def footer(self):
        top = next(i for i, line in enumerate(self.screen.display) if 'mounts ' in line and 'local' in line)
        return self.screen.display[top-1]
    def close(self):
        os.write(self.master, b'q'); until = time.monotonic() + 5
        while self.proc.poll() is None and time.monotonic() < until:
            if select.select([self.master], [], [], .05)[0]:
                try: os.read(self.master, 65536)
                except OSError: break
        try: self.proc.wait(timeout=1)
        except subprocess.TimeoutExpired: self.proc.kill(); self.proc.wait(); raise
        os.close(self.master)
        assert self.proc.returncode == 0

def collected():
    rows = {}
    for line in subprocess.check_output(['/tmp/nova-mounts-test', '--dump'], text=True).splitlines():
        path, total, used, available, kind, device = line.split('\t')
        rows[path] = (int(total), int(used), int(available), kind, device)
    return rows

rows = collected()
duf = {r['mount_point']: r for r in json.loads(subprocess.check_output(['duf', '--json'], text=True))}
assert '/' in rows and set(rows) <= set(duf), rows
mount_title = f'mounts {len(rows)} local'
for path, (total, used, available, kind, device) in rows.items():
    expected = duf[path]
    assert total == expected['total'] and kind == expected['fs_type']
    assert abs(used - expected['used']) < 8 * 1024**2
    assert abs(available - expected['free']) < 8 * 1024**2
print('Collected local filesystems and byte values agree with installed duf; binds, loops and pseudo filesystems excluded', flush=True)

# A fresh collection responds to actual allocation on the root filesystem.
with tempfile.NamedTemporaryFile(prefix='.nova-mount-allocation-', dir=root) as allocation:
    before = collected()['/'][1]
    allocation.write(bytes(64 * 1024**2)); allocation.flush(); os.fsync(allocation.fileno())
    after = collected()['/'][1]
    assert after >= before + 32 * 1024**2, (before, after)
print('Live collection reflects newly allocated filesystem blocks', flush=True)

workers = []
try:
    workers = [subprocess.Popen(['sleep', '90']) for _ in range(36)]
    busy = subprocess.Popen([sys.executable, '-c', 'import time; end=time.monotonic()+60\nwhile time.monotonic()<end: pass'])
    workers.append(busy)
    with tempfile.TemporaryDirectory(prefix='.nova-mount-ui-', dir=root) as tmp:
        t = Terminal(base, tmp)
        try:
            t.drain(1)
            assert 'MOUNTED ON' in t.text() and 'FILESYSTEM' in t.text(), t.text()
            assert mount_title in t.text(), t.text()
            header = next(i for i, line in enumerate(t.screen.display) if 'MOUNTED ON' in line)
            table = t.screen.display[header+2:header+2+len(rows)]
            for mount in rows: assert any(mount in line for line in table), t.text()
            for mount in rows:
                line = next(line for line in table if re.search(r'│' + re.escape(mount) + r'\s*│', line))
                percent = float(re.search(r'([0-9.]+)%', line).group(1))
                expected = rows[mount][1] * 100 / rows[mount][0]
                assert abs(percent - expected) < .2, (mount, percent, expected)
            assert all(any(kind in line for line in table) for _,_,_,kind,_ in rows.values()), table
            assert all('[' in line and '#' in line or '[..........]' in line for line in table), table
            proc_top = next(i for i, line in enumerate(t.screen.display) if '⁴proc' in line)
            proc_col = t.screen.display[proc_top].index('╭', t.screen.display[proc_top].index('⁴proc')-6)
            visible = t.screen.display[proc_top+2:header-2]
            assert str(busy.pid) in visible[0][proc_col:], visible[:3]
            total_processes = int(re.search(r'/(\d+)', t.footer()).group(1))
            assert len(visible) < total_processes, (len(visible), total_processes)
            (root / 'test-screen-mounts-200x60.txt').write_text(t.text())
            # Selection and details use the shortened list; table clicks cannot
            # select a process or trigger a process action.
            t.key(b'\x1b[B'); assert '1/' in t.footer(), t.footer()
            t.key(b'\r'); assert 'Status:' in t.text(), t.text()
            assert 'MOUNTED ON' in t.text(), t.text()
            t.key(b'\r'); assert 'Status:' not in t.text(), t.text()
            header = next(i for i, line in enumerate(t.screen.display) if 'MOUNTED ON' in line)
            col = t.screen.display[header].index('MOUNTED ON') + 1
            t.key(f'\x1b[<0;{col};{header+3}M'.encode())
            assert '0/' in t.footer() and 'Status:' not in t.text(), t.text()
            prior = t.footer()
            t.key(f'\x1b[<65;{col};{header+3}M'.encode())
            assert t.footer() == prior, (prior, t.footer())
            t.key(b'\x1b[6~'); assert 'MOUNTED ON' in t.text(), t.text()
            t.key(b'\x1b[H'); assert 'MOUNTED ON' in t.text(), t.text()
            t.key(b'M'); assert 'MOUNTED ON' not in t.text(), t.text()
            t.key(b'M'); assert 'MOUNTED ON' in t.text(), t.text()
            t.key(b'f'); t.key(b'no_such_process'); t.key(b'\r')
            assert 'MOUNTED ON' in t.text(), t.text()
            t.key(b'\x1b[3~'); assert 'MOUNTED ON' in t.text(), t.text()
            t.key(b'e'); assert 'MOUNTED ON' in t.text(), t.text()
            t.key(b'e'); t.key(b'h'); t.key(b'h')
            assert 'MOUNTED ON' in t.text(), t.text()
            t.resize(120, 50)
            assert 'MOUNTED ON' in t.text() and 'TYPE' in t.text() and 'FILESYSTEM' not in t.text(), t.text()
            t.resize(100, 35)
            assert 'MOUNTED ON' in t.text() and 'USE%' in t.text() and 'TYPE' not in t.text(), t.text()
            assert re.search(r'mounts [1-4]/5 local', t.text()), t.text()
            t.key(b'\x1b[B'); t.key(b'\r')
            assert 'Status:' in t.text() and 'MOUNTED ON' not in t.text(), t.text()
            t.key(b'\r'); assert 'MOUNTED ON' in t.text(), t.text()
            t.resize(80, 24); assert 'MOUNTED ON' not in t.text(), t.text()
            t.resize(200, 80); assert mount_title in t.text(), t.text()
            t.key(b'p'); assert 'MOUNTED ON' in t.text(), t.text()
        finally: t.close()
        assert 'proc_mounts = True' in t.conf.read_text()
        print('Top processes, mount columns/bars, selection, mouse bounds, details, filtering, tree, help, toggle, three resizes, fallback, restoration and preset passed', flush=True)
        # Verify the same placement with the pinned GPU enabled.
        library = pathlib.Path(tmp) / 'fixture'; library.mkdir()
        subprocess.run(['gcc', '-shared', '-fPIC', str(root / 'tests/nova_nvml_fixture.c'), '-o', str(library / 'libnvidia-ml.so')], check=True)
        t = Terminal(base.replace('gpu_always_visible = False', 'gpu_always_visible = True'), tmp, height=100, extra={'LD_LIBRARY_PATH': str(library)})
        try:
            assert 'GPU load ' in t.text() and 'VRAM used ' in t.text() and mount_title in t.text(), t.text()
            for _ in range(3):
                t.key(b'p'); assert 'GPU load ' in t.text(), t.text()
                if '⁴proc' in t.text(): assert 'MOUNTED ON' in t.text(), t.text()
        finally: t.close()
        print('Mounted table and pinned GPU coexist across presets', flush=True)
finally:
    for worker in workers:
        if worker.poll() is None: worker.terminate()
        worker.wait(timeout=5)
