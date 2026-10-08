from dataclasses import dataclass
from pathlib import Path
import hashlib
import os
import re
from .errors import RuntimeRefused
from ._windows import WindowsAPI


@dataclass(frozen=True)
class PeerObservation:
    pid: int
    creation_filetime: int
    operator_sid: str
    logon_sid: str


@dataclass(frozen=True)
class ProjectIdentity:
    root_path: Path
    project_id: str
    volume_serial: int
    root_file_id: str
    operator_sid: str
    logon_sid: str


def resolve_project(root: Path) -> ProjectIdentity:
    api = WindowsAPI()  # Refuse unsupported platforms before any filesystem work.
    root = Path(root)
    if not root.is_absolute(): raise RuntimeRefused("ABSOLUTE_ROOT_REQUIRED")
    drive = root.drive
    if not re.fullmatch(r"(?:\\\\\?\\)?[A-Za-z]:", drive) or api.GetDriveTypeW(drive[-2:] + "\\") != 3:
        raise RuntimeRefused("LOCAL_FIXED_VOLUME_REQUIRED")
    with api.open_directory(root, follow_root=True) as h:
        volume, file_id = api.file_identity(h)
        canonical = api.final_path(h)
        with api.open_process(os.getpid()) as process:
            sid, logon = api.token_sids(process)
        identity = hashlib.sha256(b"compertum-project-v1\0" + volume.to_bytes(8, "little") + bytes.fromhex(file_id)).hexdigest()
        return ProjectIdentity(canonical, identity, volume, file_id, sid, logon)
