"""Check palette readability, live theme switching and terminal colour fallbacks."""
import pathlib, re, subprocess, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent/'tests'))
from nova_terminal import Terminal, config_with, root

theme = (root/'themes/Nova.theme').read_text()
palette = dict(re.findall(r'theme\[(\w+)\]="([^"]*)"', theme))

def luminance(hex_color):
    rgb = [int(hex_color[i:i+2], 16)/255 for i in (1, 3, 5)]
    linear = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in rgb]
    return sum(a*b for a,b in zip(linear, (.2126,.7152,.0722)))

def contrast(fg, bg):
    a,b = sorted((luminance(fg),luminance(bg)))
    return (b+.05)/(a+.05)

for key in ('main_fg','title','hi_fg','inactive_fg','graph_text','gpu_load','gpu_vram','gpu_clock','gpu_mem_clock','gpu_power','disk_read','disk_write','disk_used','status_ok','status_warning','status_critical'):
    assert contrast(palette[key], palette['main_bg']) >= 4.5, key
assert contrast(palette['selected_fg'], palette['selected_bg']) >= 4.5
assert palette['gpu_load'] == palette['cpu_start'] == palette['download_start']
assert palette['gpu_vram'] == palette['used_start'] == palette['upload_start']
assert len({palette[key] for key in ('cpu_box','mem_box','net_box','proc_box')}) == 1
print('Text, selection and chart contrast; shared activity/I/O and memory colours passed', flush=True)

def legends(term):
    screen = term.screen.display
    clock_row = next(i for i,line in enumerate(screen) if 'GCLK ' in line)
    result = {}
    for row,labels in ((clock_row-1,('GPU ','VRAM ')),(clock_row,('GCLK ','MCLK '))):
        for label in labels:
            col = screen[row].index(label)
            result[label.strip()] = term.screen.buffer[row][col].fg
    return result

with tempfile.TemporaryDirectory(prefix='.nova-theme-', dir=root) as name:
    tmp = pathlib.Path(name); library=tmp/'lib'; library.mkdir()
    subprocess.run(['gcc','-shared','-fPIC','-Wall','-Wextra','-Werror',str(root/'tests/nova_nvml_fixture.c'),'-o',str(library/'libnvidia-ml.so')],check=True)
    fresh=Terminal('',tmp,library)
    fresh.close()
    generated=fresh.conf.read_text()
    assert 'color_theme = "Nova"' in generated and 'proc_gradient = False' in generated
    print('Fresh source-build profile selects Nova and readable process rows', flush=True)
    common = dict(shown_boxes='"cpu mem net proc"',gpu_always_visible='True',gpu_nvtop_graph='True',gpu_processes='True',update_ms='500')
    term = Terminal(config_with(**common),tmp,library)
    try:
        assert legends(term) == dict(GPU='5bc4d6',VRAM='81a8f8',GCLK='c3a6e8',MCLK='72c9a0')
        screen=term.screen.display
        # Every outer panel uses the same border; table headers share titles.
        for label in ('¹cpu','⁵gpu0','²mem','³net','⁴proc','mounts '):
            row=next(i for i,line in enumerate(screen) if label in line)
            label_col=screen[row].index(label)
            corner=screen[row].rfind('╭',0,label_col)
            assert corner >= 0 and term.screen.buffer[row][corner].fg == '526579', (label,screen[row])
        for label in ('MOUNTED ON','PID     USER'):
            row=next(i for i,line in enumerate(screen) if label in line)
            col=screen[row].index(label)
            assert term.screen.buffer[row][col].fg == 'f0f6fc', label
        # Read/write labels match incoming/outgoing network and PCIe roles.
        for label,color in (('R ', '5bc4d6'),('W ', '81a8f8'),('TX:', '81a8f8'),('RX:', '5bc4d6')):
            row=next(i for i,line in enumerate(screen) if (label in line if label in ('TX:','RX:') else re.search(r'\b'+re.escape(label)+r'[\d ]',line)))
            col=screen[row].index(label)
            assert term.screen.buffer[row][col].fg == color, (label,term.screen.buffer[row][col])
        # Disk capacity uses health for percent and the shared used-memory colour
        # for bytes, even when both values appear on the same compact row.
        disk_row=next(i for i,line in enumerate(screen) if re.search(r'Used \d+%',line))
        used=re.search(r'Used (\d+)%',screen[disk_row])
        expected='72c9a0' if int(used[1]) < 80 else 'e5ba73' if int(used[1]) < 90 else 'ed7f84'
        assert term.screen.buffer[disk_row][used.start()].fg == expected
        suffix=screen[disk_row][used.end():].split('│')[0]
        amount=re.search(r'\d+(?:\.\d+)? (?:[KMGTPE]iB|Byte)',suffix)
        assert amount and term.screen.buffer[disk_row][used.end()+amount.start()].fg == '81a8f8'
        (root/'test-screen-theme-full.txt').write_text(term.text())
        print('All panel borders, table headers and disk/network/PCIe colour roles passed', flush=True)
    finally:term.close()

    # An older custom theme without Nova extension keys inherits its own
    # colours. Change it live through Options to catch stale palette caches.
    custom=tmp/'btop/themes'; custom.mkdir(exist_ok=True)
    legacy=re.sub(r'^theme\[(?:gpu_\w+|status_\w+)\]=.*\n?', '', theme, flags=re.M)
    legacy=legacy.replace('theme[cpu_start]="#5bc4d6"','theme[cpu_start]="#abcdef"')
    (custom/'Probe.theme').write_text(legacy)
    term=Terminal(config_with(**common,color_theme='"Probe"'),tmp,library)
    try:
        assert legends(term)['GPU'] == 'abcdef'
        term.key('o');term.key('\x1b[C');term.key('\x1b')
        assert legends(term)['GPU'] == '77ca9b', (legends(term),term.text())
        term.key('o');term.key('\x1b[C');term.key('\x1b[C');term.key('\x1b')
        assert legends(term)['GPU'] == 'abcdef', (legends(term),term.text())
        print('Legacy theme inheritance and live palette refresh passed', flush=True)
    finally:term.close()

    for values in ({'truecolor':'False'}, {'force_tty':'True'}, {'theme_background':'False'}):
        term=Terminal(config_with(**common,**values),tmp,library)
        try:
            colours=legends(term)
            assert len(set(colours.values())) == 4, colours
            if 'force_tty' in values:
                assert colours == dict(GPU='brightcyan',VRAM='brightblue',GCLK='brightmagenta',MCLK='brightgreen'), colours
            if 'theme_background' in values:
                row=next(i for i,line in enumerate(term.screen.display) if 'GCLK ' in line)
                assert term.screen.buffer[row][1].bg == 'default'
            term.resize(80,35);term.resize(200,100)
            assert legends(term) == colours
        finally:term.close()
    print('256-colour, real 16-colour TTY and transparent-background resize fallbacks passed', flush=True)
