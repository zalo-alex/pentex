import json
import os
import shutil
import zipfile
from types import SimpleNamespace
from flask import current_app

_ORDER_FILENAME = '.order.json'
_ZIP_MAX_FILES = 200
_ZIP_DEFAULT_MAX_SIZE = 20 * 1024 * 1024


def _root_dir():
    return os.path.join(current_app.instance_path, 'template_pages')


def _is_safe_filename(filename):
    # Page filenames are a flat set (no subdirectories); reject anything that
    # could escape the template's directory once used to build a disk path.
    if not filename or '/' in filename or '\\' in filename or '\x00' in filename:
        return False
    return filename not in ('.', '..', _ORDER_FILENAME)


def _current_dir(template_public_id):
    return os.path.join(_root_dir(), template_public_id, 'current')


def _version_dir(template_public_id, version_number):
    return os.path.join(_root_dir(), template_public_id, 'versions', str(version_number))


def _baseline_dir(template_public_id):
    return os.path.join(_root_dir(), template_public_id, 'baseline')


def _read_order(directory):
    path = os.path.join(directory, _ORDER_FILENAME)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
        return []
    return data


def _list_files(directory):
    if not os.path.isdir(directory):
        return []
    on_disk = sorted(
        f for f in os.listdir(directory)
        if f != _ORDER_FILENAME and os.path.isfile(os.path.join(directory, f))
    )
    order = _read_order(directory)
    on_disk_set = set(on_disk)
    ordered = [f for f in order if f in on_disk_set]
    ordered.extend(f for f in on_disk if f not in ordered)
    return ordered


def write_page_order(template_public_id, filenames):
    directory = _current_dir(template_public_id)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, _ORDER_FILENAME)
    tmp_path = path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(list(filenames), f)
    os.replace(tmp_path, path)


def read_page_order(template_public_id):
    return _read_order(_current_dir(template_public_id))


def _read_file(directory, filename):
    if not _is_safe_filename(filename):
        return None
    path = os.path.join(directory, filename)
    if not os.path.isfile(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def list_pages(template_public_id):
    return _list_files(_current_dir(template_public_id))


def read_page(template_public_id, filename):
    return _read_file(_current_dir(template_public_id), filename)


def write_page(template_public_id, filename, content):
    if not _is_safe_filename(filename):
        raise ValueError(f'Unsafe filename: {filename!r}')
    directory = _current_dir(template_public_id)
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, filename), 'w', encoding='utf-8') as f:
        f.write(content or '')


def template_pages(template_public_id):
    directory = _current_dir(template_public_id)
    return [SimpleNamespace(filename=fn, content=_read_file(directory, fn))
            for fn in _list_files(directory)]


def list_version_pages(template_public_id, version_number):
    return _list_files(_version_dir(template_public_id, version_number))


def read_version_page(template_public_id, version_number, filename):
    return _read_file(_version_dir(template_public_id, version_number), filename)


def read_baseline_page(template_public_id, filename):
    return _read_file(_baseline_dir(template_public_id), filename)


def write_baseline_page(template_public_id, filename, content):
    if not _is_safe_filename(filename):
        raise ValueError(f'Unsafe filename: {filename!r}')
    directory = _baseline_dir(template_public_id)
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, filename), 'w', encoding='utf-8') as f:
        f.write(content or '')


def version_pages(template_public_id, version_number):
    directory = _version_dir(template_public_id, version_number)
    return [SimpleNamespace(filename=fn, content=_read_file(directory, fn))
            for fn in _list_files(directory)]


def snapshot_version(template_public_id, version_number):
    source_dir = _current_dir(template_public_id)
    dest_dir = _version_dir(template_public_id, version_number)
    os.makedirs(os.path.dirname(dest_dir), exist_ok=True)
    if os.path.isdir(source_dir):
        shutil.copytree(source_dir, dest_dir)
    else:
        os.makedirs(dest_dir, exist_ok=True)


