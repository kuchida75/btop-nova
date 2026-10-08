"""Smoke-test graph modes, menu redraws, TTY symbols and repeated live resizing."""
import codecs, fcntl, os, pathlib, pty, re, select, shutil, struct, subprocess, sys, tempfile, termios, time
sys.path.insert(0,'/tmp/nova-terminal-test')
import pyte
root=pathlib.Path(__file__).resolve().parent
with tempfile.TemporaryDirectory(prefix='.nova-ui-',dir=root) as tmp:
    config=pathlib.Path(tmp)/'btop';config.mkdir();conf=config/'btop.conf'
    original=(root/'packaging/default.conf').read_text()
    original=re.sub(r'io_mode = (True|False)','io_mode = False',original)
    # Also exercise speeds above 2047 MiB/s, which overflowed the upstream int shift.
    original=re.sub(r'io_graph_speeds = ".*"','io_graph_speeds = "/:10000"',original)
    for symbols in ['braille','block','tty']:
        conf.write_text(re.sub(r'graph_symbol_mem = ".*"',f'graph_symbol_mem = "{symbols}"',original))
        master,slave=pty.openpty();fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',60,160,0,0))
        proc=subprocess.Popen([str(root/'bin/btop'),'--utf-force'],stdin=slave,stdout=slave,stderr=slave,env=dict(os.environ,TERM='xterm-256color',XDG_CONFIG_HOME=tmp),start_new_session=True);os.close(slave)
        screen=pyte.Screen(160,60);stream=pyte.Stream(screen);decoder=codecs.getincrementaldecoder('utf-8')()
        def drain(seconds):
            until=time.monotonic()+seconds
            while time.monotonic()<until:
                if select.select([master],[],[],.05)[0]:
                    try:stream.feed(decoder.decode(os.read(master,65536)))
                    except OSError:break
            assert proc.poll() is None, '\n'.join(screen.display)
        try:
            drain(1.5)
            assert 'R ' in '\n'.join(screen.display) and 'W ' in '\n'.join(screen.display)
            for rows,cols in [(35,100),(24,80),(60,160),(24,80),(60,160)]:
                screen.resize(rows,cols);fcntl.ioctl(master,termios.TIOCSWINSZ,struct.pack('HHHH',rows,cols,0,0));drain(.65)
                assert 'MiB/s' in '\n'.join(screen.display), '\n'.join(screen.display)
            os.write(master,b'i');drain(1)
            io_text='\n'.join(screen.display)
            assert 'IO%' in io_text and 'root' in io_text, io_text
            os.write(master,b'i');drain(.65)
            assert 'MiB/s' in '\n'.join(screen.display)
            os.write(master,b'h');drain(.5);os.write(master,b'h');drain(.5)
            assert 'MiB/s' in '\n'.join(screen.display)
            print(f'{symbols}: normal graphs, I/O toggle, menu redraw and five resizes passed',flush=True)
        finally:
            os.write(master,b'q')
            until=time.monotonic()+5
            while proc.poll() is None and time.monotonic()<until:
                if select.select([master],[],[],.05)[0]:
                    try:os.read(master,65536)
                    except OSError:break
            try:proc.wait(timeout=1)
            except subprocess.TimeoutExpired:proc.kill();proc.wait();raise
            os.close(master)

    conf.write_text(original.replace('io_mode = False','io_mode = True').replace('io_graph_combined = False','io_graph_combined = True'))
    master,slave=pty.openpty();fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',60,160,0,0))
    proc=subprocess.Popen([str(root/'bin/btop'),'--utf-force'],stdin=slave,stdout=slave,stderr=slave,env=dict(os.environ,TERM='xterm-256color',XDG_CONFIG_HOME=tmp),start_new_session=True);os.close(slave)
    screen=pyte.Screen(160,60);stream=pyte.Stream(screen);decoder=codecs.getincrementaldecoder('utf-8')()
    try:
        drain(1.5)
        text='\n'.join(screen.display)
        assert 'RW' in text and 'root' in text, text
        os.write(master,b'i');drain(.7)
        assert 'MiB/s' in '\n'.join(screen.display)
        print('Combined I/O graph and return to normal history passed',flush=True)
    finally:
        os.write(master,b'q')
        until=time.monotonic()+5
        while proc.poll() is None and time.monotonic()<until:
            if select.select([master],[],[],.05)[0]:
                try:os.read(master,65536)
                except OSError:break
        try:proc.wait(timeout=1)
        except subprocess.TimeoutExpired:proc.kill();proc.wait();raise
        os.close(master)
