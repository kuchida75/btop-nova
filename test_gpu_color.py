"""PTY tests for coloured GPU histories, optional NVML process APIs and mount colours.
All GPU values are synthetic; process metadata and mounts use the actual host.
"""
import codecs, fcntl, os, pathlib, pty, re, select, struct, subprocess, sys, tempfile, termios, time
sys.path.insert(0, '/tmp/nova-terminal-test')
import pyte
root = pathlib.Path(__file__).resolve().parent
base = (root / 'nova-config/btop/btop.conf').read_text()

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


def find_line(term, needle):
    return next((i for i, line in enumerate(term.screen.display) if needle in line), -1)

def colour_at(term, row, needle):
    col = term.screen.display[row].index(needle)
    return term.screen.buffer[row][col].fg

def check(term):
    text = term.text()
    (root / 'test-screen-gpu-color-latest.txt').write_text(text)
    assert 'GCLK ' in text and 'MCLK ' in text, text
    assert 'GPU processes ' in text and 'TYPE' in text, text
    assert 'Both' in text and '320 MiB' in text and '67%' in text, text
    row = find_line(term, 'Both')
    assert str(target.pid) in term.screen.display[row], text
    assert term.screen.display[row].index('Both') < term.screen.display[row].index('67%'), text
    assert text.count(str(target.pid) + ' ') >= 1, text
    # Driver entries absent from /proc retain their PID, GPU fields and -- identity.
    unknown = find_line(term, '60002')
    assert unknown >= 0 and '--' in term.screen.display[unknown], text
    return row

