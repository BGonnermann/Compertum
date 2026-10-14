"""Opaque publication must fit the unchanged coordinator without research dependencies."""
import os,subprocess,sys


def test_market_publication_import_keeps_calendar_and_numeric_runtime_unloaded():
 code="""
import importlib.abc,sys
class Boundary(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname.split('.')[0] in {'numpy','scipy','pandas','sklearn','exchange_calendars'}:raise AssertionError('COORDINATOR_HEAVY_IMPORT:'+fullname)
sys.meta_path.insert(0,Boundary())
from compertum.runtime.paper_market_publication import PaperMarketPublication
assert not any(name in sys.modules for name in ('numpy','scipy','pandas','sklearn','exchange_calendars'))
print('OPAQUE_PUBLICATION_LIGHTWEIGHT')
"""
 env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PYTHONPATH','TEMP','TMP','PYTHONDONTWRITEBYTECODE','PYTHONNOUSERSITE'}}
 result=subprocess.run([sys.executable,'-B','-c',code],env=env,capture_output=True,text=True,timeout=15,creationflags=0x08000000)
 assert result.returncode==0,result.stderr
 assert result.stdout.strip()=='OPAQUE_PUBLICATION_LIGHTWEIGHT'
