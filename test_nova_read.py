"""PTY integration checks; writes only a temporary file in this checkout."""
import os, pty, fcntl, termios, struct, subprocess, time, select, sys, pathlib, re, codecs, tempfile
sys.path.insert(0, '/tmp/nova-terminal-test')
try:
    import pyte
except ImportError:
    raise SystemExit("Install pyte in an isolated test environment before running this check.")
root=pathlib.Path(__file__).resolve().parent

test_config=tempfile.TemporaryDirectory(prefix='.nova-read-config-',dir=root)
config_dir=pathlib.Path(test_config.name)/'btop';config_dir.mkdir()
config=(root/'packaging/default.conf').read_text()
config=re.sub(r'io_mode = (True|False)', 'io_mode = False', config)
config=re.sub(r'gpu_always_visible = (True|False)', 'gpu_always_visible = False', config)
(config_dir/'btop.conf').write_text(config)
cols,rows=160,60
master,slave=pty.openpty();fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',rows,cols,0,0))
proc=subprocess.Popen([str(root/'bin/btop'),'--utf-force'],stdin=slave,stdout=slave,stderr=slave,env=dict(os.environ,TERM='xterm-256color',XDG_CONFIG_HOME=test_config.name),start_new_session=True);os.close(slave)
screen=pyte.Screen(cols,rows);stream=pyte.Stream(screen)
decoder=codecs.getincrementaldecoder("utf-8")()
def drain(seconds):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if select.select([master],[],[],.05)[0]:
            try:stream.feed(decoder.decode(os.read(master,65536)))
            except OSError:break
path=root/'.nova-test-io'
try:
    with path.open('wb',buffering=0) as f:f.write(bytes(64*1024*1024));os.fsync(f.fileno())
    drain(2);device=os.stat(root).st_dev
    counter=pathlib.Path(f'/sys/dev/block/{os.major(device)}:{os.minor(device)}/stat')
    before=int(counter.read_text().split()[2]);started=time.monotonic();rates=[]
    for i in range(24):
        subprocess.run(['dd',f'if={path}','of=/dev/null','bs=4M','count=16','iflag=direct','status=none'],check=True)
        drain(.25)
        m=re.search(r'R ([0-9.]+)', '\n'.join(screen.display))
        if m:rates.append(float(m.group(1)))
    final='\n'.join(screen.display)
    read_rows=[line for line in screen.display if re.search(r'R [0-9.]+ MiB/s',line)]
    assert any(any('⠁' <= c <= '⣿' for c in line.split('MiB/s',1)[1]) for line in read_rows), 'No live read history'
    (root/'test-screen-read-160x60.txt').write_text(final)
    kernel=(int(counter.read_text().split()[2])-before)*512/1048576/(time.monotonic()-started)
    average=sum(rates)/len(rates)
    assert .65 < average/kernel < 1.35,(average,kernel)
    print(f'Direct read: displayed average {average:.1f} MiB/s, Linux counters {kernel:.1f} MiB/s')
finally:
    path.unlink(missing_ok=True);os.write(master,b'q');drain(.3);proc.wait(timeout=3);os.close(master);test_config.cleanup()
