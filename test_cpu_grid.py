"""Verify all logical histories, a pinned busy CPU, resizing, toggle and saved preference."""
import codecs, fcntl, os, pathlib, pty, re, select, shutil, struct, subprocess, sys, tempfile, termios, time
sys.path.insert(0,'/tmp/nova-terminal-test')
import pyte
root=pathlib.Path(__file__).resolve().parent
count=len(re.findall(r'^processor\s*:',pathlib.Path('/proc/cpuinfo').read_text(),flags=re.M))
original=(root/'nova-config/btop/btop.conf').read_text()
original=re.sub(r'io_mode = (True|False)','io_mode = False',original)
original=re.sub(r'cpu_logical_graphs = (True|False)','cpu_logical_graphs = True',original)
with tempfile.TemporaryDirectory(prefix='.nova-grid-',dir=root) as tmp:
    config=pathlib.Path(tmp)/'btop';config.mkdir();conf=config/'btop.conf'
    for symbols in ['braille','block','tty']:
        conf.write_text(re.sub(r'graph_symbol_cpu = ".*"',f'graph_symbol_cpu = "{symbols}"',original))
        master,slave=pty.openpty();fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',80,200,0,0))
        proc=subprocess.Popen([str(root/'bin/btop'),'--utf-force'],stdin=slave,stdout=slave,stderr=slave,env=dict(os.environ,TERM='xterm-256color',XDG_CONFIG_HOME=tmp),start_new_session=True);os.close(slave)
        screen=pyte.Screen(200,80);stream=pyte.Stream(screen);decoder=codecs.getincrementaldecoder('utf-8')()
        def drain(seconds):
            until=time.monotonic()+seconds
            while time.monotonic()<until:
                if select.select([master],[],[],.05)[0]:
                    try:stream.feed(decoder.decode(os.read(master,65536)))
                    except OSError:break
            assert proc.poll() is None,'\n'.join(screen.display)
        def text():return '\n'.join(screen.display)
        def assert_grid():
            # A redraw can cross the collection boundary; wait for a complete
            # frame, bounded to two seconds, instead of sampling mid-redraw.
            deadline=time.monotonic()+2
            while len(re.findall(r'CPU(\d+) \d+%',text())) != count and time.monotonic()<deadline:
                drain(.1)
            labels=re.findall(r'CPU(\d+) \d+%',text())
            assert sorted(map(int,labels))==list(range(count)),text()
            assert f'{count} logical processors' in text(),text()
            assert 'GHz GHz' not in text(),text()
        worker=None
        try:
            drain(1.5);assert_grid()
            if symbols=='braille':
                busy_cpu=min(os.sched_getaffinity(0))
                worker=subprocess.Popen([sys.executable,'-c',f'import os,time; os.sched_setaffinity(0,{{{busy_cpu}}}); end=time.monotonic()+4\nwhile time.monotonic()<end: pass'])
                drain(2.5);assert_grid()
                rate=int(re.search(rf'CPU{busy_cpu} (\d+)%',text()).group(1))
                assert rate>=70,(busy_cpu,rate,text())
                assert 'MiB/s' in text(),text()
                (root/'test-screen-cpu-grid-200x80.txt').write_text(text())
            # Disable and re-enable the optional grid without resizing.
            os.write(master,b'L');drain(.6)
            assert 'logical processors' not in text(),text()
            os.write(master,b'L');drain(.6);assert_grid()
            # An 80x24 terminal cannot fit all 32 graphs: fallback, then restore.
            screen.resize(24,80);fcntl.ioctl(master,termios.TIOCSWINSZ,struct.pack('HHHH',24,80,0,0));drain(.8)
            assert 'logical processors' not in text() and not re.search(r'CPU\d+ \d+%',text()),text()
            screen.resize(80,200);fcntl.ioctl(master,termios.TIOCSWINSZ,struct.pack('HHHH',80,200,0,0));drain(.8);assert_grid()
            os.write(master,b'h');drain(.4);os.write(master,b'h');drain(.4);assert_grid()
            print(f'{symbols}: all {count} logical histories, live toggle, fallback, restoration and redraw passed',flush=True)
        finally:
            if worker is not None:worker.wait(timeout=5)
            log=config/'btop.log'
            if log.exists(): (root/'test-screen-cpu-debug.txt').write_text(log.read_text())
            os.write(master,b'q');until=time.monotonic()+5
            while proc.poll() is None and time.monotonic()<until:
                if select.select([master],[],[],.05)[0]:
                    try:os.read(master,65536)
                    except OSError:break
            try:proc.wait(timeout=1)
            except subprocess.TimeoutExpired:proc.kill();proc.wait();raise
            os.close(master)
        assert 'cpu_logical_graphs = True' in conf.read_text(), 'Fallback changed the saved preference'
