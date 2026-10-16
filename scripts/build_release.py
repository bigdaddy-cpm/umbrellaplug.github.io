"""Build the Omega release from tracked source; do not patch release ZIPs.

Run: python scripts/build_release.py
Then publish the ZIP and its manifest to bigdaddy-cpm.github.io as well.
"""
import ast
import hashlib
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'omega' / 'plugin.video.umbrella'
RELEASES = ROOT / 'omega' / 'zips'


def build():
    manifest = (SOURCE / 'addon.xml').read_text(encoding='utf-8').strip() + '\n'
    addon = ET.fromstring(manifest)
    version = addon.attrib['version']
    assert addon.attrib['id'] == 'plugin.video.umbrella'
    assert re.fullmatch(r'\d+\.\d+\.\d+', version)
    files = sorted(path for path in SOURCE.rglob('*') if path.is_file()
                   and '__pycache__' not in path.parts and path.suffix != '.pyc')
    for path in files:
        if path.suffix == '.py':
            text = path.read_text(encoding='utf-8-sig')
            ast.parse(text, filename=str(path), feature_version=(3, 8))
            compile(text, str(path), 'exec')
        if path.name in ('addon.xml', 'settings.xml'):
            ET.parse(path)
        if path.suffix in ('.py', '.xml', '.po', '.txt'):
            assert not re.search(r'(?m)^(<<<<<<< |=======\s*$|>>>>>>> )',
                                 path.read_text(encoding='utf-8-sig')), path
    package_dir = RELEASES / 'plugin.video.umbrella'
    package = package_dir / ('plugin.video.umbrella-%s.zip' % version)
    # Stable paths, timestamps, permissions and text line endings.
    with zipfile.ZipFile(package, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            name = 'plugin.video.umbrella/' + path.relative_to(SOURCE).as_posix()
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            data = path.read_bytes()
            if path.suffix in ('.py', '.xml', '.po', '.txt'):
                data = data.replace(b'\r\n', b'\n')
            archive.writestr(info, data)
    with zipfile.ZipFile(package) as archive:
        assert archive.testzip() is None
        assert ET.fromstring(archive.read('plugin.video.umbrella/addon.xml')).attrib == addon.attrib
    (package_dir / 'addon.xml').write_bytes(manifest.encode('utf-8'))
    feed_path = RELEASES / 'addons.xml'
    feed = feed_path.read_text(encoding='utf-8')
    other_addons = [ET.tostring(node) for node in ET.fromstring(feed)
                    if node.attrib.get('id') != 'plugin.video.umbrella']
    feed, count = re.subn(r'<addon\b[^>]*\bid="plugin\.video\.umbrella"[\s\S]*?</addon>',
                         lambda match: manifest.rstrip(), feed)
    assert count == 1
    updated = ET.fromstring(feed)
    assert [ET.tostring(node) for node in updated
            if node.attrib.get('id') != 'plugin.video.umbrella'] == other_addons
    feed_bytes = feed.encode('utf-8')
    feed_path.write_bytes(feed_bytes)
    (RELEASES / 'addons.xml.md5').write_bytes(hashlib.md5(feed_bytes).hexdigest().encode('ascii'))
    print('Built %s (%d source files)' % (package, len(files)))
    print('SHA256: ' + hashlib.sha256(package.read_bytes()).hexdigest())


if __name__ == '__main__':
    build()
