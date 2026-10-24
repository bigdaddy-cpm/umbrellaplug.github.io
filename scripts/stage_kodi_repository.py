"""Stage validated release ZIPs in the user's Kodi feed; never push or delete.

Existing ZIP URLs are immutable. Unrelated feed entries and older versions
are preserved. Metadata is read from the built ZIP, not a separate checkout.
"""
import argparse
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile


def stage(repository, archives):
    repository = repository.resolve(strict=True)
    remote = subprocess.check_output(['git', '-C', str(repository), 'remote', 'get-url', 'origin'], text=True).strip()
    assert remote.rstrip('/').removesuffix('.git') == 'https://github.com/bigdaddy-cpm/bigdaddy-cpm.github.io'
    original = (repository / 'addons.xml').read_text(encoding='utf-8')
    before = ET.fromstring(original)
    feed = original
    staged, changed = [], set()
    for source in archives:
        with zipfile.ZipFile(source) as archive:
            assert archive.testzip() is None
            names = archive.namelist()
            roots = {name.split('/')[0] for name in names}
            assert len(roots) == 1
            addon_id = roots.pop()
            assert addon_id in ('plugin.video.umbrella', 'skin.arctic.fuse.3.bigdaddy')
            assert addon_id not in changed
            assert all('..' not in name.split('/') and '\\' not in name for name in names)
            metadata = archive.read(addon_id + '/addon.xml')
            manifest = ET.fromstring(metadata)
            version = manifest.attrib['version']
            assert manifest.attrib['id'] == addon_id
            assert source.name == f'{addon_id}-{version}.zip'
            assets = {'addon.xml': metadata}
            for kind in ('icon', 'fanart'):
                name = manifest.findtext(f"extension[@point='xbmc.addon.metadata']/assets/{kind}")
                if name:
                    assert Path(name).name == name
                    assets[name] = archive.read(addon_id + '/' + name)
        output_dir = repository / 'zips' / addon_id
        output_zip = output_dir / source.name
        if output_zip.exists():
            assert output_zip.read_bytes() == source.read_bytes(), 'Release URL already contains different bytes'
        entry = re.sub(r'^<\?xml[^>]*\?>\s*', '', metadata.decode('utf-8')).strip()
        pattern = r'<addon\b[^>]*\bid="' + re.escape(addon_id) + r'"[^>]*>.*?</addon>'
        feed, count = re.subn(pattern, lambda match: entry, feed, flags=re.S)
        assert count == 1, 'Expected exactly one existing feed entry'
        changed.add(addon_id)
        staged.append((source, output_dir, assets))
    after = ET.fromstring(feed)
    assert len(after) == len(before)
    assert len(after) == len({node.attrib['id'] for node in after})
    for entry in before:
        addon_id = entry.attrib['id']
        if addon_id not in changed:
            assert ET.tostring(entry) == ET.tostring(after.find(f"addon[@id='{addon_id}']"))
    for source, output_dir, assets in staged:
        output_dir.mkdir(exist_ok=True)
        shutil.copyfile(source, output_dir / source.name)
        for name, data in assets.items():
            (output_dir / name).write_bytes(data)
    feed_bytes = feed.encode('utf-8')
    (repository / 'addons.xml').write_bytes(feed_bytes)
    digest = hashlib.md5(feed_bytes).hexdigest()
    (repository / 'addons.xml.md5').write_bytes((digest + '\n').encode('ascii'))
    print(f'Staged {len(staged)} packages; unrelated feed entries unchanged. MD5: {digest}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repository', type=Path)
    parser.add_argument('archives', type=Path, nargs='+')
    args = parser.parse_args()
    stage(args.repository, args.archives)
