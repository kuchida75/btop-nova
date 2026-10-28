"""Check tightly fitted CPU height, lower-panel space and process interaction."""
import os,pathlib,re,subprocess,sys,tempfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'tests'))
from nova_terminal import Terminal,config_with,root

frequency=re.compile(r'\bC(\d+)\s+\d+%\s+(?:\d+|--)MHz')
def row(term,label):
    return next(i for i,line in enumerate(term.screen.display) if label in line)
def bounds(term):
    return {key:row(term,label) for key,label in [('gpu','⁵gpu0'),('mem','²mem'),('net','³net'),('proc','⁴proc'),('mounts','mounts ')]}
def compact(term):
    b=bounds(term)
    net_end=b['mem'] if b['net']<b['mem'] else b['mounts']
    assert net_end-b['net']>=8,(b,term.text())
    # The bottom placement draws its title on the bottom border.
    first_core=next(i for i,line in enumerate(term.screen.display) if frequency.search(line))
    cpu_top=0 if row(term,'¹cpu')==0 else first_core-3
    cpu_height=b['gpu'] if cpu_top==0 else term.screen.lines-cpu_top
    assert cpu_height==17,(cpu_height,b,term.text())
    mem_end=b['net'] if b['mem']<b['net'] else b['mounts']
    assert mem_end-b['mem']==14,(b,term.text())
    # The process title moves below the eight-row details box when opened.
    assert b['mounts']-min(b['mem'],b['net'])>=22,(b,term.text())
    assert {int(m[1]) for line in term.screen.display for m in frequency.finditer(line)}==set(range(os.cpu_count())),term.text()
    assert len({m.start() for line in term.screen.display for m in frequency.finditer(line)})==3
    for label in ('Total:','Used:','Free:','MiB/s','MOUNTED ON','GPU processes '):
        assert label in term.text(),(label,term.text())
    assert 'Available:' in term.text() or 'Avail:' in term.text()
    assert 'Cached:' in term.text() or 'Cache:' in term.text()
    return b

with tempfile.TemporaryDirectory(prefix='.nova-cpu-space-',dir=root) as folder:
    tmp=pathlib.Path(folder);library=tmp/'nvml';library.mkdir()
    subprocess.run(['gcc','-shared','-fPIC','-Wall','-Wextra','-Werror',str(root/'tests/nova_nvml_fixture.c'),'-o',str(library/'libnvidia-ml.so')],check=True)
    common=dict(shown_boxes='"cpu mem net proc gpu0"',show_core_freq='True',nova_layout='True',proc_sorting='"cpu direct"',update_ms='500',gpu_always_visible='True',gpu_nvtop_graph='True',gpu_processes='True')
    worker=subprocess.Popen([sys.executable,'-c','import time; end=time.monotonic()+120\nwhile time.monotonic()<end: pass'])
    term=Terminal(config_with(**common),tmp,library,width=146,height=80)
    try:
        term.drain(1.2);initial=compact(term)
        assert str(worker.pid) in '\n'.join(term.screen.display[initial['proc']:initial['mounts']]),term.text()
        # Keep selection, details and paging usable in the expanded process list.
        term.key('\x1b[B');term.key('\n');assert 'Status:' in term.text()
        compact(term)
        term.key('\n');assert 'Status:' not in term.text();compact(term)
        term.key('\x1b[6~');assert re.search(r'\b\d+/\d+',term.text())
        term.key('\x1b[H');compact(term)
        term.key('e');compact(term);term.key('e');compact(term)
        term.key('f');term.key('no_such_process');term.key('\n');compact(term)
        term.key('\x1b[3~');compact(term)
        # Reading network controls must remain usable after the space is returned.
        for key in ('a','a','y','y','z','z','n','b'):
            term.key(key);compact(term)
        network='\n'.join(term.screen.display[initial['net']:initial['mounts']])
        assert 'download' in network and 'upload' in network and network.count('Total:')==2,network
        term.key('B');compact(term);term.key('B');compact(term)
        term.key('M');assert 'MOUNTED ON' not in term.text()
        term.key('M');compact(term)
        for width,height in ((146,150),(111,80),(100,70),(87,70)):
            term.resize(width,height);compact(term)
        term.resize(87,60);assert 'C0' in term.text() and 'MiB/s' in term.text()
        term.resize(80,35);assert 'C0' in term.text() and 'MiB/s' in term.text()
        term.resize(146,80);compact(term)
        for key in ('1','4','3'):
            term.key(key);assert term.proc.poll() is None
            term.key(key);compact(term)
        term.key('h');assert 'keyboard shortcuts' in term.text()
        term.key('\x1b');compact(term)
        (root/'test-screen-cpu-space.txt').write_text(term.text())
    finally:
        term.close();worker.terminate();worker.wait(timeout=5)
    saved=dict(re.findall(r'^(\w+)\s*=\s*(.*)$',term.conf.read_text(),re.M))
    assert saved['proc_sorting']=='"cpu direct"' and saved['show_core_freq']=='True'
    for values in ({'cpu_bottom':'True'},{'proc_left':'True'},{'mem_below_net':'True'},
                   {'cpu_bottom':'True','proc_left':'True','mem_below_net':'True'},
                   {'show_swap':'True','swap_disk':'False'}):
        term=Terminal(config_with(**dict(common,**values)),tmp,library,width=146,height=100)
        try:
            if 'show_swap' not in values:compact(term)
            else:
                assert 'Swap:' in term.text() and 'MOUNTED ON' in term.text()
                assert 'GPU processes ' in term.text()
            assert len({int(m[1]) for line in term.screen.display for m in frequency.finditer(line)})==os.cpu_count()
        finally:term.close()
    term=Terminal(config_with(**dict(common,nova_layout='False')),tmp,library,width=146,height=100)
    try:
        assert 'C0' in term.text() and term.proc.poll() is None
        assert term.screen.lines-row(term,'³net')>8
    finally:term.close()
print('Tightly fitted three-column CPU, expanded network/process space, network totals/controls, top-process visibility, selection/details/paging/filter/tree, mounts, boot toggle, sorting persistence, alternate layouts and short-window restoration passed',flush=True)
