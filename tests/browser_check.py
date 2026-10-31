"""Real Chromium journeys using its DevTools protocol; no browser library required.
Isaac Shiloah Herbert V · ISAAC.INCOGNITO007.
"""
import base64, hashlib, json, os, secrets, shutil, socket, struct, subprocess, sys, tempfile, threading, time, urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
class CDP:
 def __init__(self,url):
  from urllib.parse import urlparse
  p=urlparse(url);self.sock=socket.create_connection((p.hostname,p.port),15);self.sock.settimeout(60);key=base64.b64encode(secrets.token_bytes(16)).decode()
  self.sock.sendall(f'GET {p.path} HTTP/1.1\r\nHost: {p.hostname}:{p.port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n'.encode());response=b''
  while b'\r\n\r\n' not in response:response+=self.sock.recv(1)
  if b'101 Switching Protocols' not in response:raise RuntimeError('DevTools WebSocket upgrade failed')
  self.seq=0;self.errors=[]
 def read(self,n):
  raw=b''
  while len(raw)<n:
   part=self.sock.recv(n-len(raw))
   if not part:raise RuntimeError('Chromium disconnected')
   raw+=part
  return raw
 def frame(self,payload,opcode=1):
  mask=secrets.token_bytes(4);n=len(payload);header=bytes([128|opcode,128|(n if n<126 else 126 if n<65536 else 127)])
  if n>=126:header+=struct.pack('!H' if n<65536 else '!Q',n)
  self.sock.sendall(header+mask+bytes(x^mask[i%4] for i,x in enumerate(payload)))
 def recv(self):
  chunks=b''
  while True:
   first,second=self.read(2);n=second&127
   if n==126:n=struct.unpack('!H',self.read(2))[0]
   elif n==127:n=struct.unpack('!Q',self.read(8))[0]
   mask=self.read(4) if second&128 else None;body=self.read(n)
   if mask:body=bytes(x^mask[i%4] for i,x in enumerate(body))
   if first&15==9:self.frame(body,10);continue
   if first&15==8:raise RuntimeError('Chromium closed DevTools')
   chunks+=body
   if first&128:return json.loads(chunks)
 def call(self,method,params=None):
  self.seq+=1;seq=self.seq;self.frame(json.dumps({'id':seq,'method':method,'params':params or {}}).encode())
  while True:
   result=self.recv()
   if result.get('method')=='Runtime.exceptionThrown':self.errors.append(result['params'])
   if result.get('id')==seq:
    if 'error' in result:raise RuntimeError(result['error'])
    return result.get('result',{})
 def evaluate(self,expression):
  r=self.call('Runtime.evaluate',{'expression':expression,'awaitPromise':True,'returnByValue':True})
  if 'exceptionDetails' in r:raise AssertionError(r['exceptionDetails'])
  return r.get('result',{}).get('value')
 def wait(self,condition,timeout=12):
  end=time.time()+timeout
  while time.time()<end:
   if self.evaluate(condition):return
   time.sleep(.08)
  raise AssertionError('Browser wait timed out: '+condition+'; '+str(self.evaluate('document.body.innerText'))[:1500])
 def screenshot(self,path):
  r=self.call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False});Path(path).parent.mkdir(parents=True,exist_ok=True);Path(path).write_bytes(base64.b64decode(r['data']))
