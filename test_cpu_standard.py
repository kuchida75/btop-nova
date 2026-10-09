"""Verify standard CPU rendering and migration from the retired grid preference."""
import pathlib, re, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / 'tests'))
from nova_terminal import Terminal, config_with, root

def standard(term):
    text = term.text()
    assert '¹cpu' in text and 'C0' in text, text
    assert 'Load AVG:' in text or 'LAV:' in text, text
    assert not re.search(r'\bCPU\d+\b', text), text
    assert 'logical processors' not in text and 'Shift+L' not in text, text

with tempfile.TemporaryDirectory(prefix='.nova-cpu-standard-', dir=root) as tmp:
    tmp = pathlib.Path(tmp)
    for symbol in ('braille', 'block', 'tty'):
        config = config_with(shown_boxes='"cpu"', gpu_always_visible='False',
                             graph_symbol_cpu=f'"{symbol}"', update_ms='500',
                             cpu_graph_upper='"user"', cpu_graph_lower='"system"',
                             cpu_single_graph='False', cpu_bottom='False')
        # Old profiles must not resurrect the removed display.
        config += '\ncpu_logical_graphs = True\n'
        term = Terminal(config, tmp, tmp, width=200, height=80)
        try:
            standard(term)
            term.key('L'); standard(term)
            term.resize(80, 24); standard(term)
            term.resize(200, 80); standard(term)
            term.key('h')
            assert 'shift + l' not in term.text().lower(), term.text()
            term.key('\x1b'); standard(term)
            term.key('o'); term.key('\t')
            assert 'cpu graph upper' in term.text().lower(), term.text()
            assert 'cpu logical graphs' not in term.text().lower(), term.text()
            term.key('\x1b'); standard(term)
            # Trigger a normal config save, retaining the original interval.
            term.key('+'); term.key('-')
        finally:
            term.close()
        saved = dict(re.findall(r'^(\w+)\s*=\s*(.*)$', term.conf.read_text(), re.M))
        assert 'cpu_logical_graphs' not in saved
        assert saved['cpu_graph_upper'] == '"user"' and saved['cpu_graph_lower'] == '"system"'
        assert saved['cpu_single_graph'] == 'False'
        print(f'{symbol}: standard CPU, inert retired shortcut, resize, help/options and legacy-profile migration passed', flush=True)
