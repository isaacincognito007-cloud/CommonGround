"""CommonGround · Isaac Shiloah Herbert V, ISAAC.INCOGNITO007."""
import argparse, hashlib, hmac, json, logging, os, re, secrets, sqlite3, threading, time
from datetime import date, datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from view import HTML
ROOT=Path(__file__).resolve().parent
DB=os.environ.get('CG_DB',str(ROOT/'data'/'commonground.sqlite3'))
PG_DSN=os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_URL') or ''
try:
 TZ=ZoneInfo('Asia/Kolkata')
except ZoneInfoNotFoundError:
 # Current Indian booking dates use fixed IST; no daylight-saving transitions.
 TZ=timezone(timedelta(hours=5,minutes=30),'Asia/Kolkata')
SECURE=os.environ.get('CG_SECURE_COOKIE','0')=='1'
PUBLIC_ORIGIN=os.environ.get('CG_ORIGIN','')
AUTH_ATTEMPTS={}
AUTH_LOCK=threading.Lock()
def today(): return datetime.now(TZ).date().isoformat()
def now(): return datetime.now(timezone.utc).isoformat(timespec='microseconds')
class Connection(sqlite3.Connection):
 def __exit__(self,*args):
  try:return super().__exit__(*args)
  finally:self.close()
class PgRow(dict):
 def __getitem__(self,key):
  if isinstance(key,int): return tuple(self.values())[key]
  if key=='end' and 'end_date' in self: key='end_date'
  return super().__getitem__(key)
def pg_row_factory(cursor):
 names=[column.name for column in cursor.description]
 def build(values): return PgRow((('end' if name=='end_date' else name,value) for name,value in zip(names,values)))
 return build
def postgres_sql(statement):
 if statement.lstrip().upper().startswith('CREATE OR REPLACE FUNCTION'): return statement
 ignore=statement.lstrip().upper().startswith('INSERT OR IGNORE INTO')
 if ignore: statement=statement.replace('INSERT OR IGNORE INTO','INSERT INTO',1)
 parts=statement.split("'")
 for i in range(0,len(parts),2):
  code=parts[i]
  code=re.sub(r'(?<![A-Za-z0-9_])end(?![A-Za-z0-9_])','end_date',code,flags=re.I)
  code=code.replace('julianday(h.end_date)','(h.end_date::date)').replace('julianday(h.start)','(h.start::date)')
  code=code.replace('?','%s')
  parts[i]=code
 statement="'".join(parts)
 if ignore: statement=statement.rstrip().rstrip(';')+' ON CONFLICT DO NOTHING'
 return statement
class PgConnection:
 def __init__(self,connection): self.raw=connection
 def __enter__(self): self.raw.__enter__(); return self
 def __exit__(self,*args): return self.raw.__exit__(*args)
 def __getattr__(self,name): return getattr(self.raw,name)
 def execute(self,statement,params=()):
  if statement.strip().upper()=='BEGIN IMMEDIATE':
   cursor=self.raw.cursor(); cursor.execute('SELECT pg_advisory_xact_lock(%s)',(734000000001,)); return cursor
  cursor=self.raw.cursor(); cursor.execute(postgres_sql(statement),params or ()); return cursor
def connect():
 if PG_DSN:
  import psycopg
  return PgConnection(psycopg.connect(PG_DSN,row_factory=pg_row_factory))
 c=sqlite3.connect(DB,timeout=15,factory=Connection); c.row_factory=sqlite3.Row
 c.execute('PRAGMA foreign_keys=ON'); c.execute('PRAGMA busy_timeout=15000'); return c
def password_hash(password,salt=None):
 salt=salt or secrets.token_hex(16)
 return salt+':'+hashlib.scrypt(password.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex()
def check_password(password,stored): return hmac.compare_digest(password_hash(password,stored.split(':')[0]),stored)
def public_user(u): return {k:u[k] for k in ['id','name','email','role','group_name','verified']}|{'credentials':json.loads(u['credentials'])}
class Problem(Exception):
 def __init__(self,code,field,message,status=422): self.code,self.field,self.message,self.status=code,field,message,status
def fail(code,field,message,status=422): raise Problem(code,field,message,status)
def text(body,key,minimum=1,maximum=1000):
 value=body.get(key)
 if not isinstance(value,str) or not minimum<=len(value.strip())<=maximum: fail('invalid_field',key,f'Enter {minimum}–{maximum} characters for {key.replace("_"," ")}.')
 return value.strip()
def dates(body,check_past=True):
 values=[]
 for field in ('start','end'):
  value=body.get(field)
  if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value): fail('invalid_date',field,'Use a valid YYYY-MM-DD date.')
  try: parsed=date.fromisoformat(value)
  except ValueError: fail('invalid_date',field,'Choose a real calendar date.')
  values.append(parsed)
 start,end=values
 if check_past and body['start']<today(): fail('past_date','start','You cannot book dates in the past. Please select a valid check-in and check-out date to continue.')
 if end<=start: fail('invalid_range','end','Return date must be later than collection date.')
 if (end-start).days>7: fail('range_limit','end','Bookings are limited to seven days.')
 return body['start'],body['end']
