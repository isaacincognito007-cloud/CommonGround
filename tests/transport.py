"""HTTP transport for isolated test environments. Not used by the application.
Isaac Shiloah Herbert V · ISAAC.INCOGNITO007.
"""
import http.client, json, socket, threading
from http.cookies import SimpleCookie
import server

def exchange(method,path,headers,body=b''):
 client,peer=socket.socketpair()
 headers={**headers,'Connection':'close','Content-Length':str(len(body))}
 class Context:server_name='localhost';server_port=8000
 errors=[]
 def serve():
  try:server.Handler(peer,('127.0.0.1',0),Context())
  except Exception as e:errors.append(e)
  finally:peer.close()
 worker=threading.Thread(target=serve,daemon=True);worker.start()
 request=f'{method} {path} HTTP/1.1\r\n'+''.join(f'{k}: {v}\r\n' for k,v in headers.items())+'\r\n'
 client.sendall(request.encode()+body)
 response=http.client.HTTPResponse(client);response.begin();status=response.status;result_headers=response.getheaders();content=response.read();response.close();client.close();worker.join(5)
 if errors:raise errors[0]
 return status,result_headers,content

def request(client,path,body,key,csrf,origin):
 headers={'Host':'localhost:8000','Origin':origin or client.base}
 if getattr(client,'cookie',''):headers['Cookie']=client.cookie
 if body is not None:headers.update({'Content-Type':'application/json','X-CSRF-Token':client.csrf if csrf else ''})
 if key:headers['Idempotency-Key']=key
 status,result_headers,content=exchange('POST' if body is not None else 'GET','/api'+path,headers,json.dumps(body).encode() if body is not None else b'')
 for name,value in result_headers:
  if name.lower()=='set-cookie':
   cookie=SimpleCookie();cookie.load(value);client.cookie='; '.join(f'{k}={v.value}' for k,v in cookie.items())
   client.cookie_attributes=value
 return status,json.loads(content)
