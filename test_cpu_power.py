"""Exercise package watts, plot orientation/scales, missing data and saved options."""
import os,pathlib,re,subprocess,sys,tempfile,threading,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'tests'))
from nova_terminal import Terminal,config_with,root

def watts(term):
    values=re.findall(r'\bPKG\s+(\d+\.\d)W',term.text(),re.I)
    assert values,term.text()
    return float(values[0])
def pkg_color(term):
    y=next(i for i,line in enumerate(term.screen.display) if 'PKG ' in line)
    x=term.screen.display[y].index('PKG ')
    return term.screen.buffer[y][x].fg
def latest_power_rows(term):
    # At 146 columns the 73-column MHz table leaves 71 plot columns.
    color=pkg_color(term)
    return [y for y in range(3,15) if any(term.screen.buffer[y][x].fg==color and
            len(term.screen.buffer[y][x].data)==1 and 0x2800<=ord(term.screen.buffer[y][x].data)<=0x28ff for x in (71,))]

with tempfile.TemporaryDirectory(prefix='.nova-cpu-power-',dir=root) as folder:
    tmp=pathlib.Path(folder);cap=tmp/'powercap';package=cap/'intel-rapl:0';package.mkdir(parents=True)
    (package/'name').write_text('package-0');(package/'max_energy_range_uj').write_text('1000000000000')
    energy=package/'energy_uj';energy.write_text('100000000')
    shim=tmp/'readings.so';library=tmp/'nvml';library.mkdir()
    subprocess.run(['gcc','-shared','-fPIC','-Wall','-Wextra','-Werror',str(root/'tests/nova_cpu_power_fixture.c'),'-o',str(shim),'-ldl'],check=True)
    subprocess.run(['gcc','-shared','-fPIC','-Wall','-Wextra','-Werror',str(root/'tests/nova_nvml_fixture.c'),'-o',str(library/'libnvidia-ml.so')],check=True)
    extra={'LD_PRELOAD':str(shim),'NOVA_TEST_POWER_FILES':str(cap)}
    stopped=threading.Event();state={'rate':42500,'bad':False};total=100000000
    def writer():
        global total
        previous=time.monotonic()
        while not stopped.wait(.01):
            now=time.monotonic();total+=round((now-previous)*state['rate']*1000);previous=now
            staged=energy.with_suffix('.new');staged.write_text('bad' if state['bad'] else str(total));staged.replace(energy)
    thread=threading.Thread(target=writer);thread.start()
    common=dict(shown_boxes='"cpu mem net proc gpu0"',show_core_freq='True',show_cpu_power='True',nova_layout='True',
                cpu_single_graph='False',cpu_invert_lower='True',update_ms='500',gpu_always_visible='True',gpu_processes='True',gpu_nvtop_graph='True')
    term=Terminal(config_with(**common),tmp,library,width=146,height=87,extra=extra)
    try:
        term.drain(1)
        assert 40<=watts(term)<=45,term.text()
        assert 'CPU 0-100%' in term.text() and 'Power 0-50W' in term.text(),term.text()
        assert next(y for y,line in enumerate(term.screen.display) if '⁵gpu0' in line)==17,term.text()
        assert len(set(re.findall(r'\bC(\d+)\s+\d+%\s+\d+MHz',term.text())))==os.cpu_count(),term.text()
        rows=latest_power_rows(term)
        assert rows and max(rows)<9,(rows,term.text()) # Watts rise from the bottom; no mirrored lower copy.
        state['rate']=125000;term.drain(1.2)
        assert 120<=watts(term)<=130 and 'Power 0-150W' in term.text(),term.text()
        state['bad']=True;term.drain(1.6)
        assert 'PKG --W' in term.text() and 'Pkg --W' in term.text(),term.text()
        assert not latest_power_rows(term),term.text() # Missing counters leave gaps, not zero points or stale values.
        state['bad']=False;state['rate']=42500;term.drain(1.6)
        assert 40<=watts(term)<=45,term.text()
        for width,height in ((111,87),(100,87),(87,87),(80,35),(146,87)):
            term.resize(width,height)
            if width>=87:assert re.search(r'\bPkg\s+\d+\.\dW',term.text()),term.text()
            assert 'C0' in term.text() and 'MiB/s' in term.text(),term.text()
            if width>=87:assert 'GPU processes ' in term.text(),term.text()
        # Toggle the actual CPU option and restore the configured ordinary graph.
        term.key('o');term.key('2')
        for _ in range(40):
            if 'CPU package watts and CPU/power dot history.' in term.text():break
            term.key('\x1b[B')
        else:raise AssertionError(term.text())
        term.key('\x1b[D');term.key('\x1b')
        assert 'PKG ' not in term.text() and 'Pkg ' not in term.text(),term.text()
        term.key('o');term.key('2')
        for _ in range(40):
            if 'CPU package watts and CPU/power dot history.' in term.text():break
            term.key('\x1b[B')
        else:raise AssertionError(term.text())
        term.key('\x1b[C');term.key('\x1b');term.drain(1.1)
        assert 40<=watts(term)<=45,term.text()
        (root/'test-screen-cpu-power.txt').write_text(term.text())
    finally:
        term.close();stopped.set();thread.join(timeout=2)
    saved=dict(re.findall(r'^(\w+)\s*=\s*(.*)$',term.conf.read_text(),re.M))
    assert saved['show_cpu_power']=='True' and saved['cpu_single_graph']=='False' and saved['cpu_invert_lower']=='True',saved
    for symbol in ('tty','braille','block'):
        # Constant counters legitimately produce 0.0 W; render styles and missing access must remain usable.
        term=Terminal(config_with(**dict(common,graph_symbol_cpu='"'+symbol+'"')),tmp,library,width=146,height=87,extra=extra)
        try:
            assert watts(term)==0,term.text()
            if symbol=='tty':
                assert all(not any(0x2800<=ord(c)<=0x28ff for c in line[1:72]) for line in term.screen.display[1:16]),term.text()
        finally:term.close()
    os.chmod(energy,0)
    term=Terminal(config_with(**common),tmp,library,width=146,height=87,extra=extra)
    try:
        assert 'PKG --W' in term.text() and 'read access needed' in term.text(),term.text()
    finally:term.close();os.chmod(energy,0o600)
print('Known wattage, dynamic scale, upward-only dual traces, unknown gaps/recovery, 32 MHz readings, small-window fallback, menu persistence, TTY/Braille/block, true zero and denied counters passed',flush=True)
