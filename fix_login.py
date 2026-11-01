"""One-off patch for CommonGround login. Run from the project root: python fix_login.py"""
import re, pathlib, sys

def patch(path, fn):
    p = pathlib.Path(path)
    s = p.read_text(encoding='utf-8')
    new = fn(s)
    if new == s:
        print('NO CHANGE (already patched?):', path)
    else:
        p.write_text(new, encoding='utf-8'); print('patched:', path)

# ---------- server.py ----------
def fix_server(s):
    # 1. cut the demo-accounts route out of the authenticated area
    m = re.search(r"\n    if path=='/api/demo-accounts':\n(?:     .*\n)+?(?=    if path==)", s)
    if not m:
        if "if path=='/api/demo-accounts'" in s and s.index("if path=='/api/demo-accounts'") < s.index("u,s=self.auth(c)"):
            block = None
        else:
            sys.exit('demo-accounts route block not found in server.py')
    else:
        block = m.group(0)
        s = s.replace(block, '\n', 1)
        # 2. put it right after /api/health, before authentication
        health = "    if path=='/api/health': c.execute('SELECT 1'); return self.send_json({'ok':True,'timezone':'Asia/Kolkata'})\n"
        if health not in s: sys.exit('health line not found')
        s = s.replace(health, health + block.lstrip('\n'), 1)
    # 3. seeding must use the same flag as the app
    s = s.replace("is_demo = os.environ.get('CG_DEMO_MODE') == '1'", "is_demo = DEMO_MODE", 1)
    return s

# ---------- web/app.js ----------
NEW_LOADER = """async function loadDemoAccounts(){
 try{
  const r=await fetch('/api/demo-accounts',{credentials:'same-origin'});
  if(!r.ok) return [];
  const j=await r.json();
  return Array.isArray(j.accounts)?j.accounts:[];
 }catch(e){return [];}
}"""
def fix_js(s):
    s = re.sub(r"async function loadDemoAccounts\(\)\{.*?\n\}", lambda m: NEW_LOADER, s, count=1, flags=re.S)
    # email field must not be a password field; wrap input+button so the eye centers on the input only
    s = s.replace('<div class=\\"field password-field\\"><label for=\\"email\\">', '<div class=\\"field\\"><label for=\\"email\\">')
    s = s.replace('<div class="field password-field"><label for="email">', '<div class="field"><label for="email">')
    for q in ('\\"', '"'):
        old = f'<div class={q}field password-field{q}><label for={q}password{q}>Password</label><input'
        new = f'<div class={q}field{q}><label for={q}password{q}>Password</label><div class={q}password-wrap{q}><input'
        s = s.replace(old, new)
        s = s.replace(f'</svg></button></div><div id={q}login-error{q}', f'</svg></button></div></div><div id={q}login-error{q}')
    return s

# ---------- web/style.css ----------
def fix_css(s):
    s = s.replace('.password-field{position:relative}', '.password-wrap{position:relative}')
    s = s.replace('.password-field input{padding-right:48px}', '.password-wrap input{padding-right:52px}')
    return s

# ---------- tests ----------
def fix_tests(s):
    return s.replace(".request('/api/", ".request('/")

patch('server.py', fix_server)
patch('web/app.js', fix_js)
patch('web/style.css', fix_css)
patch('tests/test_service.py', fix_tests)
