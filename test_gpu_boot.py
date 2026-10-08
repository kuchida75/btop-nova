"""Real PTY tests: boot mount visibility and independent GPU/VRAM histories.

GPU data is synthetic, supplied by a local fixture library only in these child
processes. Boot/EFI counters and capacities come from the actual mounted host.
"""
import codecs, fcntl, os, pathlib, pty, re, select, struct, subprocess, sys, tempfile, termios, time
sys.path.insert(0, '/tmp/nova-terminal-test')
import pyte
root = pathlib.Path(__file__).resolve().parent
base = (root / 'packaging/default.conf').read_text()

def config_with(**values):
    text = base
    for key, value in values.items():
        line = f'{key} = {value}'
        text = re.sub(r'^' + key + r'\s*=.*$', line, text, flags=re.M) if re.search(r'^' + key + r'\s*=', text, flags=re.M) else text + '\n' + line + '\n'
    return text

class Terminal:
    def __init__(self, config, home, library=None, extra=None, width=200, height=100):
        self.conf = pathlib.Path(home) / 'btop/btop.conf'
        self.conf.parent.mkdir(exist_ok=True)
        self.conf.write_text(config)
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', height, width, 0, 0))
        env = dict(os.environ, TERM='xterm-256color', XDG_CONFIG_HOME=str(home))
        if library: env['LD_LIBRARY_PATH'] = str(library)
        if extra: env.update(extra)
        self.proc = subprocess.Popen([str(root / 'bin/btop'), '--utf-force'], stdin=slave, stdout=slave, stderr=slave, env=env, start_new_session=True)
        os.close(slave)
        self.screen = pyte.Screen(width, height)
        self.stream = pyte.Stream(self.screen)
        self.decoder = codecs.getincrementaldecoder('utf-8')()
        self.drain(1.6)

    def drain(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if select.select([self.master], [], [], .05)[0]:
                try: self.stream.feed(self.decoder.decode(os.read(self.master, 65536)))
                except OSError: break
        assert self.proc.poll() is None, self.text()

    def text(self): return '\n'.join(self.screen.display)
    def key(self, key): os.write(self.master, key.encode()); self.drain(.6)
    def resize(self, width, height):
        self.screen.resize(height, width)
        fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack('HHHH', height, width, 0, 0))
        self.drain(.8)

    def close(self):
        os.write(self.master, b'q')
        until = time.monotonic() + 5
        while self.proc.poll() is None and time.monotonic() < until:
            if select.select([self.master], [], [], .05)[0]:
                try: os.read(self.master, 65536)
                except OSError: break
        try: self.proc.wait(timeout=1)
        except subprocess.TimeoutExpired: self.proc.kill(); self.proc.wait(); raise
        os.close(self.master)
        assert self.proc.returncode == 0

def has_disk(term, name): return bool(re.search(r'^\s*│?[^\n]*\b' + name + r'\b[^\n]*[MGT]iB', term.text(), re.M))

