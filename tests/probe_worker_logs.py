"""I05: explicit output through the real worker; never touches a live instance."""
import json
import locale
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

REPO = Path(__file__).resolve().parents[1]


def probe(shell):
    with tempfile.TemporaryDirectory(prefix='dsh log probe ') as temp:
        root = Path(temp).resolve()
        (root / 'venv/Scripts').mkdir(parents=True)
        shutil.copyfile(Path(sys.base_prefix) / 'python.exe', root / 'venv/Scripts/astrbot.exe')
        (root / 'deployment-config').mkdir()
        (root / 'deployment-config/runtime.json').write_text('{"OwnerPlatformId":"synthetic"}')
        (root / 'run').write_text('''import os,pathlib,sys,time
print('SYNTHETIC_STDOUT_FLUSH', flush=True)
sys.stderr.write('SYNTHETIC_STDERR_FLUSH\\n');sys.stderr.flush()
sys.stdout.write('SYNTHETIC_STDOUT_BUFFERED')
pathlib.Path('app-ready').write_text(str(os.getpid()))
time.sleep(3)
raise SystemExit(7)
''', encoding='utf-8')
        nonce = uuid.uuid4().hex
        env = {**os.environ, 'PYTHONHOME': sys.base_prefix,
               'PATH': sys.base_prefix + ';' + str(Path(os.environ['SystemRoot']) / 'System32')}
        args = [shell, '-NoProfile', '-NonInteractive', '-File', str(REPO / 'scripts/start-bot.ps1'),
                '-RuntimeRoot', str(root), '-InternalWorker', '-WorkerId', nonce]
        process = subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        live = {}
        try:
            deadline = time.monotonic() + 15
            while not (root / 'app-ready').exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(.05)
            prefix = root / 'logs/launcher' / ('Bot-' + nonce)
            out = Path(str(prefix) + '-stdout.log'); err = Path(str(prefix) + '-stderr.log')
            if (root / 'app-ready').exists():
                live = dict(stdout=out.read_text(), stderr=err.read_text())
            stdout, stderr = process.communicate(timeout=15)
            observation = root / '.launcher' / (nonce + '.json')
            state = json.loads(observation.read_text(encoding='utf-8-sig')) if observation.exists() else None
            final = dict(stdout=out.read_text() if out.exists() else None,
                         stderr=err.read_text() if err.exists() else None)
            expected = bool(live and 'SYNTHETIC_STDOUT_FLUSH' in live['stdout']
                and 'SYNTHETIC_STDOUT_BUFFERED' not in live['stdout']
                and 'SYNTHETIC_STDERR_FLUSH' in live['stderr']
                and 'SYNTHETIC_STDOUT_BUFFERED' in final['stdout']
                and process.returncode == 7 and state and state['phase'] == 'exited' and state['exit_code'] == 7)
            return dict(shell=Path(shell).name, exit_code=process.returncode, live=live, final=final,
                        worker_stdout=stdout.decode('utf-8', errors='replace').replace(str(root), '<TEMP>'),
                        worker_stderr=stderr.decode('utf-8' if Path(shell).name.lower() == 'pwsh.exe' else locale.getpreferredencoding(False), errors='replace').replace(str(root), '<TEMP>'),
                        phase=state['phase'] if state else None, observation_exit=state['exit_code'] if state else None,
                        output_route_buffering_exit_verified=expected, worker_exited=process.poll() is not None)
        finally:
            # Popen retains this exact child handle. Ending this worker closes
            # its owned Job, including the synthetic application.
            if process.poll() is None:
                process.terminate(); process.communicate(timeout=10)
            if root.parent != Path(tempfile.gettempdir()).resolve() or not root.name.startswith('dsh log probe '):
                raise AssertionError('Unexpected fixture cleanup target')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    shells = [str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'), shutil.which('pwsh.exe')]
    print(json.dumps([probe(s) for s in shells if s], ensure_ascii=False, indent=2))
