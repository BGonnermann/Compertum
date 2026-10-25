"""Restrictive decisions from measured storage; never enables brokerage."""
import time
from .storage import CAPS,GIB,SCAN_SECONDS,INVENTORY_MAX_AGE,TOTAL_CAP


def check_storage(observation,reservations,*,previous=None):
    reason=None
    if (not 0<=time.monotonic()-observation['completed_monotonic']<=INVENTORY_MAX_AGE
            or not 0<=observation['scan_seconds']<=SCAN_SECONDS):
        reason='STORAGE_STALE'
    elif observation['free_bytes']<50*GIB: reason='FREE_SPACE_FLOOR'
    elif observation['total_bytes']>TOTAL_CAP or any(observation['categories'][key]>cap for key,cap in CAPS.items()):
        reason='STORAGE_CAPACITY'
    elif previous is not None:
        if set(observation.get('reparse_paths',[]))-set(previous.get('reparse_paths',[])):
            reason='UNACCOUNTED_REPARSE'
        allowed={row['path'].replace('\\','/').split('.partial-',1)[0]:row['maximum'] for row in reservations if row.get('path')}
        used={}
        for path,item in observation['files'].items():
            old=previous['files'].get(path,{'size':0,'charged':0})
            base=path.split('.partial-',1)[0].split('.incoming-',1)[0]
            if base in allowed:
                used[base]=used.get(base,0)+item['charged']
                # Metadata rename staging may coexist with its bounded old copy.
                allowance=((allowed[base]+4095)//4096)*4096
                if used[base]>allowance: reason='UNACCOUNTED_GROWTH';break
            elif item['size']>old['size'] or item['charged']>old['charged']:
                reason='UNACCOUNTED_GROWTH';break
    return {'status':'RESEARCH_BLOCKED' if reason else 'STORAGE_OBSERVED','reason':reason,
            'broker_capability':'CAPABILITY_UNAVAILABLE','measured_at':observation['completed_monotonic']}

