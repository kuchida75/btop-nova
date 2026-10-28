"""Isolated terminal driver shared by Nova layout and zram tests."""
import codecs, fcntl, os, pathlib, pty, re, select, struct, subprocess, sys, tempfile, termios, time
sys.path.insert(0, '/tmp/nova-terminal-test')
import pyte
root = pathlib.Path(__file__).resolve().parents[1]
base = (root / 'packaging/default.conf').read_text()

def config_with(**values):
    text = base
    for key, value in values.items():
        line = f'{key} = {value}'
        text = re.sub(r'^' + key + r'\s*=.*$', line, text, flags=re.M) if re.search(r'^' + key + r'\s*=', text, flags=re.M) else text + '\n' + line + '\n'
    return text

class Terminal:
    def __init__(self, config, home, library, width=200, height=100, extra=None):
        self.conf = pathlib.Path(home) / 'btop/btop.conf'
        self.conf.parent.mkdir(exist_ok=True)
        self.conf.write_text(config)
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', height, width, 0, 0))
        env = dict(os.environ, TERM='xterm-256color', XDG_CONFIG_HOME=str(home), LD_LIBRARY_PATH=str(library))
        if extra: env.update(extra)
        self.proc = subprocess.Popen([str(root / 'bin/btop'), '--utf-force'], stdin=slave, stdout=slave, stderr=slave, env=env, start_new_session=True)
        os.close(slave)
        self.screen = pyte.Screen(width, height)
        self.stream = pyte.Stream(self.screen)
        self.decoder = codecs.getincrementaldecoder('utf-8')()
        self.frame_tail = ''
        self.in_frame = False
        self.drain(1.5)

    def drain(self, seconds):
        end = time.monotonic() + seconds
        # Snapshot a complete synchronized redraw, including large charts
        # whose output crosses a PTY read boundary at the nominal deadline.
        while time.monotonic() < end or self.in_frame:
            assert time.monotonic() < end + 3, 'Incomplete terminal redraw'
            if select.select([self.master], [], [], .05)[0]:
                try:
                    data = self.decoder.decode(os.read(self.master, 65536))
                    markers = re.findall(r'\x1b\[\?2026([hl])', self.frame_tail + data)
                    if markers: self.in_frame = markers[-1] == 'h'
                    self.frame_tail = (self.frame_tail + data)[-7:]
                    self.stream.feed(data)
                except OSError: break
        assert self.proc.poll() is None, self.text()

    def text(self): return '\n'.join(self.screen.display)
    def key(self, key): os.write(self.master, key.encode()); self.drain(.65)
    def resize(self, width, height):
        self.screen.resize(height, width)
        fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack('HHHH', height, width, 0, 0))
        self.drain(1.1)

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
