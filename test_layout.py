"""Real-terminal layout tests; GPU readings come only from the local test fixture."""
import os, pathlib, re, subprocess, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "tests"))
from nova_terminal import Terminal, config_with, root

def row(term, token):
    result = next((i for i, line in enumerate(term.screen.display) if token in line), -1)
    assert result >= 0, (token, term.text())
    return result

def boundaries(term):
    return {name: row(term, token) for name, token in [('cpu','¹cpu'), ('gpu','⁵gpu0'), ('mem','²mem'), ('net','³net'), ('proc','⁴proc')]}

def full_mounts(term):
    (root / 'test-screen-layout-latest.txt').write_text(term.text())
    title = row(term, 'mounts 5 local')
    assert term.screen.display[title].index('mounts ') < 5, term.text()
    assert title == term.screen.lines - 9, term.text()
    for token in ('MOUNTED ON', 'SIZE', 'USED', 'AVAIL', 'USE%', 'TYPE', 'FILESYSTEM'):
        assert token in term.screen.display[title + 1], term.text()
    for path in ('/boot', '/boot/efi', '/mnt/Crucial4TB', '/mnt/CrucialMX500'):
        assert path in term.text(), term.text()
    assert '/dev/mapper/ubuntu--vg-ubuntu--lv' in term.text(), term.text()
    assert 'binary | Shift+M hide' in term.screen.display[-1], term.text()
    assert 'Swap:' not in term.text(), term.text()
    assert row(term, '³net') < title and row(term, '⁴proc') < title
    # Table has the full terminal width, including the bottom-right border.
    assert term.screen.display[title][0] in '┌╭' and term.screen.display[title][-1] in '┐╮', term.text()
    return title

