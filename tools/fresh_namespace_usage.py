"""Count capped folders once per sample with fresh metadata for each path.

This maintenance helper does not replace product storage admission.
"""
import os
import stat


def namespace_usage(roots, poll, *, stat_path=os.stat, scan_directory=os.scandir):
    """Return the original rounded logical charge for every supplied root.

    Overlapping roots share observations within this call only. Reparse points
    cost 4096 bytes and are not followed. Missing paths keep the old zero charge.
    Other errors refuse the sample. ``poll`` must enforce the caller's limits.
    """
    names = [os.path.abspath(os.fspath(root)) for root in roots]
    indexes = {}
    actual_roots = {}
    for index, name in enumerate(names):
        key = os.path.normcase(name)
        if key in actual_roots and actual_roots[key] != name:
            raise ValueError('AMBIGUOUS_CAPPED_ROOT_SPELLING')
        indexes.setdefault(key, []).append(index)
        actual_roots.setdefault(key, name)
    amounts = [0] * len(names)
    observed_roots = set()
    # Parents run first. A nested root behind a reparse point still gets its
    # separate original check because that path was not visited through its parent.
    for root in sorted(indexes, key=lambda name: (len(name), name)):
        if root in observed_roots:
            continue
        pending = [(actual_roots[root], ())]
        while pending:
            poll()
            path, active = pending.pop()
            try:
                info = stat_path(path, follow_symlinks=False)
            except FileNotFoundError:
                continue
            poll()
            key = os.path.normcase(path)
            if key in indexes:
                active = active + tuple(indexes[key])
                observed_roots.add(key)
            reparse = bool(getattr(info, 'st_file_attributes', 0) & 0x400)
            directory = stat.S_ISDIR(info.st_mode)
            charge = 4096 if reparse or directory else ((info.st_size + 4095) // 4096) * 4096
            for index in active:
                amounts[index] += charge
            if directory and not reparse:
                try:
                    with scan_directory(path) as entries:
                        for entry in entries:
                            poll()
                            # Do not use DirEntry.stat(). Windows can cache its
                            # enumeration data before a later write or deletion.
                            # scandir receives an absolute path, so entry.path
                            # is already absolute. Keep the actual name spelling.
                            pending.append((entry.path, active))
                except FileNotFoundError:
                    pass
    poll()
    return amounts