def audit(c,actor,resource,booking,action,detail): c.execute('INSERT INTO activity(actor_id,resource_id,booking_id,action,detail,created) VALUES(?,?,?,?,?,?)',(actor,resource,booking,action,detail,now()))
def notify(c,user,message,key=None): c.execute('INSERT OR IGNORE INTO notifications(user_id,message,dedupe,created) VALUES(?,?,?,?)',(user,message,key,now()))
def init_postgres_db():
 with connect() as c:
  c.execute('SELECT pg_advisory_xact_lock(734000000002)')
  for statement in (
   "CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,role TEXT NOT NULL,group_name TEXT NOT NULL,verified INTEGER NOT NULL DEFAULT 0,credentials TEXT NOT NULL DEFAULT '[]')",
   'CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),csrf TEXT NOT NULL,expires DOUBLE PRECISION NOT NULL)',
   'CREATE TABLE IF NOT EXISTS resources(id TEXT PRIMARY KEY,name TEXT NOT NULL,category TEXT NOT NULL,location TEXT NOT NULL,description TEXT NOT NULL,rules TEXT NOT NULL,training TEXT NOT NULL,available_from TEXT NOT NULL,available_to TEXT NOT NULL,owner_id TEXT NOT NULL REFERENCES users(id),manager_id TEXT REFERENCES users(id),active INTEGER NOT NULL DEFAULT 1)',
   "CREATE TABLE IF NOT EXISTS bookings(id TEXT PRIMARY KEY,resource_id TEXT NOT NULL REFERENCES resources(id),user_id TEXT NOT NULL REFERENCES users(id),start TEXT NOT NULL,end_date TEXT NOT NULL,purpose TEXT NOT NULL,status TEXT NOT NULL,reason TEXT NOT NULL,created TEXT NOT NULL,before_note TEXT,after_note TEXT,checked_in TEXT,returned TEXT,idempotency TEXT NOT NULL,request_hash TEXT NOT NULL,UNIQUE(user_id,idempotency))",
   'CREATE INDEX IF NOT EXISTS booking_calendar ON bookings(resource_id,status,start,end_date)',
   'CREATE TABLE IF NOT EXISTS incidents(id TEXT PRIMARY KEY,booking_id TEXT NOT NULL REFERENCES bookings(id),reporter_id TEXT NOT NULL REFERENCES users(id),kind TEXT NOT NULL,description TEXT NOT NULL,status TEXT NOT NULL DEFAULT \'Open\',resolution TEXT,created TEXT NOT NULL)',
   'CREATE TABLE IF NOT EXISTS activity(id BIGSERIAL PRIMARY KEY,actor_id TEXT NOT NULL REFERENCES users(id),resource_id TEXT REFERENCES resources(id),booking_id TEXT REFERENCES bookings(id),action TEXT NOT NULL,detail TEXT NOT NULL,created TEXT NOT NULL)',
   'CREATE TABLE IF NOT EXISTS notifications(id BIGSERIAL PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),message TEXT NOT NULL,dedupe TEXT UNIQUE,created TEXT NOT NULL)'
  ): c.execute(statement)
  c.execute("CREATE OR REPLACE FUNCTION commonground_activity_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Activity is append-only'; END; $$")
  c.execute('DROP TRIGGER IF EXISTS audit_no_update ON activity')
  c.execute('DROP TRIGGER IF EXISTS audit_no_delete ON activity')
  c.execute('CREATE TRIGGER audit_no_update BEFORE UPDATE ON activity FOR EACH ROW EXECUTE FUNCTION commonground_activity_immutable()')
  c.execute('CREATE TRIGGER audit_no_delete BEFORE DELETE ON activity FOR EACH ROW EXECUTE FUNCTION commonground_activity_immutable()')
