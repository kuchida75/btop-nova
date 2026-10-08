"""Read-only Nova counters plus terminal tests with process-local simulated swap."""
import pathlib, re, subprocess, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / 'tests'))
from nova_terminal import Terminal, config_with, root

def size(value, decimal=False):
    unit = 0; base = 1000 if decimal else 1024
    while value >= base:
        value /= base; unit += 1
    text = f'{value:.1f}' if unit else str(value)
    if len(text)+1 > 5: text = f'{value:.0f}'
    return text + 'BKMGTPE'[unit]

def row(term, token):
    result = next((i for i, line in enumerate(term.screen.display) if token in line), -1)
    assert result >= 0, (token, term.text())
    return result

def check(term, decimal=False, data=None):
    text = term.text(); zram = row(term, 'ZRAM zstd')
    (root / 'test-screen-zram-latest.txt').write_text(text)
    if data is None: data = [4294967296, 1073741824, 1207959552] # process-local fixture counters
    capacity = int(pathlib.Path('/sys/block/zram0/disksize').read_text())
    assert 'cap'+size(capacity, decimal) in term.screen.display[zram], text
    assert 'Data '+size(data[0], decimal)+'>'+size(data[1], decimal) in term.screen.display[zram+1], text
    saved = data[0]-data[2]
    assert 'RAM '+size(data[2], decimal)+' Save '+('-' if saved < 0 else '')+size(abs(saved), decimal) in term.screen.display[zram+2], text
    assert zram == row(term, '³net')-4, text
    assert 'Swap:' not in text and 'CrucialMX500' in text, text
    mem = row(term, '²mem')
    for metric in ('Total:', 'Used:', 'Available:', 'Cached:', 'Free:'):
        assert metric in '\n'.join(term.screen.display[mem:zram]), (metric, text)
    return zram

def check_hidden(term):
    text = term.text()
    assert 'ZRAM' not in text and 'Swap:' not in text, text
    memory = '\n'.join(term.screen.display[row(term, '²mem'):row(term, '³net')])
    for metric in ('Total:', 'Used:', 'Available:', 'Cached:', 'Free:'):
        assert metric in memory, (metric, text)

