"""Explicit offline GCC build. Run inside the admitted bounded build job.

Build into a fresh scratch directory. Review the receipt before installing the
DLL/manifest into src/compertum/_native. No compilation occurs during import.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


FLAGS=['-std=c11','-O2','-Wall','-Wextra','-Werror','-shared','-static-libgcc',
       '-Wl,--no-insert-timestamp','-Wl,--dynamicbase','-Wl,--nxcompat']


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--compiler',type=Path,required=True)
    parser.add_argument('--compiler-sha256',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    compiler=args.compiler.resolve(strict=True);output=args.output.resolve()
    assert os.name=='nt' and output.is_relative_to(root/'.cache/test-runs')
    assert not output.exists() and len(args.compiler_sha256)==64
    digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest(compiler)==args.compiler_sha256
    output.mkdir()
    source=root/'src/compertum/_native/storage_scan.c'
    (output/source.name).write_bytes(source.read_bytes())
    command=[str(compiler),*FLAGS,'storage_scan.c','-o','storage_scan.dll']
    version=subprocess.run([str(compiler),'--version'],capture_output=True,check=True,timeout=10).stdout.decode('utf-8')
    result=subprocess.run(command,cwd=output,capture_output=True,timeout=60)
    (output/'compiler.stdout').write_bytes(result.stdout)
    (output/'compiler.stderr').write_bytes(result.stderr)
    assert result.returncode==0, result.stderr.decode('utf-8',errors='replace')
    manifest=dict(abi=1,platform='win_amd64',compiler_sha256=digest(compiler),
                  compiler_version=version,command=command,
                  files={name:digest(output/name) for name in ('storage_scan.c','storage_scan.dll')})
    (output/'storage_scan.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(manifest))


if __name__=='__main__':main()