def init_db(seed=False):
 if PG_DSN:
  init_postgres_db()
  if seed: raise SystemExit('Fictional --seed accounts are local-only; use vercel_bootstrap.py for real PostgreSQL accounts.')
  return
 Path(DB).parent.mkdir(parents=True,exist_ok=True)
 with connect() as c:
  c.executescript('''
  PRAGMA journal_mode=WAL;
  CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,role TEXT NOT NULL,group_name TEXT NOT NULL,verified INTEGER NOT NULL DEFAULT 0,credentials TEXT NOT NULL DEFAULT '[]');
  CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),csrf TEXT NOT NULL,expires REAL NOT NULL);
  CREATE TABLE IF NOT EXISTS resources(id TEXT PRIMARY KEY,name TEXT NOT NULL,category TEXT NOT NULL,location TEXT NOT NULL,description TEXT NOT NULL,rules TEXT NOT NULL,training TEXT NOT NULL,available_from TEXT NOT NULL,available_to TEXT NOT NULL,owner_id TEXT NOT NULL REFERENCES users(id),manager_id TEXT REFERENCES users(id),active INTEGER NOT NULL DEFAULT 1);
  CREATE TABLE IF NOT EXISTS bookings(id TEXT PRIMARY KEY,resource_id TEXT NOT NULL REFERENCES resources(id),user_id TEXT NOT NULL REFERENCES users(id),start TEXT NOT NULL,end TEXT NOT NULL,purpose TEXT NOT NULL,status TEXT NOT NULL,reason TEXT NOT NULL,created TEXT NOT NULL,before_note TEXT,after_note TEXT,checked_in TEXT,returned TEXT,idempotency TEXT NOT NULL,request_hash TEXT NOT NULL,UNIQUE(user_id,idempotency));
  CREATE INDEX IF NOT EXISTS booking_calendar ON bookings(resource_id,status,start,end);
  CREATE TABLE IF NOT EXISTS incidents(id TEXT PRIMARY KEY,booking_id TEXT NOT NULL REFERENCES bookings(id),reporter_id TEXT NOT NULL REFERENCES users(id),kind TEXT NOT NULL,description TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'Open',resolution TEXT,created TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS activity(id INTEGER PRIMARY KEY AUTOINCREMENT,actor_id TEXT NOT NULL REFERENCES users(id),resource_id TEXT REFERENCES resources(id),booking_id TEXT REFERENCES bookings(id),action TEXT NOT NULL,detail TEXT NOT NULL,created TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT NOT NULL REFERENCES users(id),message TEXT NOT NULL,dedupe TEXT UNIQUE,created TEXT NOT NULL);
  CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON activity BEGIN SELECT RAISE(ABORT,'Activity is append-only'); END;
  CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON activity BEGIN SELECT RAISE(ABORT,'Activity is append-only'); END;
  ''')
  if seed and not c.execute('SELECT 1 FROM users LIMIT 1').fetchone():
   password=os.environ.get('CG_SEED_PASSWORD','')
   if len(password)<12: raise SystemExit('Set CG_SEED_PASSWORD to a unique password of at least 12 characters before --seed.')
   users=[('member','Aarav Mehta','member','Open Studio',1,['Workshop induction']),('newcomer','Mira Rao','member','Design Collective',0,[]),('owner','Ananya Shah','owner','Campus Makerspace',1,['Workshop induction','Laser safety']),('manager','Rohan Sen','manager','Campus Makerspace',1,['Workshop induction','Laser safety']),('admin','Campus Administrator','admin','Campus Services',1,[])]
   for uid,name,role,group,verified,training in users: c.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?,?)',(uid,name,uid+'@campus.example',password_hash(password),role,group,verified,json.dumps(training)))
   start,end=today(),(datetime.now(TZ).date()+timedelta(days=180)).isoformat()
   items=[('camera','Sony Alpha field kit','Photography','Media Lab · Block B','A mirrorless camera, two lenses, tripod and audio recorder for fieldwork and creative projects.','Collect from the equipment desk. Keep the kit dry. Return all labelled accessories.','Workshop induction'),('laser','Precision laser cutter','Fabrication','Fabrication Lab · Block A','A supervised 60W laser workstation for approved sheet materials and precise fabrication.','A qualified staff supervisor must be present. No PVC or unknown materials.','Laser safety'),('studio','Collaboration studio','Spaces','Innovation Centre · Level 1','A quiet, accessible room for eight with a whiteboard, display and adjustable desks.','Keep the accessible route clear. Leave the room ready for the next group.',''),('scope','Digital microscope','Research','Materials Lab · Block C','High-resolution inspection and image capture for non-hazardous material samples.','Non-biological samples only. Clean the stage and cover the unit after use.','Workshop induction')]
   for rid,name,cat,loc,desc,rules,training in items:
    c.execute('INSERT INTO resources VALUES(?,?,?,?,?,?,?,?,?,?,?,1)',(rid,name,cat,loc,desc,rules,training,start,end,'owner','manager')); audit(c,'owner',rid,None,'Resource listed',name)
