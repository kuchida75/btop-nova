"""GPU wattage history and lower-panel geometry with controlled NVML samples."""
import os,pathlib,re,subprocess,sys,tempfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'tests'))
from nova_terminal import Terminal,config_with,root

def power(term):
    y=next(y for y,line in enumerate(term.screen.display) if re.search(r'PWR (?:--|\d+\.\d)W \|',line))
    line=term.screen.display[y];x=line.index('PWR ')
    return y,x,term.screen.buffer[y][x].fg,line[x:].split('│')[0].strip()

def newest(term):
    y,x,color,_=power(term)
    left=next(line for line in term.screen.display if 'Nova fixture GPU' in line).index('╭',1)
    end=next(i for i,line in enumerate(term.screen.display) if 'GPU processes ' in line)
    return [(row,term.screen.buffer[row][left-1].data) for row in range(y+1,end-1)
            if term.screen.buffer[row][left-1].fg==color and
            len(term.screen.buffer[row][left-1].data)==1 and 0x2801<=ord(term.screen.buffer[row][left-1].data)<=0x28ff]

def panels(term):
    return {key:next(i for i,line in enumerate(term.screen.display) if label in line)
            for key,label in [('gpu','⁵gpu0'),('mem','²mem'),('net','³net'),('proc','⁴proc'),('mounts','mounts ')]}

with tempfile.TemporaryDirectory(prefix='.nova-gpu-power-',dir=root) as folder:
    tmp=pathlib.Path(folder);library=tmp/'nvml';library.mkdir()
    subprocess.run(['gcc','-shared','-fPIC','-Wall','-Wextra','-Werror',str(root/'tests/nova_nvml_fixture.c'),'-o',str(library/'libnvidia-ml.so')],check=True)
    mode=tmp/'power';mode.write_text('150000')
    common=dict(shown_boxes='"cpu mem net proc gpu0"',nova_layout='True',show_core_freq='True',
                gpu_nvtop_graph='True',gpu_processes='True',update_ms='500')
    term=Terminal(config_with(**common),tmp,library,width=146,height=87,extra={'NOVA_FIXTURE_POWER_FILE':str(mode)})
    try:
        b=panels(term)
        assert b['gpu']==17 and b['mem']-b['gpu']==27,(b,term.text())
        assert b['net']-b['mem']==14 and b['mounts']-b['net']>=8,(b,term.text())
        assert len(set(re.findall(r'\bC(\d+)\s+\d+%\s+\d+MHz',term.text())))==os.cpu_count(),term.text()
        assert 'PWR 150.0W | 0-300W' in power(term)[3],term.text()
        low=newest(term);assert low,term.text()
        mode.write_text('270000');term.drain(1.2)
        high=newest(term);assert high and max(y for y,_ in high)<min(y for y,_ in low),(low,high,term.text())
        assert 'PWR 270.0W | 0-300W' in power(term)[3],term.text()
        mode.write_text('325000');term.drain(1.2)
        assert 'PWR 325.0W | 0-350W' in power(term)[3],term.text()
        mode.write_text('x');term.drain(1.3)
        assert 'PWR --W' in power(term)[3] and not newest(term),term.text()
        mode.write_text('0');term.drain(1.3)
        assert 'PWR 0.0W' in power(term)[3] and newest(term),term.text()
        mode.write_text('150000');term.drain(1.2)
        assert 'PWR 150.0W' in power(term)[3] and newest(term),term.text()
        for label in ('GPU processes ','MiB/s','MOUNTED ON','FILESYSTEM','download','upload'):
            assert label in term.text(),(label,term.text())
        # User controls, process details and full keyboard help still work.
        term.key('\x1b[B');term.key('\n');assert 'Status:' in term.text()
        assert 'MOUNTED ON' in term.text();term.key('\n')
        term.key('N');assert not re.search(r'PWR (?:--|\d+\.\d)W \|',term.text())
        term.key('N');assert 'PWR 150.0W' in power(term)[3]
        term.key('h');assert 'keyboard shortcuts' in term.text();term.key('\x1b')
        for width,height in ((111,87),(100,70),(87,70),(80,35),(146,87)):
            term.resize(width,height)
            assert 'C0' in term.text() and 'MiB/s' in term.text(),term.text()
            if width>=87:
                assert 'PWR 150.0W' in power(term)[3] and 'GPU processes ' in term.text(),term.text()
        (root/'test-screen-gpu-power.txt').write_text(term.text())
        print('GPU 150/270/325 W, upward trace, scale extension, missing/stale gaps, zero/recovery, +3 GPU rows, CPU MHz, lower panels, controls/details/help and resize fallback passed',flush=True)
    finally:term.close()
    for extra in ({'NOVA_FIXTURE_POWER':'x'},{'NOVA_FIXTURE_POWER':'0'}):
        term=Terminal(config_with(**common),tmp,library,width=146,height=87,extra=extra)
        try:
            assert ('PWR --W' if extra['NOVA_FIXTURE_POWER']=='x' else 'PWR 0.0W') in power(term)[3],term.text()
        finally:term.close()
    for symbol in ('tty','braille'):
        term=Terminal(config_with(**dict(common,graph_symbol_gpu='"'+symbol+'"')),tmp,library,width=146,height=87)
        try:
            assert 'PWR 40.0W | 0-300W' in power(term)[3],term.text()
            if symbol=='tty':
                y=power(term)[0]
                assert all(not any(0x2801<=ord(c)<=0x28ff for c in line[1:95]) for line in term.screen.display[y+1:y+10]),term.text()
        finally:term.close()
print('Startup unsupported/zero power and ASCII/Braille modes passed',flush=True)
