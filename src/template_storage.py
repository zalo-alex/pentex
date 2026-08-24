import json
import os
import shutil
from types import SimpleNamespace
from flask import current_app

_ORDER_FILENAME = '.order.json'


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
