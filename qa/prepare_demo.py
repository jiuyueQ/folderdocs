"""Prepare a synthetic demo and browser account; credentials stay in ignored qa-output/."""
import io
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'folderdocs.settings')
import django
django.setup()
from django.core.management import call_command

output = ROOT / 'qa-output'
output.mkdir(exist_ok=True)
account_file = Path(os.environ.get('FOLDERDOCS_TEST_ACCOUNT', output / 'account.json'))
account_file.parent.mkdir(parents=True, exist_ok=True)
if not account_file.exists():
    stream = io.StringIO()
    call_command('seed_demo', username='demo', stdout=stream)
    lines = stream.getvalue().splitlines()
    password = next(line.split(': ', 1)[1] for line in lines if line.startswith('Demo password: '))
    account_file.write_text(json.dumps({'username': 'demo', 'password': password}), encoding='utf-8')
call_command('worker', drain=True)
print('Synthetic demo ready; browser credentials saved in the selected QA account file.')
