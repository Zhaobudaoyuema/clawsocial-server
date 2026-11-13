"""Build the public zipapp from canonical sources and pinned v8 dependencies."""
import argparse
import hashlib
import io
from pathlib import Path
from urllib.request import urlopen
import zipfile

BASE_URL = 'https://ns.chat.360.cn/zhaomi-so/client-up/611c27931e8377a258cbbaaecc49348cbbec847c/remote-command-target-agent-macos-v8.pyz'
BASE_SHA256 = 'd50d32620e288e9d0a6437c7c83c541917c833eda90952da69e60dd3260b60fa'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--base-bundle', type=Path)
    args = parser.parse_args()
    if args.base_bundle:
        data = args.base_bundle.read_bytes()
    else:
        with urlopen(BASE_URL, timeout=60) as response:
            data = response.read()
    if hashlib.sha256(data).hexdigest() != BASE_SHA256:
        raise SystemExit('base bundle SHA-256 mismatch')
    source = Path(__file__).resolve().parent
    with zipfile.ZipFile(io.BytesIO(data)) as old, zipfile.ZipFile(args.output, 'w', zipfile.ZIP_DEFLATED) as new:
        for entry in old.infolist():
            if entry.filename != '__main__.py' and '__pycache__' not in entry.filename:
                new.writestr(entry, old.read(entry))
        for filename, target in [('remote_command_public_agent.py', '__main__.py'),
                                 ('remote_command_output.py', 'remote_command_output.py')]:
            new.writestr(target, (source / filename).read_bytes())
    print(hashlib.sha256(args.output.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
