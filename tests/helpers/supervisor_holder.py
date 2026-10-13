from pathlib import Path
import sys
from compertum.runtime.supervisor import Supervisor
from compertum.config import load_config
root=Path(sys.argv[1])
Supervisor(load_config(root/'config.toml',root),_partial_fixture=True).run(maximum_seconds=40)