def manages(u,r): return u['role']=='admin' or u['id'] in (r['owner_id'],r['manager_id'])
def resource(c,rid):
 r=c.execute('SELECT * FROM resources WHERE id=?',(rid,)).fetchone()
 if not r: fail('not_found','resource','Resource not found.',404)
 return r
def eligible(u,r):
 missing=[]
 if not u['verified']: missing.append('Verified campus membership')
 if r['training'] and r['training'] not in json.loads(u['credentials']): missing.append(r['training'])
 return missing
def overlap_request(c,rid,start,end,exclude=''): return c.execute("SELECT id,status FROM bookings WHERE resource_id=? AND status IN ('Pending','Waitlisted') AND start<? AND end>? AND id!=? ORDER BY created,id LIMIT 1",(rid,end,start,exclude)).fetchone()
def conflict(c,rid,start,end,exclude=''): return c.execute("SELECT id FROM bookings WHERE resource_id=? AND status IN ('Pending','Approved','Checked in','Return pending') AND ((start<? AND end>?) OR (status IN ('Checked in','Return pending') AND end<=?)) AND id!=? LIMIT 1",(rid,end,start,today(),exclude)).fetchone()
def usage(c,group,rid,exclude=''): return c.execute("SELECT COUNT(*) FROM bookings b JOIN users u ON u.id=b.user_id WHERE u.group_name=? AND b.resource_id=? AND b.status IN ('Pending','Approved','Checked in','Return pending') AND b.id!=?",(group,rid,exclude)).fetchone()[0]
def queue(c,rid):
 cutoff=(datetime.now(TZ).date()-timedelta(days=30)).isoformat()
 return c.execute("SELECT b.*,u.group_name,COALESCE((SELECT SUM(julianday(h.end)-julianday(h.start)) FROM bookings h JOIN users hu ON hu.id=h.user_id WHERE hu.group_name=u.group_name AND h.resource_id=b.resource_id AND h.status='Completed' AND h.end>=?),0) score FROM bookings b JOIN users u ON u.id=b.user_id WHERE b.resource_id=? AND b.status='Waitlisted' ORDER BY score,b.created,b.id",(cutoff,rid)).fetchall()
def booking_view(c,b,u):
 r=resource(c,b['resource_id']); borrower=c.execute('SELECT name,group_name FROM users WHERE id=?',(b['user_id'],)).fetchone()
 result=dict(b); result.pop('idempotency',None); result.pop('request_hash',None)
 result.update(resource_name=r['name'],borrower=borrower['name'],group_name=borrower['group_name'],can_manage=manages(u,r),training=r['training'])
 result['queue_position']=next((i+1 for i,x in enumerate(queue(c,r['id'])) if x['id']==b['id']),None)
 result['incidents']=[dict(x) for x in c.execute('SELECT * FROM incidents WHERE booking_id=? ORDER BY created',(b['id'],))]
 result['history']=[dict(x) for x in c.execute('SELECT a.*,u.name actor FROM activity a JOIN users u ON u.id=a.actor_id WHERE booking_id=? ORDER BY a.id',(b['id'],))]
 return result
