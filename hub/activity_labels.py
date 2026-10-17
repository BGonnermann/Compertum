"""Fixed public activity labels. Never return command bodies or transcript text."""
import re
import json
import shlex
from pathlib import PureWindowsPath


def worker_stage(command):
    try: args = [part.strip('\"\'') for part in shlex.split(command, posix=False)]
    except ValueError: return None
    if not args or PureWindowsPath(args[0]).name.lower() not in {'python','python.exe','py','py.exe'} or '-c' in args: return None
    try:
        index = args.index('-m'); module = args[index + 1]; mode = args[index + 2] if len(args)>index+2 else ''
    except (ValueError,IndexError): return None
    if module == 'compertum.runtime.campaign_worker':
        return 'final_evaluation' if mode=='final' else 'reports' if mode=='scorecard' else 'experiments'
    if module == 'compertum.runtime.audit_worker':
        return 'independent_audit' if mode=='final_audit' else 'development_audit'
    if module == 'compertum.runtime.replay_worker': return 'experiments'
    return None


def test_command(command):
    try:
        args = [part.strip('\"\'') for part in shlex.split(command, posix=False)]
    except ValueError:
        return False
    if args and args[0] == '&': args = args[1:]
    if not args: return False
    program = PureWindowsPath(args[0]).name.lower()
    if program in {'pytest', 'pytest.exe'}: return True
    if program in {'python', 'python.exe', 'py', 'py.exe'}:
        if '-c' in args: return False
        return any(args[index] == '-m' and args[index + 1] in {'pytest', 'unittest'} for index in range(len(args) - 1))
    if program in {'node', 'node.exe'}:
        return any(PureWindowsPath(arg).name == 'check_browser.cjs' for arg in args[1:3])
    return False


def activity_label(tool='', text=''):
    if tool in {'apply_patch', 'FileChange'} or 'tools.apply_patch(' in text:
        return 'Editing files'
    commands = []
    for match in re.finditer(r'\bcmd\s*:\s*("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')', text):
        raw = match[1]
        try: commands.append(json.loads(raw) if raw.startswith('"') else raw[1:-1].replace("\\'", "'"))
        except ValueError: pass
    if any(test_command(command) for command in commands or [text]):
        return 'Running test tools'
    if tool in {'wait', 'wait_agent', 'wait_threads', 'sleep', 'write_stdin'}:
        return 'Waiting for a tool'
    if tool in {'spawn_agent', 'followup_task', 'send_message'}:
        return 'Coordinating agent work'
    return 'Using tools'