with tempfile.TemporaryDirectory(prefix='.nova-gpu-boot-', dir=root) as tmp:
    tmp = pathlib.Path(tmp)
    library = tmp / 'fixture'; library.mkdir()
    subprocess.run(['gcc', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror', str(root / 'tests/nova_nvml_fixture.c'), '-o', str(library / 'libnvidia-ml.so')], check=True)
    common = dict(nova_layout="False", gpu_nvtop_graph='False', gpu_processes='False', io_mode='False', show_boot_disks='False', gpu_always_visible='True', gpu_split_vram='True', update_ms='500', shown_boxes='"cpu mem net proc"')
    t = Terminal(config_with(**common), tmp, library)
    try:
        assert 'gpu0' in t.text(), t.text()
        assert not has_disk(t, 'boot') and not has_disk(t, 'efi'), t.text()
        t.key('B'); t.drain(.6)
        assert has_disk(t, 'boot') and has_disk(t, 'efi'), t.text()
        assert has_disk(t, 'root'), t.text()
        assert t.text().count('MiB/s') >= 10, t.text()
        (root / 'test-screen-gpu-boot-200x100.txt').write_text(t.text())
        t.key('B')
        assert not has_disk(t, 'boot') and not has_disk(t, 'efi'), t.text()
        # Distinct input percentages and histogram heights prove that the lower
        # graph uses allocated VRAM, rather than mirroring GPU load or its 7%
        # memory-controller activity.
        lines = t.screen.display
        upper = next(i for i, line in enumerate(lines) if 'GPU load ' in line)
        lower = next(i for i, line in enumerate(lines) if 'VRAM used ' in line)
        assert 20 <= int(re.search(r'GPU load (\d+)%', lines[upper]).group(1)) <= 30
        assert 75 <= int(re.search(r'VRAM used (\d+)%', lines[lower]).group(1)) <= 85
        graph_width = t.screen.columns - 67  # b_width=64, borders and gutter
        has_pixels = lambda line: any(c not in ' │─' for c in line[1:graph_width+1])
        upper_rows = sum(has_pixels(line) for line in lines[upper+1:lower])
        bottom = next(i for i in range(lower+1, len(lines)) if lines[i].startswith(('╰', '└')))
        lower_rows = sum(has_pixels(line) for line in lines[lower+1:bottom])
        assert lower_rows > upper_rows, (upper_rows, lower_rows, t.text())
        assert any('█' in line or '▄' in line or '▀' in line for line in lines[lower+1:bottom]), t.text()
        t.key('5'); assert 'GPU load ' in t.text(), t.text()
        for _ in range(4):
            t.key('p'); assert 'GPU load ' in t.text() and 'VRAM used ' in t.text(), t.text()
        t.key('V'); assert 'GPU load ' not in t.text() and 'VRAM used ' not in t.text(), t.text()
        t.key('V'); assert 'GPU load ' in t.text() and 'VRAM used ' in t.text(), t.text()
        t.key('h'); t.key('h'); assert 'VRAM used ' in t.text(), t.text()
        t.resize(80, 35); assert 'GPU load ' in t.text() and 'VRAM used ' in t.text(), t.text()
        t.resize(200, 100); assert 'VRAM used ' in t.text(), t.text()
    finally: t.close()
    saved = t.conf.read_text()
    assert 'show_boot_disks = False' in saved and 'gpu_split_vram = True' in saved
    assert 'gpu0' in re.search(r'^shown_boxes = .*$', saved, re.M).group()
    assert re.search(r'^disks_filter = .*$', saved, re.M).group() == re.search(r'^disks_filter = .*$', base, re.M).group()
    print('Boot/EFI toggle, preserved filter, independent GPU/VRAM heights, pinning, presets, legacy toggle, help and resize passed', flush=True)
    # Pinning is optional; turning it off restores the ordinary GPU toggle.
    common.update(gpu_always_visible='False', shown_boxes='"cpu mem net proc gpu0"')
    t = Terminal(config_with(**common), tmp, library)
    try:
        t.key('5'); assert 'GPU load ' not in t.text(), t.text()
        t.key('5'); assert 'GPU load ' in t.text(), t.text()
    finally: t.close()
    print('Unpinned GPU hide/show passed', flush=True)
    # A missing sensor shows -- for its half while the other remains live.
    common.update(gpu_always_visible='True')
    for missing, absent, present in [('VRAM', 'VRAM used --', 'GPU load '), ('LOAD', 'GPU load --', 'VRAM used ')]:
        t = Terminal(config_with(**common), tmp, library, {f'NOVA_FIXTURE_NO_{missing}': '1'})
        try:
            assert absent in t.text() and present in t.text(), t.text()
        finally: t.close()
        print(f'Missing {missing} sensor passed', flush=True)
    # Native GPU symbols and the narrow GPU-only layout stay readable.
    common.update(shown_boxes='"gpu0"')
    for symbols in ['braille', 'block', 'tty']:
        t = Terminal(config_with(**common, graph_symbol_gpu=f'"{symbols}"'), tmp, library, width=60, height=30)
        try:
            assert 'GPU load ' in t.text() and 'VRAM used ' in t.text(), t.text()
            t.key('V'); assert 'VRAM used ' not in t.text(), t.text()
            t.key('V'); assert 'VRAM used ' in t.text(), t.text()
        finally: t.close()
        print(f'{symbols}: narrow GPU-only layout and legacy toggle passed', flush=True)
    # Explicit GPU presets use the shared GPU symbol key without dangling
    # deferred configuration names or graph_symbol_gpu0 lookups.
    common.update(shown_boxes='"cpu mem net proc"')
    t = Terminal(config_with(**common, presets='"gpu0:0:tty cpu:1:braille,gpu0:0:block,mem:0:default,net:0:default"'), tmp, library)
    try:
        for _ in range(3):
            t.key('p'); assert 'GPU load ' in t.text() and 'VRAM used ' in t.text(), t.text()
    finally: t.close()
    print('Explicit GPU presets and deferred settings passed', flush=True)
    # No mock NVML: boot/EFI still toggles using real mounted host partitions.
    common.update(gpu_always_visible='False', shown_boxes='"cpu mem net proc"')
    t = Terminal(config_with(**common), tmp)
    try:
        t.key('B'); t.drain(.6)
        assert has_disk(t, 'boot') and has_disk(t, 'efi'), t.text()
        assert t.text().count('MiB/s') >= 10, t.text()
    finally: t.close()
    assert 'show_boot_disks = True' in t.conf.read_text()
    print('Real mounted boot/EFI collection and saved visibility passed', flush=True)
