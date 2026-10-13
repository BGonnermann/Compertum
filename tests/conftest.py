"""Explicit persistent native fixture root for restart verification only."""
def pytest_addoption(parser):
    parser.addoption('--m0-recovery-project',default=None,help='Current-run native recovery fixture project; preserves all prior generations and receipts')
    parser.addoption('--m0-managed-project',default=None,help='Current-run separate-owner native fixture project')
