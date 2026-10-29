"""Render a dense, labelled GPU dot preview with synthetic driver readings."""
import pathlib, re, subprocess, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent/'tests'))
from nova_terminal import Terminal, config_with, root

with tempfile.TemporaryDirectory(prefix='.nova-gpu-dots-', dir=root) as tmp:
    tmp = pathlib.Path(tmp)
    library = tmp/'nvml'; library.mkdir()
    subprocess.run(['gcc', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror', str(root/'tests/nova_nvml_fixture.c'), '-o', str(library/'libnvidia-ml.so')], check=True)
    config = config_with(shown_boxes='"gpu0"', gpu_always_visible='True', gpu_nvtop_graph='True', gpu_processes='True',
                         update_ms='100', graph_symbol_gpu='"braille"', tty_mode='False', truecolor='True')
    term = Terminal(config, tmp, library, width=146, height=30, extra={'NOVA_FIXTURE_DOT_WAVE':'1'})
    try:
        term.drain(15)
        lines = term.screen.display
        legend = next(i for i, line in enumerate(lines) if 'GCLK ' in line)
        stats_x = next(line for line in lines if 'Nova fixture GPU' in line).index('╭', 1)
        table = next(i for i, line in enumerate(lines) if 'GPU processes ' in line)
        plot = [cell for row in range(legend+1, table-1) for x,cell in term.screen.buffer[row].items() if 5 <= x < stats_x]
        dots = [cell for cell in plot if len(cell.data) == 1 and 0x2801 <= ord(cell.data) <= 0x28ff]
        (root/'test-screen-gpu-dots.txt').write_text(term.text())
        assert len(dots) > 100, (len(dots), stats_x, legend, table, term.text())
        assert {'5bc4d6','81a8f8','c3a6e8','72c9a0','e5ba73'} <= {cell.fg for cell in dots}
        assert not any(cell.data in '─│' for cell in plot)
        # Fine curves occupy individual left/right dot columns within a cell.
        masks = [ord(cell.data)-0x2800 for cell in dots]
        assert any(mask & 0x47 and mask & 0xb8 for mask in masks)
        from PIL import Image, ImageDraw, ImageFont
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf', 13)
        preview = Image.new('RGB', (term.screen.columns*8, (term.screen.lines+3)*17), '#111827')
        draw = ImageDraw.Draw(preview)
        draw.text((8,4), 'Nova — consistent dark slate theme; simulated readings for display testing', font=font, fill='#dbe4ef')
        for row in range(term.screen.lines):
            for col in range(term.screen.columns):
                cell = term.screen.buffer[row][col]
                color = '#'+cell.fg if re.fullmatch('[0-9a-fA-F]{6}', cell.fg) else '#d0d0d0'
                top = (row+2)*17
                if len(cell.data) == 1 and 0x2800 <= ord(cell.data) <= 0x28ff:
                    for bit,(dx,dy) in enumerate(((2,3),(2,6),(2,9),(5,3),(5,6),(5,9),(2,12),(5,12))):
                        if (ord(cell.data)-0x2800) & (1 << bit): draw.ellipse((col*8+dx,top+dy,col*8+dx+1,top+dy+1),fill=color)
                else: draw.text((col*8,top), cell.data, font=font, fill=color)
        preview.save(root/'nova-gpu-dots-preview.png')
        # The compact statistics retain every metric without crossing the
        # panel's right border, including odd widths and small windows.
        for width in (200, 153, 150, 146, 123, 110, 84, 80):
            term.resize(width, 30)
            screen = term.screen.display
            top = next(i for i, line in enumerate(screen) if 'Nova fixture GPU' in line)
            left = screen[top].index('╭', 1)
            stats_width = width - 1 - left
            assert 41 <= stats_width <= 52, (width, stats_width, term.text())
            assert width < 123 or left >= width * .64, (width, left, term.text())
            bottom = next(i for i in range(top+1, len(screen)) if 'TX:' in screen[i])
            stats = '\n'.join(line[left:width-1] for line in screen[top:bottom+1])
            for label in ('GPU ', 'PWR ', 'P-state:', 'Used:', 'Total:', 'Utilization:', 'TX:', 'RX:', 'Mhz', '°C'):
                assert label in stats, (width, label, stats)
            assert all(line[width-1:] == '│' for line in screen[top:bottom+1]), (width, term.text())
            assert 'GCLK ' in term.text() and 'GPU processes ' in term.text()
        term.resize(60, 30)
        assert 'GCLK ' not in term.text() and 'VRAM used ' in term.text()
        term.resize(146,30)
        assert 'GCLK ' in term.text() and 'GPU processes ' in term.text()
        print('Dense five-colour Braille curves, compact GPU statistics at 80–200 columns, process list and narrow-window fallback/restoration passed')
    finally: term.close()
    ascii_config = config_with(shown_boxes='"gpu0"', gpu_always_visible='True', gpu_nvtop_graph='True', gpu_processes='True',
                               graph_symbol_gpu='"default"', graph_symbol='"tty"', tty_mode='False')
    term = Terminal(ascii_config, tmp, library, width=146, height=30)
    try:
        assert 'GCLK ' in term.text()
        assert not any(len(cell.data) == 1 and 0x2801 <= ord(cell.data) <= 0x28ff for row in term.screen.buffer.values() for cell in row.values())
        print('Inherited general TTY setting uses ASCII dots without Unicode plot glyphs')
    finally: term.close()
