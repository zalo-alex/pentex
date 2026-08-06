import os
import shutil
from flask import current_app


def _root_dir():
    return os.path.join(current_app.instance_path, 'assets')


def _is_safe_filename(filename):
    if not filename or '/' in filename or '\\' in filename or '\x00' in filename:
        return False
    return filename not in ('.', '..')


def _asset_dir(asset_public_id):
    return os.path.join(_root_dir(), asset_public_id)


def save_asset(asset_public_id, filename, file_storage):
    """Persist an uploaded werkzeug FileStorage to disk. Returns size in bytes."""
    if not _is_safe_filename(filename):
        raise ValueError(f'Unsafe filename: {filename!r}')
    directory = _asset_dir(asset_public_id)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, filename)
    file_storage.save(path)
    return os.path.getsize(path)


def asset_file(asset_public_id, filename):
    """Return (directory, filename) for send_from_directory, or None if missing/unsafe."""
    if not _is_safe_filename(filename):
        return None
    directory = _asset_dir(asset_public_id)
    if not os.path.isfile(os.path.join(directory, filename)):
        return None
    return directory, filename


def delete_asset(asset_public_id):
    directory = _asset_dir(asset_public_id)
    if os.path.isdir(directory):
        shutil.rmtree(directory)
