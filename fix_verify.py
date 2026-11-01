import pathlib, sys
p = pathlib.Path('server.py')
s = p.read_text(encoding='utf-8')
old = "     if from_status == to_status: fail('invalid_transition','status','No status change.',409)\n"
new = ("     try: old_credentials=json.loads(person['credentials'] or '[]')\n"
       "     except Exception: old_credentials=[]\n"
       "     if from_status == to_status and old_credentials == list(dict.fromkeys(credentials)): fail('invalid_transition','status','Nothing to change: membership status and training names are the same as before.',409)\n")
if new in s: print('Already patched'); sys.exit()
if s.count(old) != 1: sys.exit('Expected line not found exactly once; send me the lines around "No status change"')
p.write_text(s.replace(old, new), encoding='utf-8'); print('patched server.py')