with tempfile.TemporaryDirectory(prefix='.nova-zram-', dir=root) as tmp:
    tmp = pathlib.Path(tmp)
    unit = tmp/'unit'; unit.mkdir()
    helper = tmp/'zram-test'
    subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra', '-Werror', str(root/'tests/nova_zram.cpp'), str(root/'src/btop_zram.cpp'), '-o', str(helper)], check=True)
    subprocess.run([str(helper), str(unit)], check=True)
    before = list(map(int, pathlib.Path('/sys/block/zram0/mm_stat').read_text().split()[:3]))
    dumped = subprocess.check_output([str(helper), '--dump'], text=True).splitlines()
    after = list(map(int, pathlib.Path('/sys/block/zram0/mm_stat').read_text().split()[:3]))
    fields = next(line.split('\t') for line in dumped if line.startswith('zram0\t'))
    assert fields[1] == 'zstd' and int(fields[2]) == int(pathlib.Path('/sys/block/zram0/disksize').read_text())
    if before == after: assert list(map(int, fields[3:6])) == before
    assert fields[6:8] == ['1','1'], fields
    print('Nova zram0 capacity, algorithm and all three byte counters agree with kernel sysfs; swap usage is read even with the swap box hidden', flush=True)

    library = tmp/'nvml'; library.mkdir()
    subprocess.run(['gcc', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror', str(root/'tests/nova_nvml_fixture.c'), '-o', str(library/'libnvidia-ml.so')], check=True)
    common = dict(io_mode='False', show_zram='True', show_swap='False', swap_disk='False', nova_layout='True', cpu_logical_graphs='False', proc_mounts='True', shown_boxes='"cpu mem net proc gpu0"', gpu_always_visible='True', gpu_nvtop_graph='True', gpu_processes='True', update_ms='500', mem_below_net='False', cpu_bottom='False', proc_left='False', base_10_sizes='False')

    # Match live visibility to actual usage; background applications may swap
    # between runs. Known active/idle transitions are tested with the shim.
    real = Terminal(config_with(**common), tmp, library)
    try:
        net = row(real, '³net')
        live_before = pathlib.Path('/sys/block/zram0/mm_stat').read_text()
        real.drain(.7)
        used = int(next(line.split()[3] for line in pathlib.Path('/proc/swaps').read_text().splitlines() if line.startswith('/dev/zram0')))
        if used == 0: check_hidden(real)
        elif live_before == pathlib.Path('/sys/block/zram0/mm_stat').read_text():
            check(real, data=list(map(int, live_before.split()[:3])))
        real.key('Z'); check_hidden(real)
        real.key('Z')
        assert row(real, '³net') == net
        (root / 'test-screen-zram-real.txt').write_text(real.text())
    finally: real.close()
    assert 'show_zram = True' in real.conf.read_text()
    print('Actual Nova: visibility matches kernel swap usage; real counters, preference and RAM/network layout retained', flush=True)

    fixture = tmp/'simulated'; fixture.mkdir()
    shim = tmp/'zram-fixture.so'
    subprocess.run(['gcc', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror', str(root/'tests/nova_zram_fixture.c'), '-ldl', '-o', str(shim)], check=True)
    extra = dict(LD_PRELOAD=str(shim), NOVA_TEST_ZRAM_FILES=str(fixture))
    def counters(active=True, unknown=False):
        values = 'unavailable' if unknown else '4294967296 1073741824 1207959552 0 0 0 0 0 0' if active else '4096 59 20480 0 20480 0 0 0 0'
        for name, text in {'mm_stat':values+'\n', 'swaps':'Filename Type Size Used Priority\n/dev/zram0 partition 62286956 '+('4194304' if active else '0')+' 100\n/swap.img file 8388604 0 -1\n'}.items():
            staged = fixture/(name+'.tmp'); staged.write_text(text); staged.replace(fixture/name)
    for symbol in ('braille', 'block', 'tty'):
        counters()
        term = Terminal(config_with(**common, graph_symbol_mem='"'+symbol+'"'), tmp, library, extra=extra)
        try:
            zram = check(term)
            net = row(term, '³net')
            assert '4.0x' in term.screen.display[zram+1], term.text()
            counters(False); term.drain(1.2); check_hidden(term)
            assert row(term, '³net') == net
            counters(); term.drain(1.2); check(term)
            assert row(term, '³net') == net
            counters(unknown=True); term.drain(1.2)
            assert 'Data -- (unavailable)' in term.text(), term.text()
            counters(); term.drain(1.2); check(term)
            term.key('Z'); assert 'ZRAM' not in term.text() and row(term, '³net') == net, term.text()
            term.key('Z'); check(term); assert row(term, '³net') == net
            term.key('f'); term.key('Z'); assert 'ZRAM' in term.text(), term.text()
            term.key('\x1b'); check(term)
            term.key('h'); assert 'Show/hide zram' in term.text(), term.text()
            term.key('\x1b'); check(term)
            for width,height in ((146,96), (110,60), (80,35), (200,100)):
                term.resize(width,height)
                if width >= 146: check(term)
                else: assert 'ZRAM' not in term.text(), term.text()
            (root / ('test-screen-zram-'+symbol+'.txt')).write_text(term.text())
        finally: term.close()
        assert 'show_zram = True' in term.conf.read_text()
        print(symbol+': simulated active → idle → active, unavailable data, preserved RAM metrics, fixed network height, toggles, filter focus, help and resize restoration passed', flush=True)

    decimal = dict(common, base_10_sizes='True')
    counters()
    term = Terminal(config_with(**decimal), tmp, library, extra=extra)
    try: check(term, decimal=True)
    finally: term.close()
    # Re-enabling the optional swap view keeps both summaries in a large panel.
    restored_swap = dict(common, show_swap='True')
    term = Terminal(config_with(**restored_swap), tmp, library, extra=extra)
    try:
        assert 'ZRAM' in term.text() and 'Swap:' in term.text(), term.text()
        assert 'Swap:' in '\n'.join(term.screen.display[:row(term, 'ZRAM')]), term.text()
    finally: term.close()
    print('Decimal sizes and explicitly restored swap view passed; no swap activity or memory pressure was generated', flush=True)
