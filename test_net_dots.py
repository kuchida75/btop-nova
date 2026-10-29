"""Dot network rendering with controlled counters; never generates real traffic."""
import pathlib,re,subprocess,sys,tempfile,threading,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'tests'))
from nova_terminal import Terminal,config_with,root

def bounds(term):
    start=next(i for i,line in enumerate(term.screen.display) if '³net' in line)
    end=next((i for i,line in enumerate(term.screen.display) if 'mounts ' in line),term.screen.lines)
    return start,end

def legend(term):
    start,end=bounds(term)
    y=next((y for y in range(start+1,end) if 'DL ' in term.screen.display[y] and 'UL ' in term.screen.display[y]),-1)
    assert y>=0,term.text()
    return y

def latest(term,direction):
    top=legend(term);line=term.screen.display[top];x=line.index('DL ' if direction==0 else 'UL ')
    color=term.screen.buffer[top][x].fg
    start,end=bounds(term);net_width=term.screen.display[start].index('╮')+1
    stats_width=27 if net_width>55 else 19;column=net_width-stats_width-2
    return [y for y in range(top+2,end-2) if term.screen.buffer[y][column].fg==color and
            len(term.screen.buffer[y][column].data)==1 and 0x2801<=ord(term.screen.buffer[y][column].data)<=0x28ff]

def check(term):
    y=legend(term);_,end=bounds(term)
    assert '0-' in term.screen.display[y+1] and '/s' in term.screen.display[y+1],term.text()
    text='\n'.join(term.screen.display[y:end])
    for word in ('download','upload','Total:'):assert word in term.text(),(word,term.text())
    assert text.count('Total:')==2,text
    return y

with tempfile.TemporaryDirectory(prefix='.nova-net-dots-',dir=root) as folder:
    tmp=pathlib.Path(folder);library=tmp/'nvml';library.mkdir();counters=tmp/'counters';counters.mkdir()
    subprocess.run(['gcc','-shared','-fPIC','-Wall','-Wextra','-Werror',str(root/'tests/nova_nvml_fixture.c'),'-o',str(library/'libnvidia-ml.so')],check=True)
    shim=tmp/'network.so';subprocess.run(['gcc','-shared','-fPIC','-Wall','-Wextra','-Werror',str(root/'tests/nova_net_fixture.c'),'-ldl','-o',str(shim)],check=True)
    state={'rates':[256*1024,64*1024]};totals=[1000000.,1000000.];stop=threading.Event()
    def write(name,text):
        stage=counters/(name+'.new');stage.write_text(text);stage.replace(counters/name)
    for name in ('rx_bytes','tx_bytes'):write(name,'1000000')
    write('state','up')
    def writer():
        previous=time.monotonic()
        while not stop.wait(.015):
            now=time.monotonic()
            for i,name in enumerate(('rx_bytes','tx_bytes')):
                totals[i]+=(now-previous)*state['rates'][i];write(name,str(round(totals[i])))
            previous=now
    worker=threading.Thread(target=writer);worker.start()
    common=dict(shown_boxes='"cpu mem net proc gpu0"',show_core_freq='True',nova_layout='True',net_iface='"lo"',
                net_dot_graph='True',net_auto='False',net_sync='True',net_download='8',net_upload='8',update_ms='500',
                gpu_always_visible='True',gpu_nvtop_graph='True',gpu_processes='True')
    extra=dict(LD_PRELOAD=str(shim),NOVA_TEST_NET_FILES=str(counters))
    term=None
    try:
        term=Terminal(config_with(**common),tmp,library,width=146,height=87,extra=extra);term.drain(1)
        y=check(term);low=latest(term,0);assert low and latest(term,1),term.text()
        assert '1.00 MiB/s' in term.screen.display[y+1],term.text()
        dl=term.screen.buffer[y][term.screen.display[y].index('DL ')].fg
        ul=term.screen.buffer[y][term.screen.display[y].index('UL ')].fg
        assert dl!=ul,(dl,ul)
        state['rates']=[768*1024,64*1024];term.drain(1.3);high=latest(term,0)
        assert high and max(high)<min(low),(low,high,term.text())
        state['rates']=[0,0];term.drain(1.3);check(term)
        assert 'DL 0 Byte/s' in term.text() and 'UL 0 Byte/s' in term.text(),term.text()
        write('state','down');term.drain(1.3)
        assert 'DL --' in term.text() and 'UL --' in term.text() and not latest(term,0) and not latest(term,1),term.text()
        write('state','up');state['rates']=[256*1024,64*1024];term.drain(1.3);check(term);assert latest(term,0)
        # Scale and interface/reset controls still apply to both curves.
        for key in ('a','y','z','z','n','b','y','a'):
            term.key(key);check(term)
        assert '1.00 MiB/s' in term.screen.display[legend(term)+1],term.text()
        # Toggle the real NET option, retaining the earlier view and restoring dots.
        term.key('o');term.key('5')
        for _ in range(16):
            if 'Upward download/upload dot histories.' in term.text():break
            term.key('\x1b[B')
        else:raise AssertionError(term.text())
        term.key('\x1b[D');term.key('\x1b')
        assert 'DL ' not in '\n'.join(term.screen.display[bounds(term)[0]:bounds(term)[1]]),term.text()
        term.key('o');term.key('5')
        for _ in range(16):
            if 'Upward download/upload dot histories.' in term.text():break
            term.key('\x1b[B')
        else:raise AssertionError(term.text())
        term.key('\x1b[C');term.key('\x1b');check(term)
        for width,height in ((111,87),(100,70),(80,35),(146,87)):
            term.resize(width,height)
            if width>=100:check(term)
            else:assert 'DL ' not in term.text() and 'upload' in term.text(),term.text()
        term.drain(1);(root/'test-screen-net-dots.txt').write_text(term.text())
        print('Known download/upload rates, dual colours/upward traces, fixed/auto/sync scales, zero/disconnection/recovery, interface/reset controls, NET option and narrow fallback passed',flush=True)
        term.close();term=None
        assert 'net_dot_graph = True' in (tmp/'btop/btop.conf').read_text()
        for values in ({'graph_symbol_net':'"tty"'},{'graph_symbol_net':'"default"','graph_symbol':'"tty"'},{'net_sync':'False','net_upload':'16'}):
            term=Terminal(config_with(**dict(common,**values)),tmp,library,width=146,height=87,extra=extra);check(term)
            if 'graph_symbol_net' in values:
                start,end=bounds(term);assert not any(0x2801<=ord(c)<=0x28ff for line in term.screen.display[start+1:end-1] for c in line[1:38]),term.text()
            else:assert '2.00 MiB/s' in term.screen.display[legend(term)+1],term.text()
            term.close();term=None
        print('Saved option, inherited/direct ASCII mode and independent upload/download scales passed',flush=True)
    finally:
        try:
            if term:
                term.close()
        finally:stop.set();worker.join(timeout=3)
