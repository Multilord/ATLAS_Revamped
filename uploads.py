"""File parsing in a separate process with a deadline and optional scanner gate."""
import json
import base64
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import security

_slots = threading.BoundedSemaphore(2)


def scan(data):
    scanner = os.getenv('ATLAS_CLAMSCAN_PATH', '')
    if not scanner:
        if os.getenv('ATLAS_REQUIRE_MALWARE_SCAN') == '1':
            raise security.SecurityError('Uploads are blocked until malware scanning is configured.', 503)
        return 'Not performed; independent review required'
    executable = Path(scanner)
    if not executable.is_absolute() or not executable.is_file():
        raise security.SecurityError('Malware scanner configuration is invalid.', 503)
    raw = base64.b64decode(data.get('file_base64', ''), validate=True)
    if not 0 < len(raw) <= 5 * 1024 * 1024:
        raise ValueError('Upload a non-empty file of at most 5 MB.')
    with tempfile.TemporaryDirectory(prefix='atlas-scan-') as folder:
        path = Path(folder) / 'upload.bin'
        path.write_bytes(raw)
        try:
            result = subprocess.run([str(executable), '--no-summary', str(path)], capture_output=True,
                timeout=30, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except subprocess.TimeoutExpired:
            raise security.SecurityError('Malware scan timed out. Upload blocked.', 422) from None
        if result.returncode:
            raise security.SecurityError('Malware scan rejected the upload or could not complete.', 422)
    return 'Scanner completed without a detection'


def parse(data, mode='document'):
    if not _slots.acquire(blocking=False):
        raise security.SecurityError('Document processors are busy. Retry shortly.', 429)
    try:
        return _parse(data, mode)
    finally:
        _slots.release()


def _parse(data, mode):
    scan_status = scan(data)
    # Credential configuration must not be inherited by the parser worker.
    env = {k: v for k, v in os.environ.items() if k.upper() in ('SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP')}
    env['PYTHONIOENCODING'] = 'utf-8'
    env['ATLAS_PARSER_WORKER'] = '1'
    try:
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('upload_worker.py'))],
            input=json.dumps({'data': data, 'mode': mode}), text=True, encoding='utf-8',
            capture_output=True, timeout=20, env=env,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired:
        raise security.SecurityError('File parsing exceeded 20 seconds. Split or simplify the document.', 422) from None
    if result.returncode or len(result.stdout) > 2 * 1024 * 1024:
        raise ValueError('File parsing failed or exceeded output limits.')
    response = json.loads(result.stdout)
    if 'error' in response:
        raise ValueError(response['error'])
    payload = response['result']
    payload['security_findings'] = security.screen(json.dumps(payload, ensure_ascii=False))
    payload['malware_scan'] = scan_status
    return payload
