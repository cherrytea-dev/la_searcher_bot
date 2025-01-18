import subprocess
from pathlib import Path


def main():
    defs = Path('src').glob('**/*.py')
    for file in defs:
        subprocess.run(['pyannotate', '-w', '--py3', str(file)])


if __name__ == '__main__':
    main()
