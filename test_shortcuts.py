"""Verify shortcut discovery and every reference entry in real terminals."""
import pathlib, re, sys, tempfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'tests'))
from nova_terminal import Terminal,config_with,root

source=(root/'src/btop_menu.cpp').read_text().split('help_text = {',1)[1].split('const vector<vector<vector<string>>> categories',1)[0]
entries=re.findall(r'\{"([^"\n]*)", "([^"\n]*)"\}',source)
assert len(entries)>60
assert all(len(key)<=20 and len(description)<=56 for key,description in entries)
assert any(key=='Shift+F' for key,_ in entries)

def page(term):
    match=re.search(r'page (\d+)/(\d+)',term.text())
    assert match,term.text()
    return tuple(map(int,match.groups()))

def click(term,label):
    y=next(i for i,line in enumerate(term.screen.display) if label in line)
    x=term.screen.display[y].index(label)
    term.key(f'\x1b[<0;{x+1};{y+1}M')

with tempfile.TemporaryDirectory(prefix='.nova-shortcuts-',dir=root) as folder:
    tmp=pathlib.Path(folder)
    config=config_with(shown_boxes='"cpu"',show_gpu_info='"Off"',gpu_always_visible='False',show_core_freq='True')
    term=Terminal(config,tmp,tmp,width=146,height=60)
    try:
        assert 'keys' in term.text()
        click(term,'keys');assert 'keyboard shortcuts' in term.text()
        term.key('\x1b');assert 'keyboard shortcuts' not in term.text()
        for code in ('\x1bOP','\x1b[11~','?'):
            term.key(code);assert 'keyboard shortcuts' in term.text(),(repr(code),term.text())
            term.key(code);assert 'keyboard shortcuts' not in term.text()
        for code in ('\x1bOQ','\x1b[12~'):
            term.key(code);assert 'Color theme' in term.text()
            term.key('\x1b')
        term.key('m');assert 'Keyboard shortcuts' in term.text()
        term.key('\x1b[B');term.key('\n');assert 'keyboard shortcuts' in term.text()
        term.key('\x1b');term.key('\x1b')
        for width,height in ((80,24),(100,35),(146,60),(200,100)):
            term.resize(width,height);term.key('?')
            first,total=page(term);assert first==1
            screens=[]
            for number in range(1,total+1):
                assert page(term)[0]==number
                screens.append(term.text());term.key('\x1b[6~')
            assert page(term)[0]==1 # All pages are reachable and wrap.
            text='\n'.join(screens)
            for key,description in entries:assert description in text,(width,height,key,description,text)
            term.key('\x1b[F');assert page(term)[0]==total
            term.key('\x1b[H');assert page(term)[0]==1
            if total>1:
                click(term,'Next >');assert page(term)[0]==2
                click(term,'< Prev');assert page(term)[0]==1
                term.key('\x1b[D');assert page(term)[0]==total
                term.key('\x1b[C');assert page(term)[0]==1
            (root/f'test-screen-shortcuts-{width}x{height}.txt').write_text(term.text())
            term.key('\x1b');assert 'keyboard shortcuts' not in term.text()
            assert 'C0' in term.text()
            print(f'{width}x{height}: all {len(entries)} reference entries reachable across {total} page(s); navigation, clickable paging and return to CPU passed',flush=True)
    finally:term.close()
    term=Terminal(config_with(shown_boxes='"cpu"',gpu_always_visible='False',vim_keys='True'),tmp,tmp,width=146,height=60)
    try:
        term.key('H');assert 'keyboard shortcuts' in term.text()
        term.key('H');assert 'keyboard shortcuts' not in term.text()
    finally:term.close()
    print('Visible keys button, main-menu discovery, both F1/F2 terminal encodings, question-mark toggle and Vim help passed',flush=True)
