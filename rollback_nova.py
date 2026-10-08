"""Remove only the Nova command and its Bash alias; keep releases and configuration."""
import argparse, pathlib, re
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--prefix',type=pathlib.Path,default=pathlib.Path.home()/'.local')
parser.add_argument('--bashrc',type=pathlib.Path,default=pathlib.Path.home()/'.bashrc')
args=parser.parse_args()
command=args.prefix/'bin/btop'
if command.exists() and not command.is_symlink() and '# Nova btop user command' in command.read_text(errors='replace'):
    command.unlink()
if args.bashrc.exists():
    text=args.bashrc.read_text();updated=re.sub(r'# BEGIN NOVA BTOP.*?# END NOVA BTOP\n?', '',text,flags=re.S)
    if updated!=text:args.bashrc.write_text(updated)
print('Nova default removed. Open a new Bash terminal, or run unalias btop; hash -r.')
