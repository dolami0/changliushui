"""批量上传报告 JSON 到飞书多维表格"""
import json, subprocess, os, sys, time

os.chdir(os.path.dirname(os.path.abspath(__file__)))

BASE_TOKEN = 'ITMSbr109aIX3CsNWKQcYPHinod'
TABLE_ID = 'tbl3RlBIq4LBy1h8'
LARK_CLI = r'C:\Users\1\AppData\Roaming\npm\lark-cli.cmd'

success = 0
failed = []

files = sorted([f for f in os.listdir('.') if f.startswith('tmp_rec_') and f.endswith('.json')])

for i, fname in enumerate(files):
    # Read record to get display name
    with open(fname, encoding='utf-8') as f:
        rec = json.load(f)
    display = rec.get('json_filename', fname)

    # Call lark-cli directly
    proc = subprocess.run(
        [LARK_CLI, 'base', '+record-upsert',
         '--base-token', BASE_TOKEN,
         '--table-id', TABLE_ID,
         '--json', f'@{fname}'],
        capture_output=True, timeout=60
    )

    stdout_text = proc.stdout.decode('utf-8', errors='replace')
    try:
        result = json.loads(stdout_text)
        if result.get('ok'):
            success += 1
            print(f'[{i+1}/{len(files)}] OK  {display}')
        else:
            failed.append(display)
            err = result.get('error', {}).get('message', '')
            print(f'[{i+1}/{len(files)}] FAIL {display}: {err[:100]}')
    except Exception:
        failed.append(display)
        stderr_text = proc.stderr.decode('utf-8', errors='replace')
        print(f'[{i+1}/{len(files)}] FAIL {display}: {stderr_text[:100]}')

    if (i + 1) % 5 == 0:
        time.sleep(0.5)

print(f'\nDone: {success}/{len(files)} success, {len(failed)} failed')
if failed:
    print('Failed files:')
    for f in failed:
        print(f'  {f}')
