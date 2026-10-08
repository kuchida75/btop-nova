"""PTY integration checks; writes only a temporary file in this checkout."""
import os, pty, fcntl, termios, struct, subprocess, time, select, sys, pathlib, re, codecs, tempfile, shutil
sys.path.insert(0, '/tmp/nova-terminal-test')
try:
    import pyte
except ImportError:
    raise SystemExit("Install pyte in an isolated test environment before running this check.")
root=pathlib.Path(__file__).resolve().parent
test_config=tempfile.TemporaryDirectory(prefix=".nova-test-config-",dir=root)
config_dir=pathlib.Path(test_config.name)
(config_dir/"btop").mkdir()
original=(root/"nova-config/btop/btop.conf").read_text()
original=re.sub(r'io_mode = (True|False)', 'io_mode = False', original)
original=re.sub(r'gpu_always_visible = (True|False)', 'gpu_always_visible = False', original)
(config_dir/"btop/btop.conf").write_text(original)
for cols,rows,interval in [(160,60,500),(100,35,500),(80,24,500),(160,60,1000),(160,60,2000)]:
    conf=config_dir/"btop/btop.conf"
    conf.write_text(re.sub(r"update_ms = \d+", f"update_ms = {interval}", conf.read_text()))
    master,slave=pty.openpty(); fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',rows,cols,0,0))
    env=dict(os.environ,TERM='xterm-256color',XDG_CONFIG_HOME=str(config_dir))
    proc=subprocess.Popen([str(root/'bin/btop'),'--utf-force'],stdin=slave,stdout=slave,stderr=slave,env=env, start_new_session=True);os.close(slave)
    screen=pyte.Screen(cols,rows);stream=pyte.Stream(screen)
    decoder=codecs.getincrementaldecoder("utf-8")()
    def drain(seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            ready,_,_=select.select([master],[],[],.05)
            if ready:
                try: stream.feed(decoder.decode(os.read(master,65536)))
                except OSError: break
    drain(interval/1000+1)
    snaps=[]
    path=root/'.nova-test-io'
    try:
        device=os.stat(root).st_dev
        counter=pathlib.Path(f'/sys/dev/block/{os.major(device)}:{os.minor(device)}/stat')
        before=int(counter.read_text().split()[6]); started=time.monotonic()
        with path.open('wb',buffering=0) as f:
            data=bytes(4*1024*1024)
            for i in range(32):
                f.write(data);os.fsync(f.fileno());drain(.25)
                snaps.append('\n'.join(screen.display))
        elapsed=time.monotonic()-started
        kernel=(int(counter.read_text().split()[6])-before)*512/1048576/elapsed
        final='\n'.join(screen.display);(root/f'test-screen-{cols}x{rows}.txt').write_text(final)
        assert proc.poll() is None, final
        assert 'MiB/s' in final, final
        assert 'Used' in final and 'root' in final, final
        write_rows=[line for s in snaps for line in s.splitlines() if re.search(r'W [0-9.]+ MiB/s',line)]
        assert any(any('⠁' <= c <= '⣿' for c in line.split('MiB/s',1)[1]) for line in write_rows), 'No live write history'
        if cols==160:
            assert 'Crucial4TB' in final and 'CrucialMX500' in final, final
        rates=[float(m.group(1)) for s in snaps if (m:=re.search(r'W ([0-9.]+)',s))]
        assert rates and max(rates)>0, final
        average=sum(rates)/len(rates)
        assert 0.65 < average/kernel < 1.35, (average,kernel,interval)
        print(f'{cols}x{rows}, {interval}ms: displayed average {average:.1f} MiB/s, Linux counters {kernel:.1f} MiB/s')
    finally:
        path.unlink(missing_ok=True);os.write(master,b'q');drain(.3)
        try:proc.wait(timeout=3)
        except subprocess.TimeoutExpired:proc.kill();proc.wait()
        os.close(master)

test_config.cleanup()