def clone_template(source_public_id, dest_public_id):
    source_dir = _current_dir(source_public_id)
    dest_dir = _current_dir(dest_public_id)
    os.makedirs(os.path.dirname(dest_dir), exist_ok=True)
    if os.path.isdir(source_dir):
        shutil.copytree(source_dir, dest_dir)
    else:
        os.makedirs(dest_dir, exist_ok=True)


def delete_template(template_public_id):
    directory = os.path.join(_root_dir(), template_public_id)
    if os.path.isdir(directory):
        shutil.rmtree(directory)


def _human_size(n):
    size = float(n)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size < 1024 or unit == 'GB':
            return f'{size:.0f} {unit}' if unit == 'B' else f'{size:.1f} {unit}'
        size /= 1024


def _common_leading_dir(names):
    # If every entry in the zip shares the same top-level folder (e.g. it was zipped as
    # "mytemplate/headers.hbs" rather than "headers.hbs"), strip that wrapper so a flat set of
    # pages comes out either way. Any entry sitting at the zip root means there's no wrapper.
    prefixes = set()
    for name in names:
        if '/' not in name:
            return ''
        prefixes.add(name.split('/', 1)[0])
    if len(prefixes) == 1:
        return prefixes.pop() + '/'
    return ''


def parse_template_zip(file_obj):
    """Parses an uploaded .zip into a flat {filename: content} dict of .hbs/.css pages.
    Raises ValueError with a user-facing message on any problem, so callers can just
    flash(str(e)) without translating the failure themselves."""
    try:
        zf = zipfile.ZipFile(file_obj)
    except zipfile.BadZipFile:
        raise ValueError('That file is not a valid .zip archive.')

    infos = [i for i in zf.infolist() if not i.is_dir() and not i.filename.endswith('/')]
    if not infos:
        raise ValueError('The zip archive is empty.')
    if len(infos) > _ZIP_MAX_FILES:
        raise ValueError(f'The zip archive has too many files (max {_ZIP_MAX_FILES}).')

    max_size = _ZIP_DEFAULT_MAX_SIZE
    try:
        max_size = current_app.config.get('TEMPLATE_ZIP_MAX_UPLOAD_SIZE', _ZIP_DEFAULT_MAX_SIZE)
    except RuntimeError:
        pass  # no app context (e.g. a script calling this directly) - fall back to the default
    total_size = sum(i.file_size for i in infos)
    if total_size > max_size:
        raise ValueError(f'The zip archive is too large (max {_human_size(max_size)}).')

    common_prefix = _common_leading_dir([i.filename for i in infos])

    pages = {}
    for info in infos:
        rel = info.filename[len(common_prefix):] if common_prefix else info.filename
        if not rel or not (rel.endswith('.hbs') or rel.endswith('.css')):
            continue  # skip non-page files (README, images, __MACOSX/, etc.)
        if not _is_safe_filename(rel):
            raise ValueError(f'Unsafe or nested filename in zip: {rel!r}. Pages must be flat '
                             '(no subfolders), directly at the zip root or inside a single wrapping folder.')
        try:
            content = zf.read(info).decode('utf-8')
        except UnicodeDecodeError:
            raise ValueError(f'{rel} is not valid UTF-8 text.')
        pages[rel] = content

    if not pages:
        raise ValueError('No .hbs or .css template pages found in the zip.')
    return pages


def replace_pages(template_public_id, pages):
    """Wipes the template's current pages and writes the given {filename: content} dict in
    their place. Callers are responsible for snapshotting a version first if the previous
    content should stay recoverable."""
    directory = _current_dir(template_public_id)
    if os.path.isdir(directory):
        shutil.rmtree(directory)
    os.makedirs(directory, exist_ok=True)
    for filename, content in pages.items():
        with open(os.path.join(directory, filename), 'w', encoding='utf-8') as f:
            f.write(content)