with tempfile.TemporaryDirectory(prefix='.nova-gpu-color-', dir=root) as tmp:
    tmp = pathlib.Path(tmp)
    libraries = {}
    for api in ('v3', 'v2', 'v1', 'legacy'):
        path = tmp / api; path.mkdir()
        flags = [] if api == 'v3' else ['-DNOVA_FIXTURE_' + api.upper()]
        subprocess.run(['gcc', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror', *flags, str(root / 'tests/nova_nvml_fixture.c'), '-o', str(path / 'libnvidia-ml.so')], check=True)
        libraries[api] = path
    target = subprocess.Popen([sys.executable, '-c', 'while True: pass'])
    extra = {'NOVA_FIXTURE_PID': str(target.pid)}
    common = dict(nova_layout="False", io_mode='False', proc_mounts='True', gpu_always_visible='True', gpu_split_vram='True', gpu_nvtop_graph='True', gpu_processes='True', update_ms='500', shown_boxes='"cpu mem net proc"')
    try:
        for api in ('v3', 'v2', 'v1'):
            t = Terminal(config_with(**common), tmp, libraries[api], extra)
            try:
                row = check(t)
                assert 'kuchida' in t.screen.display[row], t.text()
                assert 'CPU%' in t.text() and 'RSS' in t.text(), t.text()
                if api != 'v3':
                    print(api + ': typed process API, duplicate merge and metadata passed')
                    continue
                gpu_row = find_line(t, 'GCLK ')
                first = gpu_row - 1
                assert colour_at(t, first, 'GPU ') == '00bcd4', t.screen.buffer[first]
                assert colour_at(t, first, 'VRAM ') == 'ffcd4b', t.screen.buffer[first]
                assert colour_at(t, gpu_row, 'GCLK ') == 'd772e5'
                assert colour_at(t, gpu_row, 'MCLK ') == '52c878'
                table = find_line(t, 'MOUNTED ON')
                assert table > row and find_line(t, '/boot/efi') > table, t.text()
                efi = find_line(t, '/boot/efi')
                assert colour_at(t, efi, '/boot/efi') == '6ba8ff'
                assert any(c.fg == '52c878' for c in t.screen.buffer[efi].values())
                disk = find_line(t, '/mnt/Crucial4TB')
                assert any(c.fg == 'ffcd4b' for c in t.screen.buffer[disk].values()), t.text()
                # Check the plot itself, not merely coloured legend text.
                separator = find_line(t, 'GPU processes ')
                plot_colours = {c.fg for r in range(gpu_row+1, separator-1) for x,c in t.screen.buffer[r].items() if x < 134 and len(c.data) == 1 and 0x2801 <= ord(c.data) <= 0x28ff}
                assert {'00bcd4', 'ffcd4b', 'd772e5', '52c878'} <= plot_colours, plot_colours
                (root / 'test-screen-gpu-color-200x100.txt').write_text(t.text())
                t.drain(4)
                # Export a faithful terminal preview, with test data explicitly labelled.
                from PIL import Image, ImageDraw, ImageFont
                indices = list(range(first-1, separator+9)) + [None] + list(range(table-1, efi+4))
                font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf', 13)
                preview = Image.new('RGB', (1600, (len(indices)+3)*17), '#101218')
                draw = ImageDraw.Draw(preview)
                draw.text((8, 4), 'Nova btop colour/layout preview — synthetic GPU test data; actual host mounts', font=font, fill='white')
                for dest, src in enumerate(indices, 2):
                    if src is None: continue
                    for col in range(t.screen.columns):
                        cell = t.screen.buffer[src][col]
                        colour = '#' + cell.fg if re.fullmatch('[0-9a-fA-F]{6}', cell.fg) else '#d0d0d0'
                        if len(cell.data) == 1 and 0x2800 <= ord(cell.data) <= 0x28ff:
                            dots = ord(cell.data)-0x2800
                            for bit,(dx,dy) in enumerate(((2,3),(2,6),(2,9),(5,3),(5,6),(5,9),(2,12),(5,12))):
                                if dots & (1 << bit): draw.ellipse((col*8+dx, dest*17+dy, col*8+dx+1, dest*17+dy+1), fill=colour)
                        else: draw.text((col*8, dest*17), cell.data, font=font, fill=colour)
                preview.save(root / 'nova-gpu-color-preview.png')
                # UI controls, filtering focus, resize restoration and native settings persistence.
                t.key('U'); assert 'GPU processes ' not in t.text(), t.text()
                t.key('U'); check(t)
                t.key('N'); assert 'GCLK ' not in t.text() and 'VRAM used ' in t.text(), t.text()
                t.key('N'); check(t)
                t.key('f'); t.key('N'); t.key('U')
                assert 'GPU processes ' in t.text() and 'GCLK ' in t.text(), t.text()
                t.key('\x1b'); check(t)
                t.key('V'); assert 'GCLK ' not in t.text(), t.text()
                t.key('N'); check(t)
                for w,h in ((110,60),(80,35),(200,100)):
                    t.resize(w,h)
                    if w == 80:
                        assert 'GPU processes ' not in t.text(), t.text()
                    elif w == 200: check(t)
                for _ in range(4): t.key('p'); check(t)
                t.key('h'); assert 'Toggle coloured' in t.text() and 'GPU processes below' in t.text(), t.text()
                t.key('\x1b'); check(t)
            finally: t.close()
            assert 'gpu_nvtop_graph = True' in t.conf.read_text()
            assert 'gpu_processes = True' in t.conf.read_text()
            print(api + ': typed process API, duplicate merge, metadata and chart passed')
        for mode, additions in (
            ('unavailable', {'NOVA_FIXTURE_NO_PROCS':'1'}),
            ('partial', {'NOVA_FIXTURE_NO_COMPUTE':'1'}),
            ('util unsupported', {'NOVA_FIXTURE_NO_UTIL':'1'}),
            ('stale samples', {'NOVA_FIXTURE_STALE':'1'}),
            ('clocks unavailable', {'NOVA_FIXTURE_NO_MAX':'1'}),
            ('process race', {'NOVA_FIXTURE_RACE':'1'}),
            ('truncated list', {'NOVA_FIXTURE_MANY':'1'}),
        ):
            t = Terminal(config_with(**common), tmp, libraries['v3'], dict(extra, **additions))
            try:
                if mode == 'unavailable': assert 'GPU process data unavailable' in t.text(), t.text()
                elif mode == 'partial': assert '(partial)' in t.text() and 'Graphic' in t.text(), t.text()
                elif mode in ('util unsupported', 'stale samples'):
                    row = find_line(t, 'Both'); assert '--' in t.screen.display[row] and '67%' not in t.screen.display[row], t.text()
                elif mode == 'clocks unavailable':
                    row = find_line(t, 'GCLK '); assert '(--)' in t.screen.display[row], t.text()
                elif mode == 'truncated list': assert '/30' in t.text(), t.text()
                else: check(t)
            finally: t.close()
            print(mode + ': honest availability/bounds passed')
        for symbols, truecolor in (('tty','False'),('block','False'),('braille','True')):
            t = Terminal(config_with(**common, graph_symbol_gpu='"'+symbols+'"', tty_mode='True' if symbols=='tty' else 'False', truecolor=truecolor), tmp, libraries['v3'], extra)
            try:
                check(t)
                first = find_line(t, 'GCLK ')+1
                end = find_line(t, 'GPU processes ')-1
                plot = [c for row in range(first, end) for x,c in t.screen.buffer[row].items() if 5 <= x < 134]
                dots = [c for c in plot if len(c.data) == 1 and 0x2801 <= ord(c.data) <= 0x28ff]
                if symbols == 'tty':
                    assert not dots and any(c.data == '.' and c.fg != 'default' for c in plot), t.text()
                else: assert dots, t.text()
            finally: t.close()
            print(symbols + ': colour fallback passed')
        t = Terminal(config_with(**dict(common, shown_boxes='"gpu0"')), tmp, libraries['v3'], extra, width=60, height=30)
        try:
            assert 'GCLK ' not in t.text() and 'VRAM used ' in t.text(), t.text()
            assert 'GPU processes ' in t.text(), t.text()
        finally: t.close()
        print('Narrow GPU-only panel: automatic graph fallback and compact process columns passed')
        t = Terminal(config_with(**common), tmp, libraries['legacy'], extra)
        try:
            assert 'gpu0' in t.text() and 'GPU process data unavailable' in t.text(), t.text()
            assert 'GCLK ' in t.text(), t.text()
        finally: t.close()
        print('Older NVML without optional symbols remains usable')
    finally:
        target.terminate(); target.wait(timeout=5)
