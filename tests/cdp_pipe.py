"""Chromium pipe driver with optional HTTP-handler request bridging.
This adapter does not replace app logic; it bridges actual browser HTTP requests
through BaseHTTPRequestHandler and the real SQLite database when TCP is absent.
Isaac Shiloah Herbert V · ISAAC.INCOGNITO007.
"""
import base64,json,os,select,subprocess,time
from pathlib import Path
from urllib.parse import urlparse
from transport import exchange
class PipeCDP:
 def __init__(self,binary,profile):
  self.seq=0;self.errors=[];self.buffer=b'';self.pending={};self.session=None
  to_read,self.write_fd=os.pipe();self.read_fd,from_write=os.pipe()
  self.log=open(profile.parent/'chromium.log','w')
  def setup():os.dup2(to_read,3);os.dup2(from_write,4)
  self.proc=subprocess.Popen([binary,'--headless','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--no-first-run','--disable-background-networking','--remote-debugging-pipe','--user-data-dir='+str(profile.resolve()),'about:blank'],pass_fds=tuple(set([to_read,from_write,3,4])),preexec_fn=setup,stdout=self.log,stderr=self.log)
  os.close(to_read);os.close(from_write)
  target=self.call('Target.createTarget',{'url':'about:blank'})['targetId'];self.session=self.call('Target.attachToTarget',{'targetId':target,'flatten':True})['sessionId']
  self.call('Fetch.enable',{'patterns':[{'urlPattern':'http://localhost:8000/*','requestStage':'Request'}]})
 def recv(self):
  while b'\x00' not in self.buffer:
   if not select.select([self.read_fd],[],[],60)[0]:raise TimeoutError('Chromium pipe response timeout')
   raw=os.read(self.read_fd,1048576)
   if not raw:raise RuntimeError('Chromium pipe disconnected')
   self.buffer+=raw
  raw,self.buffer=self.buffer.split(b'\x00',1);return json.loads(raw)
 def call(self,method,params=None):
  self.seq+=1;seq=self.seq;message={'id':seq,'method':method,'params':params or {}}
  if self.session:message['sessionId']=self.session
  os.write(self.write_fd,json.dumps(message).encode()+b'\x00')
  while True:
   if seq in self.pending:result=self.pending.pop(seq)
   else:result=self.recv()
   if result.get('method')=='Runtime.exceptionThrown':self.errors.append(result['params'])
   if result.get('method')=='Fetch.requestPaused':
    p=result['params'];request=p['request'];url=urlparse(request['url']);headers=request['headers'];headers['Host']=url.netloc
    code,response_headers,content=exchange(request['method'],url.path+('?' +url.query if url.query else ''),headers,request.get('postData','').encode())
    self.call('Fetch.fulfillRequest',{'requestId':p['requestId'],'responseCode':code,'responseHeaders':[{'name':k,'value':v} for k,v in response_headers],'body':base64.b64encode(content).decode()})
   if result.get('id')==seq:
    if 'error' in result:raise RuntimeError(result['error'])
    return result.get('result',{})
   if 'id' in result:self.pending[result['id']]=result
 def evaluate(self,expression):
  result=self.call('Runtime.evaluate',{'expression':expression,'awaitPromise':True,'returnByValue':True})
  if 'exceptionDetails' in result:raise AssertionError(result['exceptionDetails'])
  return result.get('result',{}).get('value')
 def wait(self,condition,timeout=12):
  end=time.time()+timeout
  while time.time()<end:
   if self.evaluate(condition):return
   time.sleep(.08)
  raise AssertionError('Browser wait timed out: '+condition+'; '+str(self.evaluate('document.body.innerText'))[:2000])
 def screenshot(self,path):
  data=self.call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False});Path(path).parent.mkdir(parents=True,exist_ok=True);Path(path).write_bytes(base64.b64decode(data['data']))