def run():
 binary=os.environ.get('CHROMIUM') or shutil.which('chromium') or shutil.which('google-chrome')
 if not binary:raise SystemExit('Chromium is required. Install Chromium or set CHROMIUM to its executable.')
 password=secrets.token_urlsafe(24)
 with tempfile.TemporaryDirectory(prefix='cg-browser-',dir='.') as temp:
  server.DB=str(Path(temp)/'browser.sqlite3');os.environ['CG_SEED_PASSWORD']=password;server.init_db(True);server.Handler.log_message=lambda *a:None
  profile=Path(temp)/'profile'
  if os.environ.get('CG_TEST_TRANSPORT')=='socketpair':
   from cdp_pipe import PipeCDP
   http=None;base='http://localhost:8000';cdp=PipeCDP(binary,profile);proc=cdp.proc;log=cdp.log
  else:
   http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=http.serve_forever,daemon=True).start();base='http://127.0.0.1:'+str(http.server_port)
   log=open(Path(temp)/'chromium.log','w');proc=subprocess.Popen([binary,'--headless','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--no-first-run','--remote-debugging-port=0','--user-data-dir='+str(profile.resolve()),'about:blank'],stdout=log,stderr=log)
   active=profile/'DevToolsActivePort'
   for _ in range(150):
    if active.exists():break
    if proc.poll() is not None:raise RuntimeError('Chromium failed to start')
    time.sleep(.1)
   port=active.read_text().splitlines()[0]
   req=urllib.request.Request('http://127.0.0.1:'+port+'/json/new?about:blank',method='PUT');target=json.load(urllib.request.urlopen(req));cdp=CDP(target['webSocketDebuggerUrl'])
  try:
   cdp.call('Runtime.enable');cdp.call('Page.enable');cdp.call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1080,'deviceScaleFactor':1,'mobile':False});cdp.call('Page.navigate',{'url':base+'/#bookings'});cdp.wait('!!document.querySelector("#login-form")')
   cdp.evaluate('window.qaErrors=[];window.addEventListener("error",e=>qaErrors.push(e.message));window.addEventListener("unhandledrejection",e=>qaErrors.push(String(e.reason)));')
   def login(user):
    cdp.evaluate(f'document.querySelector("#email").value={json.dumps(user+"@campus.example")};document.querySelector("#password").value={json.dumps(password)};document.querySelector("#login-form").requestSubmit();');cdp.wait('!!document.querySelector(".sidebar")')
   login('member');cdp.wait('document.body.innerText.includes("Your bookings, from request to return.")');print('PASS intended protected route after login')
   for page in ['bookings','resources','verification','activity','notifications','profile']:
    cdp.evaluate('location.hash='+json.dumps(page));cdp.call('Page.reload');cdp.wait('!!document.querySelector(".sidebar")');assert cdp.evaluate('!!document.querySelector("#main h1")');print('PASS protected route refresh:',page)
   cdp.evaluate('location.hash="resources"');cdp.wait('!!document.querySelector("[data-resource=camera]")');cdp.screenshot('output/screenshots/desktop.png')
   cdp.evaluate('document.querySelector("[data-resource=camera]").click()');cdp.wait('!!document.querySelector("#booking-form")');assert cdp.evaluate('document.querySelector("#start").min===session.today')
   result=cdp.evaluate('''(()=>{const f=document.querySelector('#booking-form');f.elements.start.value=addDays(session.today,-1);f.elements.end.value=session.today;f.elements.purpose.value='Field research project with full kit';f.elements.accept.checked=true;f.dispatchEvent(new Event('input',{bubbles:true}));return {disabled:document.querySelector('#request-submit').disabled,error:document.querySelector('#start-error').textContent};})()''');assert result['disabled'] and 'past' in result['error'];print('PASS UI rejects yesterday')
   cdp.evaluate('document.querySelector("#booking-form").dispatchEvent(new Event("submit",{bubbles:true,cancelable:true}))');cdp.wait('document.querySelector("#modal").open');assert cdp.evaluate('document.querySelector("#dialog-title").textContent')=='Invalid Booking Dates';assert cdp.evaluate('!!document.querySelector("#modal [role=alert]")');cdp.evaluate('document.querySelector("#error-return").click()');cdp.wait('document.activeElement.id==="start"');print('PASS invalid-date dialog and focus return')
   cdp.evaluate('document.querySelector("#start").value=session.today;document.querySelector("#end").value=session.today;document.querySelector("#booking-form").dispatchEvent(new Event("input",{bubbles:true}))');assert cdp.evaluate('document.querySelector("#request-submit").disabled');print('PASS UI rejects equal dates')
   cdp.evaluate('document.querySelector("#end").value=addDays(session.today,1);document.querySelector("#booking-form").dispatchEvent(new Event("input",{bubbles:true}));document.querySelector("#request-submit").click();document.querySelector("#request-submit").click()');cdp.wait('document.querySelector("#modal").open && document.querySelector("#dialog-title").textContent==="Booking Request Submitted"');bid=cdp.evaluate('data.bookings[0].id');assert cdp.evaluate('data.bookings.length')==1;assert cdp.evaluate('document.querySelector("#modal").contains(document.activeElement)');assert cdp.evaluate('document.querySelector("#modal .status").textContent')=='Pending';cdp.screenshot('output/screenshots/confirmation.png');print('PASS real saved response, pending status, double-click prevention, focus entry')
   cdp.call('Input.dispatchKeyEvent',{'type':'keyDown','key':'Escape','code':'Escape','windowsVirtualKeyCode':27});cdp.call('Input.dispatchKeyEvent',{'type':'keyUp','key':'Escape','code':'Escape','windowsVirtualKeyCode':27});cdp.wait('!document.querySelector("#modal").open');print('PASS Escape dismisses dialog')
   cdp.evaluate('location.hash="bookings"');cdp.wait('!!document.querySelector("[data-record]")');assert bid in cdp.evaluate('document.body.innerText');print('PASS saved booking visible in history')
   cdp.evaluate('document.querySelector("#logout").click()');cdp.wait('!!document.querySelector("#login-form")');login('owner');cdp.evaluate('location.hash="manage"');cdp.wait('!!document.querySelector("[data-record]")');cdp.evaluate('document.querySelector("[data-record]").click()');cdp.wait('!!document.querySelector("[data-action=approve]")')
   def action(name,note):
    cdp.evaluate(f'document.querySelector("[data-action={name}]").click()');cdp.wait('!!document.querySelector("#action-form")');cdp.evaluate('document.querySelector("#note").value='+json.dumps(note)+';document.querySelector("#action-form").requestSubmit()');cdp.wait('!document.querySelector("#modal").open')
   action('approve','Training and project reviewed. Staff available.');cdp.wait('!!document.querySelector("[data-action=check_in]")');print('PASS owner approval')
   cdp.evaluate('document.querySelector("#logout").click()');cdp.wait('!!document.querySelector("#login-form")');login('member');cdp.wait('!!document.querySelector("[data-action=check_in]")');action('check_in','Camera clean, both lenses and tripod present.');cdp.wait('!!document.querySelector("[data-action=return]")');action('return','All parts returned dry and in original condition.');cdp.wait('document.body.innerText.includes("Return pending")');print('PASS member collection and condition-based return')
   cdp.evaluate('document.querySelector("#logout").click()');cdp.wait('!!document.querySelector("#login-form")');login('owner');cdp.wait('!!document.querySelector("[data-action=confirm_return]")');action('confirm_return','Equipment inspected. Complete and ready for reuse.');cdp.wait('document.body.innerText.includes("Completed")');assert cdp.evaluate('data.bookings[0].history.length')==5;print('PASS owner-confirmed return and complete history')
   cdp.evaluate('location.hash="resources"');cdp.wait('!!document.querySelector("#new-resource")');cdp.evaluate('document.querySelector("#new-resource").click()');cdp.wait('!!document.querySelector("#resource-form")');cdp.evaluate('''(()=>{const f=document.querySelector('#resource-form');for(const [k,v] of Object.entries({name:'Portable research recorder',location:'Campus media desk',description:'A portable recorder with microphones and a padded case.',rules:'Return all accessories clean and labelled.'}))f.elements[k].value=v;f.requestSubmit();})()''');cdp.wait('!!document.querySelector("#catalog")');assert cdp.evaluate('document.body.innerText.includes("Portable research recorder")');print('PASS owner resource listing')
   for width,height in [(390,844),(768,1024),(1440,1080)]:
    cdp.call('Emulation.setDeviceMetricsOverride',{'width':width,'height':height,'deviceScaleFactor':1,'mobile':width<500});assert cdp.evaluate('document.documentElement.scrollWidth<=innerWidth'),f'Horizontal overflow at {width}'
    if width==390:cdp.screenshot('output/screenshots/mobile.png')
    print('PASS responsive overflow check',width)
   cdp.call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1080,'deviceScaleFactor':1,'mobile':False})
   labels=cdp.evaluate('Array.from(document.querySelectorAll("button,input,select,textarea")).filter(e=>!e.disabled&&!((e.innerText||e.getAttribute("aria-label")||"").trim())&&!(e.labels&&e.labels.length)).map(e=>e.outerHTML)');assert not labels,labels
   assert not cdp.errors,cdp.errors;assert not cdp.evaluate('window.qaErrors||[]');print('PASS no uncaught browser exceptions; visible controls have accessible names')
   with server.connect() as c:c.execute('UPDATE sessions SET expires=0')
   cdp.call('Page.reload');cdp.wait('!!document.querySelector("#login-form")');print('PASS expired session recovery')
   print('BROWSER JOURNEYS PASSED')
  finally:
   proc.terminate();proc.wait(timeout=10);log.close()
   if http:http.shutdown();http.server_close()
if __name__=='__main__':run()
