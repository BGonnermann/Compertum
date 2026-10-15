"""Verify the prebuilt native payload and mark wheels for Windows x64."""
import hashlib
import json
from pathlib import Path
import re
from setuptools import setup
from setuptools.command.build_py import build_py
from wheel.bdist_wheel import bdist_wheel


class CheckedBuild(build_py):
    def run(self):
        root=Path(__file__).parent/'src/compertum'
        anchor=re.search(r"_MANIFEST_SHA256='([a-f0-9]{64})'",(root/'_native_storage.py').read_text())[1]
        raw=(root/'_native/storage_scan.json').read_bytes()
        assert hashlib.sha256(raw).hexdigest()==anchor,'native manifest identity'
        manifest=json.loads(raw)
        assert manifest['abi']==1 and manifest['platform']=='win_amd64'
        for name in ('storage_scan.c','storage_scan.dll'):
            assert hashlib.sha256((root/'_native'/name).read_bytes()).hexdigest()==manifest['files'][name],name
        super().run()


class WindowsWheel(bdist_wheel):
    def get_tag(self):return 'py3','none','win_amd64'


setup(cmdclass={'build_py':CheckedBuild,'bdist_wheel':WindowsWheel})
