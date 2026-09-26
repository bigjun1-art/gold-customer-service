#!/usr/bin/env python3
"""Version-checked Markdown writes for a local skill knowledge directory (POSIX)."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else 'missing'


def target_path(root, relative):
    relative = Path(relative)
    if relative.is_absolute() or '..' in relative.parts or any(p.startswith('.') for p in relative.parts):
        raise ValueError('Use a non-hidden relative Markdown path without parent traversal')
    if relative.suffix != '.md':
        raise ValueError('Only Markdown knowledge files are supported')
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('Symlinks are not supported')
    current.resolve().relative_to(root.resolve())
    return current


def read_note(root, relative):
    path = target_path(root, relative)
    data = path.read_bytes() if path.exists() else None
    return {'path': relative, 'sha256': digest(data), 'content': data.decode('utf-8') if data is not None else None}


def atomic_replace(path, data, mode=0o600):
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix='.pending-')
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_note(root, relative, content, expected):
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError('Knowledge root must already exist')
    target_path(root, relative)
    lock = root / '.write.lock'
    if lock.is_symlink():
        raise ValueError('Symlink lock is not supported')
    descriptor = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'r+') as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another knowledge update is active; read again after it completes')
        path = target_path(root, relative)
        old = path.read_bytes() if path.exists() else None
        if digest(old) != expected:
            raise ValueError('Knowledge changed since read; re-read and reconcile before writing')
        new = content.encode('utf-8')
        if old == new:
            return {'path': relative, 'sha256': digest(old), 'changed': False, 'backup': None}
        backup = None
        if old is not None:
            history = root / '.history'
            if history.is_symlink():
                raise ValueError('Symlink history is not supported')
            history.mkdir(mode=0o700, exist_ok=True)
            backup = history / (uuid.uuid4().hex + '.json')
            descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                json.dump({'path': relative, 'sha256': digest(old), 'content': old.decode('utf-8')}, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
        atomic_replace(path, new, mode)
        actual = path.read_bytes()
        if actual != new:
            raise ValueError('Readback differs from submitted content; inspect state before retrying')
        return {'path': relative, 'sha256': digest(actual), 'changed': True, 'backup': str(backup) if backup else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1] / 'knowledge')
    sub = parser.add_subparsers(dest='action', required=True)
    read = sub.add_parser('read'); read.add_argument('path')
    write = sub.add_parser('write'); write.add_argument('path')
    write.add_argument('--content', type=Path, required=True)
    write.add_argument('--expected', required=True, help='SHA-256 from read, or missing for a new file')
    args = parser.parse_args()
    try:
        if args.action == 'read':
            result = read_note(args.root, args.path)
        else:
            result = write_note(args.root, args.path, args.content.read_text(encoding='utf-8'), args.expected)
        print(json.dumps(result, ensure_ascii=False))
    except (ValueError, OSError, UnicodeError) as exc:
        parser.exit(1, f'{exc}\n')


if __name__ == '__main__':
    main()
