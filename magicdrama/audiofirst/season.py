import json
from pathlib import Path, PurePosixPath
import stat
import zipfile

from .core import digest, identifier, integer, write_json

MAX_FILES = 10000
MAX_BYTES = 5 * 1024 ** 3
MAX_MEMBER = 512 * 1024 ** 2


def safe_name(name):
    path = PurePosixPath(name)
    if not name or '\\' in name or '\x00' in name or path.is_absolute() or any(p in ('', '.', '..') for p in name.split('/')) or ':' in name:
        raise ValueError('Unsafe archive path')
    return path


def validate_manifest(manifest):
    if manifest.get('schema_version') != 1:
        raise ValueError('Unsupported season schema')
    identifier(manifest['series_id'], 'series id')
    integer(manifest['season'], 'season', 1, 999)
    if not isinstance(manifest.get('canon'), dict) or not all(k in manifest['canon'] for k in ('characters', 'facts', 'unresolved', 'ending')):
        raise ValueError('Canon must contain characters, facts, unresolved and ending')
    files = manifest.get('files')
    if not isinstance(files, list) or not files:
        raise ValueError('Season files are required')
    names = set()
    for item in files:
        name = str(safe_name(item['path']))
        if name == 'season.json' or name.casefold() in names:
            raise ValueError('Duplicate or reserved manifest path')
        names.add(name.casefold())
        integer(item['size'], 'file size', 0, MAX_MEMBER)
        if not isinstance(item.get('sha256'), str) or len(item['sha256']) != 64 or any(c not in '0123456789abcdef' for c in item['sha256']):
            raise ValueError('Invalid SHA-256')
    return manifest


def inspect_season_zip(path, max_files=MAX_FILES, max_bytes=MAX_BYTES, max_member=MAX_MEMBER):
    import hashlib
    with zipfile.ZipFile(path) as archive:
        entries = [i for i in archive.infolist() if not i.is_dir()]
        if len(entries) > max_files or sum(i.file_size for i in entries) > max_bytes:
            raise ValueError('Archive exceeds size or file-count limits')
        names = set()
        for item in archive.infolist():
            if item.is_dir():
                safe_name(item.filename.rstrip('/'))
                if stat.S_ISLNK(item.external_attr >> 16):
                    raise ValueError('Archive directory symlinks are not allowed')
                continue
            safe_name(item.filename)
            if item.filename.casefold() in names or item.file_size > max_member or item.flag_bits & 1:
                raise ValueError('Duplicate, encrypted or oversized archive entry')
            names.add(item.filename.casefold())
            if stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError('Archive symlinks are not allowed')
            if item.file_size > 1024 * 1024 and item.file_size / max(item.compress_size, 1) > 200:
                raise ValueError('Suspicious archive compression ratio')
        try:
            info = archive.getinfo('season.json')
        except KeyError:
            raise ValueError('Missing season.json: arbitrary video ZIPs need a reviewed import manifest')
        if info.file_size > 4 * 1024 * 1024:
            raise ValueError('Manifest too large')
        manifest = validate_manifest(json.loads(archive.read(info)))
        expected = {i['path']: i for i in manifest['files']}
        if set(i.filename for i in entries) != set(expected) | {'season.json'}:
            raise ValueError('Manifest must enumerate every asset and no extra files')
        for name, item in expected.items():
            info = archive.getinfo(name)
            if info.file_size != item['size']:
                raise ValueError('Asset size mismatch')
            h = hashlib.sha256()
            with archive.open(info) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    h.update(block)
            if h.hexdigest() != item['sha256']:
                raise ValueError('Asset hash mismatch')
        return manifest


def extract_season_zip(path, destination):
    manifest = inspect_season_zip(path)
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Extraction destination must not already exist')
    destination.mkdir(parents=True)
    try:
        with zipfile.ZipFile(path) as archive:
            for name in ['season.json'] + [i['path'] for i in manifest['files']]:
                target = destination.joinpath(*safe_name(name).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as source, target.open('xb') as output:
                    import shutil
                    shutil.copyfileobj(source, output)
    except Exception:
        import shutil
        shutil.rmtree(destination)
        raise
    return manifest


def pack_season(root, destination, series_id, season, canon):
    root = Path(root).resolve()
    destination = Path(destination).resolve()
    if root == destination or root in destination.parents:
        raise ValueError('Archive destination must be outside source directory')
    if destination.exists():
        raise ValueError('Archive destination already exists')
    files = []
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('Symlinks cannot be packaged')
        if not path.is_file():
            continue
        name = path.relative_to(root).as_posix()
        if name == 'season.json':
            continue
        if path.suffix.lower() in ('.pem', '.key', '.env') or path.name.startswith('.env'):
            raise ValueError('Potential credential file cannot be packaged')
        files.append({'path': name, 'size': path.stat().st_size, 'sha256': digest(path)})
    manifest = validate_manifest({'schema_version': 1, 'series_id': series_id,
                                  'season': season, 'canon': canon, 'files': files})
    temporary = destination.with_suffix(destination.suffix + '.tmp')
    try:
        with zipfile.ZipFile(temporary, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('season.json', json.dumps(manifest, ensure_ascii=False))
            for item in files:
                archive.write(root / item['path'], item['path'])
        inspect_season_zip(temporary)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return manifest
