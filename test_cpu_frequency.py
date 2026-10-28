"""Exercise the optional MHz layout with deterministic, process-local readings."""
import os, pathlib, re, subprocess, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / 'tests'))
from nova_terminal import Terminal, config_with, root

pattern = re.compile(r'\bC(\d+)\s+(?:\d+|--)%\s+(\d+|--)MHz')
count = os.cpu_count()

def readings(term, expected=True):
    found = {}
    for y, line in enumerate(term.screen.display):
        for match in pattern.finditer(line):
            index = int(match[1])
            assert index not in found, term.text()
            found[index] = (match[2], y, match.start())
    if not expected:
        assert not found, term.text()
        assert 'C0' in term.text(), term.text()
        return found
    assert set(found) == set(range(count)), (found, term.text())
    assert len({value[2] for value in found.values()}) == min(count, 3), found
    for value in found.values():
        assert term.screen.display[value[1]][-1] == '│', term.text()
    return found

with tempfile.TemporaryDirectory(prefix='.nova-cpu-frequency-', dir=root) as folder:
    tmp = pathlib.Path(folder); files = tmp/'files'; files.mkdir()
    # Keep model/topology fields while making missing per-thread samples unknown.
    cpuinfo = pathlib.Path('/proc/cpuinfo').read_text()
    (files/'cpuinfo').write_text(re.sub(r'^cpu MHz\s*:.*\n?', '', cpuinfo, flags=re.M))
    for index in range(count):
        path = files/f'cpu{index}/cpufreq'; path.mkdir(parents=True)
        (path/'scaling_cur_freq').write_text(str((1000 + index * 100)*1000))
        (path.parent/'online').write_text('1')
    shim = tmp/'readings.so'
    subprocess.run(['gcc','-shared','-fPIC','-Wall','-Wextra','-Werror',str(root/'tests/nova_cpu_frequency_fixture.c'),'-o',str(shim),'-ldl'],check=True)
    library = tmp/'nvml'; library.mkdir()
    subprocess.run(['gcc','-shared','-fPIC','-Wall','-Wextra','-Werror',str(root/'tests/nova_nvml_fixture.c'),'-o',str(library/'libnvidia-ml.so')],check=True)
    extra = {'LD_PRELOAD':str(shim),'NOVA_TEST_CPU_FILES':str(files)}
    common = dict(shown_boxes='"cpu mem net proc gpu0"',show_core_freq='True',update_ms='500',
                  gpu_always_visible='True',gpu_processes='True',gpu_nvtop_graph='True')
    term = Terminal(config_with(**common),tmp,library,width=146,height=80,extra=extra)
    try:
        found = readings(term)
        for index,(value,_,_) in found.items(): assert value == str(1000+index*100), found
        if count == 32:
            assert len({value[1] for value in found.values()}) == 11, found
        assert 'MOUNTED ON' in term.text() and 'GPU processes ' in term.text() and 'MiB/s' in term.text()
        memory_row = next(i for i,line in enumerate(term.screen.display) if '²mem' in line)
        (root/'test-screen-cpu-frequency.txt').write_text(term.text())
        # Readings refresh; absent/invalid/offline data cannot reuse old values.
        path = files/'cpu0/cpufreq/scaling_cur_freq'
        path.write_text('999000'); term.drain(1.1); assert readings(term)[0][0] == '999'
        path.unlink(); term.drain(1.1); assert readings(term)[0][0] == '--'
        path.write_text('broken'); term.drain(1.1); assert readings(term)[0][0] == '--'
        path.write_text('2500000'); term.drain(1.1); assert readings(term)[0][0] == '2500'
        (files/'cpu0/online').write_text('0'); term.drain(1.1); assert readings(term)[0][0] == '--'
        (files/'cpu0/online').write_text('1'); term.drain(1.1); assert readings(term)[0][0] == '2500'
        term.key('F'); readings(term,False)
        assert next(i for i,line in enumerate(term.screen.display) if '²mem' in line) < memory_row
        term.key('F'); readings(term)
        assert next(i for i,line in enumerate(term.screen.display) if '²mem' in line) == memory_row
        term.key('f');term.key('F');term.key('\x1b');readings(term) # Filter typing cannot toggle.
        # Three columns retain MHz at narrow widths; short frames still
        # fall back to the normal CPU view without altering the preference.
        for width in (132, 120, 112, 111, 100, 87):
            term.resize(width,80);readings(term)
            assert 'MOUNTED ON' in term.text() and 'GPU processes ' in term.text()
        term.resize(86,80);readings(term,False)
        term.resize(87,80);readings(term)
        term.key('F');readings(term,False)
        term.key('F');readings(term)
        term.resize(86,60);readings(term,False)
        term.resize(80,35);readings(term,False)
        term.resize(146,80);readings(term)
        term.key('h');assert 'per-thread mhz' in term.text().lower(),term.text()
        term.key('\x1b');readings(term)
        term.key('o');term.key('2')
        # Find and change the actual CPU option rather than only the shortcut.
        for _ in range(40):
            if 'Shift+F toggles up to three columns.' in term.text():break
            term.key('\x1b[B')
        else: raise AssertionError(term.text())
        term.key('\x1b[D');term.key('\x1b');readings(term,False)
        term.key('F');readings(term)
        for _ in range(4):
            term.key('p')
            if '¹cpu' in term.text():
                assert 'C0' in term.text()
            assert 'MOUNTED ON' in term.text() or '⁴proc' not in term.text()
        print('Three-column samples, refresh/unknown/offline transitions, saved toggle, filter focus, CPU options, help, presets, compact lower panels and resize restoration passed',flush=True)
    finally: term.close()
    assert 'show_core_freq = True' in term.conf.read_text()
    # Restart using the saved preference; exercise each native graph style and
    # layouts without temperatures or without the aggregate frequency setting.
    for values in ({'graph_symbol_cpu':'"block"'}, {'graph_symbol_cpu':'"tty"'},
                   {'force_tty':'True'}, {'show_coretemp':'False'}, {'check_temp':'False'},
                   {'show_cpu_freq':'False'}, {'cpu_bottom':'True'},
                   {'temp_scale':'"fahrenheit"'}, {'temp_scale':'"kelvin"'}, {'temp_scale':'"rankine"'}):
        term = Terminal(config_with(**dict(common,**values)),tmp,library,width=200,height=100,extra=extra)
        try:
            readings(term)
            term.resize(111,80);readings(term)
        finally: term.close()
    print('Block/TTY/16-colour rendering, hidden temperatures, independent header-frequency option and CPU-bottom passed',flush=True)
    term = Terminal(config_with(shown_boxes='"cpu"',gpu_always_visible='False',show_core_freq='True'),tmp,library,width=146,height=24,extra=extra)
    try:
        readings(term)
        term.resize(80,24);readings(term,False)
        term.resize(146,24);readings(term)
    finally:term.close()
    print('CPU-only layout and small-window restoration passed; no host files or frequency settings were changed',flush=True)
    term = Terminal(config_with(shown_boxes='"cpu"',show_gpu_info='"Off"',gpu_always_visible='False',show_core_freq='True',
                               cpu_graph_upper='"user"',cpu_graph_lower='"system"',cpu_single_graph='False'),tmp,library,width=111,height=24,extra=extra)
    try:
        readings(term)
        assert 'user ▲▼ system' in term.text(),term.text()
        term.resize(87,24);readings(term)
        assert 'use ▲▼ sys' in term.text(),term.text()
        term.resize(200,24);readings(term)
        term.resize(111,24);readings(term)
    finally:term.close()
    print('Compact history labels and CPU-only 111-column resize passed',flush=True)