with tempfile.TemporaryDirectory(prefix='.nova-layout-', dir=root) as tmp:
    tmp = pathlib.Path(tmp)
    library = tmp / 'nvml'; library.mkdir()
    subprocess.run(['gcc', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror', str(root / 'tests/nova_nvml_fixture.c'), '-o', str(library / 'libnvidia-ml.so')], check=True)
    common = dict(io_mode='False', proc_mounts='True', cpu_logical_graphs='False', show_boot_disks='False', gpu_always_visible='True', gpu_split_vram='True', gpu_nvtop_graph='True', gpu_processes='True', update_ms='500', shown_boxes='"cpu mem net proc gpu0"', cpu_bottom='False', mem_below_net='False', proc_left='False', swap_disk='False', proc_sorting='"pid"')
    baseline = Terminal(config_with(**common, nova_layout='False', show_swap='True'), tmp, library)
    try:
        old = boundaries(baseline)
        old_table = row(baseline, 'mounts 5 local')
        old_network_height = baseline.screen.lines - old['net']
        (root / 'test-screen-layout-before.txt').write_text(baseline.text())
    finally: baseline.close()

    term = Terminal(config_with(**common, nova_layout='True', show_swap='False'), tmp, library)
    try:
        new = boundaries(term)
        bottom = full_mounts(term)
        assert new['gpu'] < old['gpu'], (new, old)
        assert new['mem'] == old['mem'], (new, old)
        assert new['net'] < old['net'], (new, old)
        assert bottom - new['net'] >= old_network_height, (new, old)
        assert 'GPU processes ' in term.text() and 'GCLK ' in term.text()
        assert 'CrucialMX500' in '\n'.join(term.screen.display[new['mem']:bottom]), term.text()
        assert 'Free:' in '\n'.join(term.screen.display[new['mem']:new['net']]), term.text()
        print(f'200x100: CPU {old["gpu"]} → {new["gpu"]} rows; GPU {old["mem"]-old["gpu"]} → {new["mem"]-new["gpu"]}; network starts {old["net"]+1} → {new["net"]+1}; full-width table shows all device paths', flush=True)
        term.drain(3)
        (root / 'test-screen-layout-after.txt').write_text(term.text())
        from PIL import Image, ImageDraw, ImageFont
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf', 13)
        preview = Image.new('RGB', (1600, (term.screen.lines+3)*17), '#101218')
        draw = ImageDraw.Draw(preview)
        draw.text((8, 4), 'Nova io9 layout — synthetic GPU readings; actual Nova mounts; idle zram hidden', font=font, fill='white')
        for line in range(term.screen.lines):
            for col in range(term.screen.columns):
                cell = term.screen.buffer[line][col]
                color = '#' + cell.fg if re.fullmatch('[0-9a-fA-F]{6}', cell.fg) else '#d0d0d0'
                if len(cell.data) == 1 and 0x2800 <= ord(cell.data) <= 0x28ff:
                    dots = ord(cell.data) - 0x2800
                    for bit, (dx, dy) in enumerate(((2,3),(2,6),(2,9),(5,3),(5,6),(5,9),(2,12),(5,12))):
                        if dots & (1 << bit): draw.ellipse((col*8+dx, (line+2)*17+dy, col*8+dx+1, (line+2)*17+dy+1), fill=color)
                else: draw.text((col*8, (line+2)*17), cell.data, font=font, fill=color)
        preview.save(root / 'nova-layout-preview.png')

        # Informational mount cells across both columns ignore selection/scroll.
        term.key('\x1b[B')
        footer = term.screen.display[bottom-1]
        assert re.search(r'\b1/\d+', footer), footer
        proc_column = term.screen.display[new['proc']].index('╭', 1)
        first_process = re.search(r'\d+', term.screen.display[new['proc']+2][proc_column:]).group()
        for col in (8, 160):
            for code in (0, 65):
                term.key(f'\x1b[<{code};{col};{bottom+4}M')
                assert re.search(r'\b1/\d+', term.screen.display[bottom-1]), term.text()
                assert re.search(r'\d+', term.screen.display[new['proc']+2][proc_column:]).group() == first_process, term.text()
        term.key('\n'); assert 'Status:' in term.text(), term.text()
        full_mounts(term)
        term.key('\n'); assert 'Status:' not in term.text(); full_mounts(term)
        term.key('M'); assert 'MOUNTED ON' not in term.text()
        assert row(term, '³net') == new['net'], term.text()
        term.key('M'); full_mounts(term)
        term.key('L')
        assert len(set(re.findall(r'\bCPU(\d+)\b', term.text()))) == 32, term.text()
        assert boundaries(term)['gpu'] == 18, term.text()
        full_mounts(term)
        term.key('L'); assert boundaries(term)['gpu'] == new['gpu']
        term.key('B'); assert 'efi' in '\n'.join(term.screen.display[new['mem']:bottom]), term.text()
        term.key('B'); full_mounts(term)
        term.key('U'); assert 'GPU processes ' not in term.text()
        term.key('U'); full_mounts(term)
        term.key('h'); assert 'Show/hide the mounted' in term.text(), term.text()
        term.key('\x1b'); full_mounts(term)
        for width, height in ((146,96), (110,60), (80,35), (200,100)):
            term.resize(width, height)
            if width == 80:
                assert 'MOUNTED ON' not in term.text(), term.text()
                assert 'GPU processes ' not in term.text(), term.text()
            elif width >= 146: full_mounts(term)
        print('Shared table mouse bounds, details, toggles, logical-grid preservation, help and shrink/grow fallback passed', flush=True)
        for _ in range(4):
            term.key('p')
            assert 'gpu0' in term.text(), term.text()
            if 'mounts ' in term.text():
                assert 'MOUNTED ON' in term.text(), term.text()
        print('Four presets including CPU-bottom placement passed', flush=True)
    finally: term.close()
    saved = term.conf.read_text()
    assert 'nova_layout = True' in saved and 'show_swap = False' in saved

    for alternate in (dict(proc_left='True'), dict(mem_below_net='True'), dict(cpu_bottom='True'), dict(shown_boxes='"mem net proc gpu0"'), dict(shown_boxes='"cpu mem net gpu0"')):
        values = dict(common, nova_layout='True', show_swap='False'); values.update(alternate)
        term = Terminal(config_with(**values), tmp, library)
        try:
            text = term.text()
            assert 'GPU processes ' in text, text
            if 'proc' not in alternate.get('shown_boxes', 'proc'): assert 'MOUNTED ON' not in text, text
            elif alternate.get('cpu_bottom') == 'True':
                assert row(term, 'MOUNTED ON') < row(term, '⁵gpu0') < row(term, '¹cpu'), text
                assert '/dev/mapper/ubuntu--vg-ubuntu--lv' in text, text
            else: full_mounts(term)
        finally: term.close()
    print('Process-left, network-above-memory, CPU-bottom, CPU-hidden and process-hidden layouts passed', flush=True)
