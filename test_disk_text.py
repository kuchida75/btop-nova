"""Verify scoped disk text colours remain readable with Default/Nova themes."""
import pathlib,re,subprocess,sys,tempfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'tests'))
from nova_terminal import Terminal,config_with,root

def contrast(fg,bg):
    def light(c):
        values=[int(c[i:i+2],16)/255 for i in (0,2,4)]
        values=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values]
        return sum(a*b for a,b in zip(values,(.2126,.7152,.0722)))
    a,b=sorted((light(fg),light(bg)));return (b+.05)/(a+.05)

with tempfile.TemporaryDirectory(prefix='.nova-disk-text-',dir=root) as folder:
    tmp=pathlib.Path(folder);library=tmp/'nvml';library.mkdir()
    subprocess.run(['gcc','-shared','-fPIC','-Wall','-Wextra','-Werror',str(root/'tests/nova_nvml_fixture.c'),'-o',str(library/'libnvidia-ml.so')],check=True)
    common=dict(shown_boxes='"cpu mem net proc gpu0"',show_core_freq='True',nova_layout='True',io_mode='False',update_ms='500')
    for theme,expected in [('Default',('b0a9de','dcafde','e5a0a8')),('Nova',('5bc4d6','81a8f8','81a8f8'))]:
        term=Terminal(config_with(**common,color_theme='"'+theme+'"'),tmp,library,width=146,height=87)
        try:
            screen=term.screen.display;mem=next(y for y,line in enumerate(screen) if '²mem' in line);net=next(y for y,line in enumerate(screen) if '³net' in line)
            left=screen[mem].index('disks')-2
            found=[]
            for label in ('R ','W '):
                y=next(y for y in range(mem,net) if re.search(r'\b'+label+r'(?:\d|--)',screen[y][left:]));x=screen[y].index(label,left)
                found.append(term.screen.buffer[y][x].fg)
            y=next(y for y in range(mem,net) if re.search(r'Used \d+%',screen[y][left:]));match=re.search(r'Used \d+%\s+(\d+(?:\.\d+)? [KMGTPE]iB)',screen[y][left:]);assert match,screen[y]
            found.append(term.screen.buffer[y][left+match.start(1)].fg)
            assert tuple(found)==expected,(theme,found)
            # This dark teal sample represents a transparent terminal background.
            assert all(contrast(color,'14333a')>=4.5 for color in found),(theme,found)
            # Other panel colours keep the chosen theme's existing roles.
            y=next(y for y,line in enumerate(screen) if 'GCLK ' in line)
            gpu=term.screen.buffer[y-1][screen[y-1].index('GPU ')].fg
            assert gpu==('77ca9b' if theme=='Default' else '5bc4d6'),gpu
            (root/('test-screen-disk-text-'+theme.lower()+'.txt')).write_text(term.text())
        finally:term.close()
print('Default/Nova disk R/W text and used bytes, dark-background contrast and unchanged GPU palette passed',flush=True)