class Handler(BaseHTTPRequestHandler):
 server_version='CommonGround'
 def setup(self):
  super().setup();self.connection.settimeout(20)
 def log_message(self,fmt,*args): logging.info('%s %s',self.address_string(),fmt%args)
 def security(self):
  for k,v in {'X-Content-Type-Options':'nosniff','Referrer-Policy':'same-origin','X-Frame-Options':'DENY','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",'Permissions-Policy':'camera=(), microphone=(), geolocation=()'}.items(): self.send_header(k,v)
  if SECURE: self.send_header('Strict-Transport-Security','max-age=31536000')
 def send_json(self,value,status=200,cookie=None):
  raw=json.dumps(value,ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.security(); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(raw)))
  if cookie: self.send_header('Set-Cookie',cookie)
  self.end_headers(); self.wfile.write(raw)
 def body(self):
  if self.headers.get('Content-Type','').split(';')[0]!='application/json': fail('content_type','request','Send application/json.',415)
  try: length=int(self.headers.get('Content-Length','0'))
  except ValueError: fail('invalid_body','request','Invalid request length.',400)
  if not 0<length<=20000: fail('body_limit','request','Request must be between 1 and 20,000 bytes.',413)
  try: b=json.loads(self.rfile.read(length))
  except (ValueError,UnicodeDecodeError): fail('invalid_json','request','Invalid JSON.',400)
  if not isinstance(b,dict): fail('invalid_json','request','Request must be an object.',400)
  return b
 def auth(self,c,unsafe=False):
  cookie=SimpleCookie()
  try: cookie.load(self.headers.get('Cookie','')); raw=cookie['cg_session'].value
  except (KeyError,ValueError): fail('session_required','session','Please sign in to continue.',401)
  token=hashlib.sha256(raw.encode()).hexdigest(); s=c.execute('SELECT * FROM sessions WHERE token=? AND expires>?',(token,time.time())).fetchone()
  if not s: fail('session_expired','session','Your session has expired. Please sign in again.',401)
  if unsafe and not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),s['csrf']): fail('csrf','request','Refresh the page and try again.',403)
  return c.execute('SELECT * FROM users WHERE id=?',(s['user_id'],)).fetchone(),s
 def do_GET(self):
  path=urlparse(self.path).path
  if not path.startswith('/api/'):
   files={'/app.js':('app.js','text/javascript'),'/style.css':('style.css','text/css'),'/favicon.svg':('favicon.svg','image/svg+xml')}
   if path in files:
    name,mime=files[path]
    try: raw=(ROOT/'web'/name).read_bytes()
    except FileNotFoundError: self.send_error(404); return
   else: raw,mime=HTML.encode(),'text/html'
   self.send_response(200); self.send_header('Content-Type',mime+'; charset=utf-8'); self.send_header('Content-Length',str(len(raw))); self.send_header('Cache-Control','no-cache'); self.security(); self.end_headers(); self.wfile.write(raw); return
  try:
   with connect() as c:
    if path=='/api/health': c.execute('SELECT 1'); return self.send_json({'ok':True,'timezone':'Asia/Kolkata'})
    u,s=self.auth(c)
    if path=='/api/session': return self.send_json({'user':public_user(u),'csrf':s['csrf'],'today':today()})
    if path=='/api/state':
     resources=[dict(r)|{'missing':eligible(u,r),'can_manage':manages(u,r)} for r in c.execute('SELECT r.*,u.name owner_name FROM resources r JOIN users u ON u.id=r.owner_id ORDER BY r.name')]
     visible=c.execute("SELECT b.* FROM bookings b JOIN resources r ON r.id=b.resource_id WHERE b.user_id=? OR r.owner_id=? OR r.manager_id=? OR ?='admin' ORDER BY b.created DESC",(u['id'],u['id'],u['id'],u['role'])).fetchall()
     for b in visible:
      if b['user_id']==u['id'] and b['status'] in ('Approved','Checked in','Return pending'):
       if b['end']<=today(): notify(c,u['id'],f'Overdue: {b["id"]}. Contact the resource manager.',f'overdue:{b["id"]}:{today()}')
       elif b['start']<=(datetime.now(TZ).date()+timedelta(days=1)).isoformat() and b['status']=='Approved': notify(c,u['id'],f'Collection reminder: {b["id"]} starts {b["start"]}.',f'reminder:{b["id"]}')
     activity=c.execute("SELECT a.*,u.name actor,r.name resource_name FROM activity a JOIN users u ON u.id=a.actor_id LEFT JOIN resources r ON r.id=a.resource_id LEFT JOIN bookings b ON b.id=a.booking_id WHERE b.user_id=? OR r.owner_id=? OR r.manager_id=? OR ?='admin' ORDER BY a.id DESC LIMIT 200",(u['id'],u['id'],u['id'],u['role'])).fetchall()
     people=[public_user(x) for x in c.execute("SELECT * FROM users WHERE role='member' ORDER BY name")] if u['role']=='admin' else []
     return self.send_json({'user':public_user(u),'today':today(),'resources':resources,'bookings':[booking_view(c,b,u) for b in visible],'activity':[dict(x) for x in activity],'notifications':[dict(x) for x in c.execute('SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 50',(u['id'],))],'people':people})
    fail('not_found','request','API endpoint not found.',404)
  except Problem as e: self.send_json({'error':vars(e)},e.status)
  except Exception: logging.exception('Request failed'); self.send_json({'error':{'code':'server_error','message':'Could not load this request. Please retry.'}},500)
 def do_POST(self):
  try:
   expected=PUBLIC_ORIGIN or ('https://' if SECURE else 'http://')+self.headers.get('Host','')
   if self.headers.get('Origin')!=expected: fail('origin','request','This request must originate from this application.',403)
   body=self.body(); path=urlparse(self.path).path
   with connect() as c:
    c.execute('BEGIN IMMEDIATE')
    if path=='/api/login':
     email=text(body,'email',3,180).lower(); password=text(body,'password',1,300); ip=self.client_address[0]
     with AUTH_LOCK:
      attempts=[x for x in AUTH_ATTEMPTS.get(ip,[]) if x>time.time()-300]; AUTH_ATTEMPTS[ip]=attempts
      if len(attempts)>=30: fail('rate_limit','email','Too many attempts. Wait five minutes.',429)
      attempts.append(time.time())
     u=c.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
     stored=u['password'] if u else password_hash('unknown-account-timing-value')
     if not check_password(password,stored) or not u: fail('login_failed','email','Email or password is incorrect.',401)
     raw,csrf=secrets.token_urlsafe(32),secrets.token_urlsafe(32); c.execute('DELETE FROM sessions WHERE expires<?',(time.time(),)); c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashlib.sha256(raw.encode()).hexdigest(),u['id'],csrf,time.time()+28800)); c.commit()
     return self.send_json({'user':public_user(u),'csrf':csrf,'today':today()},cookie=f'cg_session={raw}; Path=/; HttpOnly; SameSite=Strict; Max-Age=28800'+('; Secure' if SECURE else ''))
    u,s=self.auth(c,True)
    if path=='/api/logout':
     c.execute('DELETE FROM sessions WHERE token=?',(s['token'],)); c.commit(); return self.send_json({'ok':True},cookie='cg_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0'+('; Secure' if SECURE else ''))
    if path=='/api/password':
     current=text(body,'current_password',1,300); new=text(body,'new_password',12,300)
     if not check_password(current,u['password']): fail('login_failed','current_password','Current password is incorrect.',403)
     c.execute('UPDATE users SET password=? WHERE id=?',(password_hash(new),u['id'])); c.execute('DELETE FROM sessions WHERE user_id=?',(u['id'],)); audit(c,u['id'],None,None,'Password changed','All sessions revoked'); c.commit(); return self.send_json({'ok':True})
    if path=='/api/resources':
     if u['role'] not in ('owner','admin') or not u['verified']: fail('forbidden','role','Only verified owners can list resources.',403)
     name=text(body,'name',3,100); cat=text(body,'category',2,50); loc=text(body,'location',3,150); desc=text(body,'description',10,1000); rules=text(body,'rules',10,1000); training=text(body,'training',0,100)
     start,end=body.get('available_from'),body.get('available_to')
     for key,v in [('available_from',start),('available_to',end)]:
      try:
       if not isinstance(v,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',v): raise ValueError()
       date.fromisoformat(v)
      except ValueError: fail('invalid_date',key,'Choose a valid availability date.')
     if start<today() or end<=start: fail('invalid_range','available_to','Availability must begin today or later and end after it begins.')
     rid=secrets.token_hex(8); c.execute('INSERT INTO resources VALUES(?,?,?,?,?,?,?,?,?,?,?,1)',(rid,name,cat,loc,desc,rules,training,start,end,u['id'],None)); audit(c,u['id'],rid,None,'Resource listed',name); c.commit(); return self.send_json({'id':rid},201)
    if path=='/api/bookings':
     start,end=dates(body); purpose=text(body,'purpose',10,1000); rid=text(body,'resource_id',1,80); key=self.headers.get('Idempotency-Key','')
     if not re.fullmatch(r'[A-Za-z0-9_-]{12,100}',key): fail('idempotency_required','request','A valid request key is required.',400)
     digest=hashlib.sha256(json.dumps({'start':start,'end':end,'purpose':purpose,'resource_id':rid},sort_keys=True).encode()).hexdigest(); previous=c.execute('SELECT * FROM bookings WHERE user_id=? AND idempotency=?',(u['id'],key)).fetchone()
     if previous:
      if previous['request_hash']!=digest: fail('idempotency_conflict','request','Request key already used for different details.',409)
      return self.send_json({'booking':booking_view(c,previous,u),'replayed':True})
     r=resource(c,rid)
     if not r['active'] or start<r['available_from'] or end>r['available_to']: fail('unavailable','start','Choose dates inside the availability window.',409)
     if c.execute("SELECT 1 FROM bookings WHERE user_id=? AND resource_id=? AND start=? AND end=? AND status NOT IN ('Cancelled','Rejected','Completed')",(u['id'],rid,start,end)).fetchone(): fail('duplicate','request','You already have an active request for these dates.',409)
     reasons=[]; missing=eligible(u,r)
     if missing: reasons.append('Awaiting verification: '+', '.join(missing))
     if overlap_request(c,rid,start,end): reasons.append('Dates overlap another active request; queued by shared access rules')
     elif conflict(c,rid,start,end): reasons.append('Dates overlap an approved or pending booking')
     if usage(c,u['group_name'],rid)>=2: reasons.append('Group limit: two active requests per resource')
     status='Waitlisted' if reasons else 'Pending'; reason='; '.join(reasons) if reasons else 'Eligibility checks passed. Awaiting human approval.'; bid='CG-'+secrets.token_hex(4).upper()
     c.execute('INSERT INTO bookings(id,resource_id,user_id,start,end,purpose,status,reason,created,idempotency,request_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(bid,rid,u['id'],start,end,purpose,status,reason,now(),key,digest)); audit(c,u['id'],rid,bid,'Request submitted',status+': '+reason); notify(c,u['id'],f'{bid}: {status}. {reason}'); notify(c,r['owner_id'],f'New request {bid} for {r["name"]}.'); c.commit(); return self.send_json({'booking':booking_view(c,c.execute('SELECT * FROM bookings WHERE id=?',(bid,)).fetchone(),u)},201)
    if re.fullmatch('/api/users/[^/]+/verify',path):
     if u['role']!='admin': fail('forbidden','role','Only administrators may verify membership and training.',403)
     target=path.split('/')[3]; person=c.execute('SELECT * FROM users WHERE id=?',(target,)).fetchone()
     if not person: fail('not_found','user','User not found.',404)
     reason=text(body,'reason',10,1000); verified=body.get('verified'); credentials=body.get('credentials')
     if not isinstance(verified,bool) or not isinstance(credentials,list) or len(credentials)>20 or any(not isinstance(x,str) or not 1<=len(x)<=100 for x in credentials): fail('invalid_field','credentials','Supply membership status and a list of training names.')
     c.execute('UPDATE users SET verified=?,credentials=? WHERE id=?',(verified,json.dumps(list(dict.fromkeys(credentials))),target)); audit(c,u['id'],None,None,'Verification reviewed',person['name']+': '+reason+'; membership='+str(verified)+'; training='+', '.join(credentials)); notify(c,target,'Your verification has been reviewed. '+reason); c.commit(); return self.send_json({'ok':True})
    if re.fullmatch('/api/bookings/[^/]+/action',path):
     bid=path.split('/')[3]; b=c.execute('SELECT * FROM bookings WHERE id=?',(bid,)).fetchone()
     if not b: fail('not_found','booking','Booking not found.',404)
     r=resource(c,b['resource_id']); manager=manages(u,r)
     if not manager and b['user_id']!=u['id']: fail('forbidden','booking','You cannot access this booking.',403)
     action=text(body,'action',1,40); note=text(body,'note',3,1500); borrower=c.execute('SELECT * FROM users WHERE id=?',(b['user_id'],)).fetchone(); status=b['status']; newstatus=status
     if action in ('approve','reject','waitlist','confirm_return','resolve','extend','assign_manager') and not manager: fail('forbidden','role','A resource manager must review this action.',403)
     if action in ('approve','reject','waitlist'):
      if status not in ('Pending','Waitlisted'): fail('invalid_transition','status','Only pending or waitlisted requests can be reviewed.',409)
      if action=='approve':
       if eligible(borrower,r): fail('not_eligible','training','Verify membership and required training before approval.',409)
       if b['start']<today(): fail('past_date','start','The collection date has passed. Request new dates.',409)
       if usage(c,borrower['group_name'],r['id'],bid)>=2: fail('fair_limit','booking','This group already has two active requests for this resource.',409)
       if conflict(c,r['id'],b['start'],b['end'],bid): fail('conflict','start','Dates overlap an approved booking.',409)
       if b['status']=='Waitlisted':
        for candidate in queue(c,r['id']):
         cu=c.execute('SELECT * FROM users WHERE id=?',(candidate['user_id'],)).fetchone()
         if candidate['start']<b['end'] and candidate['end']>b['start'] and candidate['start']>=today() and not eligible(cu,r) and usage(c,cu['group_name'],r['id'],candidate['id'])<2:
          if candidate['id']!=bid: fail('queue_order','booking','An eligible overlapping request has higher waiting-list priority.',409)
          break
       newstatus='Approved'
      else: newstatus='Rejected' if action=='reject' else 'Waitlisted'
     elif action=='cancel':
      if status not in ('Pending','Waitlisted','Approved'): fail('invalid_transition','status','Collected bookings cannot be cancelled.',409)
      newstatus='Cancelled'
     elif action=='check_in':
      if status!='Approved' or not b['start']<=today()<b['end']: fail('invalid_transition','status','Collection is allowed only during the approved period.',409)
      if eligible(borrower,r): fail('not_eligible','training','Membership or training is no longer valid.',409)
      if c.execute("SELECT 1 FROM bookings WHERE resource_id=? AND id!=? AND status IN ('Checked in','Return pending')",(r['id'],bid)).fetchone(): fail('custody_conflict','booking','The previous resource handover is still open. Contact a manager.',409)
      newstatus='Checked in'; c.execute('UPDATE bookings SET before_note=?,checked_in=? WHERE id=?',(note,now(),bid))
     elif action=='return':
      if status!='Checked in': fail('invalid_transition','status','Only collected resources can be returned.',409)
      newstatus='Return pending'; c.execute('UPDATE bookings SET after_note=?,returned=? WHERE id=?',(note,now(),bid))
     elif action=='confirm_return':
      if status!='Return pending': fail('invalid_transition','status','Record the return before confirmation.',409)
      if c.execute("SELECT 1 FROM incidents WHERE booking_id=? AND status='Open'",(bid,)).fetchone(): fail('open_incident','booking','Resolve open incidents before confirming return.',409)
      newstatus='Completed'
     elif action=='incident':
      kind=body.get('kind')
      if kind not in ('Damage','Delay','Safety','Dispute'): fail('invalid_field','kind','Choose an incident type.')
      c.execute('INSERT INTO incidents(id,booking_id,reporter_id,kind,description,created) VALUES(?,?,?,?,?,?)',(secrets.token_hex(8),bid,u['id'],kind,note,now())); notify(c,r['owner_id'],f'{bid}: {kind} reported. Human review required.')
     elif action=='resolve':
      incident=text(body,'incident_id',1,100)
      if not c.execute("UPDATE incidents SET status='Resolved',resolution=? WHERE id=? AND booking_id=? AND status='Open'",(note,incident,bid)).rowcount: fail('not_found','incident','Open incident not found.',404)
     elif action=='extend':
      if status not in ('Approved','Checked in'): fail('invalid_transition','status','Only approved or collected bookings can be extended.',409)
      start,end=dates({'start':b['start'],'end':body.get('end')},False)
      if end<=b['end'] or end>r['available_to']: fail('invalid_range','end','Choose a later return within availability and seven-day total limit.')
      if c.execute("SELECT 1 FROM bookings WHERE resource_id=? AND id!=? AND status IN ('Pending','Waitlisted') AND start<? AND end>?",(r['id'],bid,end,b['end'])).fetchone(): fail('queue_protected','end','An extension cannot displace a pending or waitlisted request.',409)
      if conflict(c,r['id'],start,end,bid): fail('conflict','end','The extension conflicts with another active booking.',409)
      c.execute('UPDATE bookings SET end=? WHERE id=?',(end,bid))
     elif action=='assign_manager':
      if u['role']!='admin' and u['id']!=r['owner_id']: fail('forbidden','role','Only owners or administrators assign managers.',403)
      mid=text(body,'manager_id',1,100)
      if not c.execute("SELECT 1 FROM users WHERE id=? AND role='manager' AND verified=1",(mid,)).fetchone(): fail('invalid_field','manager_id','Choose an existing verified manager ID.')
      c.execute('UPDATE resources SET manager_id=? WHERE id=?',(mid,r['id']))
     else: fail('invalid_action','action','Unknown action.',400)
     c.execute('UPDATE bookings SET status=?,reason=? WHERE id=?',(newstatus,note if newstatus!=status else b['reason'],bid)); audit(c,u['id'],r['id'],bid,action.replace('_',' ').capitalize(),note+('; end='+str(body.get('end')) if action=='extend' else '')); notify(c,b['user_id'],f'{bid}: {action.replace("_"," ")}. {note}')
     if newstatus in ('Cancelled','Rejected','Completed'):
      for q in c.execute("SELECT user_id,id FROM bookings WHERE resource_id=? AND status='Waitlisted'",(r['id'],)): notify(c,q['user_id'],f'{q["id"]}: availability changed. A manager can review the waiting list.')
     c.commit(); return self.send_json({'booking':booking_view(c,c.execute('SELECT * FROM bookings WHERE id=?',(bid,)).fetchone(),u)})
    fail('not_found','request','API endpoint not found.',404)
  except Problem as e: self.send_json({'error':vars(e)},e.status)
  except sqlite3.OperationalError: logging.exception('Database failed'); self.send_json({'error':{'code':'storage_busy','field':'request','message':'Storage is busy. Keep your details and retry.'}},503)
  except Exception: logging.exception('Request failed'); self.send_json({'error':{'code':'server_error','field':'request','message':'Could not complete this request. Keep your details and retry.'}},500)
def main():
 p=argparse.ArgumentParser(description='CommonGround resource sharing'); p.add_argument('--seed',action='store_true'); p.add_argument('--host',default=os.environ.get('CG_HOST','127.0.0.1')); p.add_argument('--port',type=int,default=int(os.environ.get('PORT','8000'))); args=p.parse_args(); logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s'); init_db(args.seed); server=ThreadingHTTPServer((args.host,args.port),Handler); logging.info('CommonGround listening on %s:%s · Asia/Kolkata',args.host,args.port); server.serve_forever()
if __name__=='__main__': main()
