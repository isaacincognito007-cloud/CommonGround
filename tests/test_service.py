"""API regression suite. Isaac Shiloah Herbert V · ISAAC.INCOGNITO007."""
import concurrent.futures, http.cookiejar, json, os, secrets, sqlite3, sys, tempfile, threading, unittest, urllib.error, urllib.request
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
PASSWORD=secrets.token_urlsafe(22)
class Client:
 def __init__(self,base):
  self.base=base; self.csrf=''; self.jar=http.cookiejar.CookieJar(); self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
 def request(self,path,body=None,key=None,csrf=True,origin=None,method=None):
  if os.environ.get('CG_TEST_TRANSPORT')=='socketpair':
   from transport import request
   return request(self,path,body,key,csrf,origin)
  headers={'Origin':origin or self.base}
  if body is not None: headers['Content-Type']='application/json'; headers['X-CSRF-Token']=self.csrf if csrf else ''
  if key: headers['Idempotency-Key']=key
  req=urllib.request.Request(self.base+'/api'+path, data=json.dumps(body).encode() if body is not None else None,headers=headers, method=method)
  try:
   with self.opener.open(req,timeout=15) as response: return response.status,json.load(response)
  except urllib.error.HTTPError as error: return error.code,json.load(error)
 def login(self,user='member',password=PASSWORD):
  code,result=self.request('/login',{'email':user+'@campus.example','password':password})
  if code==200: self.csrf=result['csrf']
  return code,result
class ServiceTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  server.Handler.log_message=lambda *a:None
  if os.environ.get('CG_TEST_TRANSPORT')=='socketpair':
   cls.http=None;cls.base='http://localhost:8000';return
  cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
  cls.base='http://127.0.0.1:'+str(cls.http.server_port)
  cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
 @classmethod
 def tearDownClass(cls):
  if cls.http:cls.http.shutdown();cls.http.server_close()
 def setUp(self):
  self.folder=tempfile.TemporaryDirectory(prefix='cg-test-',dir='.')
  server.DB=str(Path(self.folder.name)/'test.sqlite3');server.AUTH_ATTEMPTS.clear();os.environ['CG_SEED_PASSWORD']=PASSWORD;server.init_db(True)
  self.member=Client(self.base);self.member.login();self.owner=Client(self.base);self.owner.login('owner');self.admin=Client(self.base);self.admin.login('admin');self.new=Client(self.base);self.new.login('newcomer')
  self.day=date.fromisoformat(server.today())
 def tearDown(self):
        # Close any open database connections before cleanup
        import gc
        gc.collect()
        try:
            self.folder.cleanup()
        except Exception:
            # Ignore cleanup errors on Windows
            pass
 def body(self,start=0,end=1,rid='camera'): return {'resource_id':rid,'start':(self.day+timedelta(days=start)).isoformat(),'end':(self.day+timedelta(days=end)).isoformat(),'purpose':'Materials field research project'}
 def book(self,client=None,body=None,key=None):
  code,result=(client or self.member).request('/bookings',body or self.body(),key or secrets.token_hex(16));self.assertEqual(code,201,result);return result['booking']
 def action(self,b,action,client=None,**extra):return (client or self.owner).request('/bookings/'+b['id']+'/action',{'action':action,'note':'Reviewed with the campus equipment desk.',**extra})
 def count(self):
  with server.connect() as c:return c.execute('SELECT COUNT(*) FROM bookings').fetchone()[0]
 def verify(self): return self.admin.request('/users/newcomer/verify',{'verified':True,'credentials':['Workshop induction'],'reason':'Membership and induction register independently checked.'})
 def test_01_auth_login_failure_success_restore_logout(self):
  c=Client(self.base);self.assertEqual(c.request('/state')[0],401);self.assertEqual(c.login(password='wrong password')[0],401);self.assertEqual(c.login()[0],200);self.assertEqual(c.request('/session')[1]['user']['role'],'member');self.assertEqual(c.request('/state')[0],200)
  if os.environ.get('CG_TEST_TRANSPORT')=='socketpair':self.assertIn('HttpOnly',c.cookie_attributes)
  else:self.assertTrue(next(iter(c.jar)).has_nonstandard_attr('HttpOnly'))
  self.assertEqual(c.request('/logout',{})[0],200);self.assertEqual(c.request('/state')[0],401);self.assertEqual(c.login()[0],200)
 def test_02_expired_session(self):
  with server.connect() as c:c.execute("UPDATE sessions SET expires=0 WHERE user_id='member'")
  self.assertEqual(self.member.request('/state')[0],401)
 def test_03_invalid_dates_no_write(self):
  cases=[self.body(-1,1),self.body(1,0),self.body(0,0),self.body(0,8),{**self.body(),'start':'2007-01-01','end':'2008-01-01'},{**self.body(),'start':'2026-02-30'},{**self.body(),'start':'tomorrow'},{**self.body(),'end':''},{**self.body(),'start':None},{**self.body(),'end':17},{'resource_id':'camera','purpose':'Valid purpose text'}]
  for b in cases:
   with self.subTest(body=b):code,result=self.member.request('/bookings',b,secrets.token_hex(16));self.assertEqual(code,422,result);self.assertIn('field',result['error']);self.assertEqual(self.count(),0)
 def test_04_today_and_tomorrow_accepted(self):
  self.assertEqual(self.book()['status'],'Pending');self.assertEqual(self.book(body=self.body(1,2))['status'],'Pending')
 def test_05_idempotency_same_key_and_new_key(self):
  key=secrets.token_hex(16);b=self.book(key=key);code,res=self.member.request('/bookings',self.body(),key);self.assertEqual(code,200);self.assertEqual(res['booking']['id'],b['id']);self.assertTrue(res['replayed']);self.assertEqual(self.count(),1)
  self.assertEqual(self.member.request('/bookings',self.body(0,2),key)[0],409);self.assertEqual(self.member.request('/bookings',self.body(),secrets.token_hex(16))[0],409);self.assertEqual(self.count(),1)
 def test_06_concurrent_duplicate(self):
  key=secrets.token_hex(16)
  with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(lambda _:self.member.request('/bookings',self.body(),key),range(2)))
  self.assertEqual(sorted(x[0] for x in results),[200,201]);self.assertEqual(self.count(),1)
 def test_07_authorization_and_privacy(self):
  b=self.book();self.assertEqual(self.action(b,'approve',self.member)[0],403);self.assertEqual(self.action(b,'cancel',self.new)[0],403);self.assertEqual(self.new.request('/state')[1]['bookings'],[]);self.assertEqual(self.member.request('/state')[1]['people'],[])
  self.assertEqual(self.member.request('/resources',{})[0],403);self.assertEqual(self.owner.request('/users/newcomer/verify',{'verified':True,'credentials':[],'reason':'Evidence reviewed properly'})[0],403)
 def test_08_csrf_and_origin(self):
  self.assertEqual(self.member.request('/bookings',self.body(),secrets.token_hex(16),csrf=False)[0],403);self.assertEqual(self.member.request('/bookings',self.body(),secrets.token_hex(16),origin='https://foreign.invalid')[0],403);self.assertEqual(self.count(),0)
 def test_09_eligibility_and_human_review(self):
  b=self.book(self.new);self.assertEqual(b['status'],'Waitlisted');self.assertEqual(self.action(b,'approve')[1]['error']['code'],'not_eligible');self.assertEqual(self.verify()[0],200);self.assertEqual(self.action(b,'approve')[1]['booking']['status'],'Approved')
 def test_10_conflict_and_boundary(self):
  self.verify();b=self.book();self.assertEqual(self.action(b,'approve')[0],200);q=self.book(self.new);self.assertEqual(q['status'],'Waitlisted');self.assertEqual(self.action(q,'approve')[1]['error']['code'],'conflict');later=self.book(self.new,self.body(1,2));self.assertEqual(self.action(later,'approve')[0],200)
 def test_11_group_limit(self):
  self.book(body=self.body(0,1));self.book(body=self.body(2,3));b=self.book(body=self.body(4,5));self.assertEqual(b['status'],'Waitlisted');self.assertEqual(self.action(b,'approve')[1]['error']['code'],'fair_limit')
 def test_12_full_lifecycle_conditions_damage_resolution(self):
  b=self.book();self.assertEqual(self.action(b,'approve')[0],200);self.assertEqual(self.action(b,'check_in',self.member,note='Lens clear; tripod, charger and both batteries included.')[0],200)
  self.assertEqual(self.action(b,'incident',self.member,kind='Damage',note='Tripod latch became loose during use.')[0],200);self.assertEqual(self.action(b,'return',self.member,note='All accessories returned; loose latch documented.')[0],200);self.assertEqual(self.action(b,'confirm_return')[1]['error']['code'],'open_incident')
  record=self.member.request('/state')[1]['bookings'][0];self.assertEqual(self.action(b,'resolve',incident_id=record['incidents'][0]['id'],note='Latch tightened and inspected. No charge assessed.')[0],200);code,res=self.action(b,'confirm_return');self.assertEqual(code,200);self.assertEqual(res['booking']['status'],'Completed');self.assertIn('Lens clear',res['booking']['before_note']);self.assertEqual(len(res['booking']['history']),7)
 def test_13_invalid_transitions(self):
  b=self.book();self.assertEqual(self.action(b,'return',self.member)[0],409);self.assertEqual(self.action(b,'check_in',self.member)[0],409);self.action(b,'approve');self.action(b,'check_in',self.member);self.assertEqual(self.action(b,'cancel',self.member)[0],409)
 def test_14_extension_and_queue_protection(self):
  b=self.book();self.action(b,'approve');self.assertEqual(self.action(b,'extend',end=self.body(0,2)['end'])[0],200);self.verify();self.book(self.new,self.body(2,3));self.assertEqual(self.action(b,'extend',end=self.body(0,3)['end'])[1]['error']['code'],'queue_protected')
 def test_15_append_only_audit(self):
  self.book()
  with server.connect() as c:
   with self.assertRaises(sqlite3.IntegrityError):c.execute('DELETE FROM activity')
   with self.assertRaises(sqlite3.IntegrityError):c.execute("UPDATE activity SET detail='changed'")
 def test_16_resource_listing_and_full_journey(self):
  body={'name':'Portable audio kit','category':'Photography','location':'Media equipment desk','description':'A recorder with two microphones and a padded case.','rules':'Collect and return all labelled cables and batteries.','training':'Workshop induction','available_from':self.body()['start'],'available_to':self.body(0,30)['end']}
  code,res=self.owner.request('/resources',body);self.assertEqual(code,201);b=self.book(body=self.body(rid=res['id']));self.action(b,'approve');self.action(b,'check_in',self.member);self.action(b,'return',self.member);self.assertEqual(self.action(b,'confirm_return')[1]['booking']['status'],'Completed')
 def test_17_cancel_reject_and_notifications(self):
  b=self.book();self.assertEqual(self.action(b,'cancel',self.member)[1]['booking']['status'],'Cancelled');b=self.book();self.assertEqual(self.action(b,'reject')[1]['booking']['status'],'Rejected');self.assertGreaterEqual(len(self.member.request('/state')[1]['notifications']),4)
 def test_18_password_revokes_sessions(self):
  new=secrets.token_urlsafe(25);code,res=self.member.request('/password',{'current_password':PASSWORD,'new_password':new});self.assertEqual(code,200);self.assertEqual(self.member.request('/session')[0],401);self.assertEqual(self.member.login(password=new)[0],200)
 def test_19_training_revoked_before_collection(self):
  b=self.book();self.action(b,'approve');self.admin.request('/users/member/verify',{'verified':False,'credentials':[],'reason':'Membership access suspended after staff review.'});self.assertEqual(self.action(b,'check_in',self.member)[1]['error']['code'],'not_eligible')
 def test_20_manager_scope(self):
  m=Client(self.base);m.login('manager');b=self.book();self.assertEqual(self.action(b,'approve',m)[0],200)
  body={'name':'Private tool kit','category':'Research','location':'Owner equipment desk','description':'A manually inspected portable tool kit.','rules':'Collect all accessories and follow the safety checklist.','training':'','available_from':self.body()['start'],'available_to':self.body(0,30)['end']};rid=self.owner.request('/resources',body)[1]['id'];b=self.book(body=self.body(rid=rid));self.assertEqual(self.action(b,'approve',m)[0],403);self.assertEqual(self.action(b,'assign_manager',manager_id='manager')[0],200);self.assertEqual(self.action(b,'approve',m)[0],200)
 def test_21_queue_fifo_enforced(self):
  self.verify();a=self.book(self.new);self.action(a,'waitlist');b=self.book();self.assertEqual(self.action(b,'approve')[1]['error']['code'],'queue_order');self.assertEqual(self.action(a,'approve')[0],200)
 def test_22_outside_window_and_required_fields(self):
  code,res=self.member.request('/bookings',self.body(181,182),secrets.token_hex(16));self.assertEqual(code,409);self.assertEqual(self.member.request('/bookings',{**self.body(),'purpose':''},secrets.token_hex(16))[0],422);self.assertEqual(self.member.request('/bookings',self.body())[0],400);self.assertEqual(self.count(),0)
 def test_23_overlapping_pending_request_is_waitlisted(self):
  first=self.book()
  second=self.book(self.new)
  self.assertEqual(second['status'],'Waitlisted')
  self.assertIn('another active request',second['reason'])
  self.verify()
  self.assertEqual(self.action(first,'approve')[0],200)
  self.assertEqual(self.action(second,'approve')[1]['error']['code'],'conflict')
  self.assertEqual(self.action(first,'cancel',self.member)[0],200)
  self.assertEqual(self.action(second,'approve')[1]['booking']['status'],'Approved')
 if __name__=='__main__':unittest.main(verbosity=2)

class VerificationWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.Handler.log_message=lambda *a:None
        cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        cls.base='http://127.0.0.1:'+str(cls.http.server_port)
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close()
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory(prefix='cg-test-',dir='.')
        server.DB=str(Path(self.folder.name)/'test.sqlite3');server.AUTH_ATTEMPTS.clear();os.environ['CG_SEED_PASSWORD']=PASSWORD;server.init_db(True)
        self.member=Client(self.base);self.member.login();self.owner=Client(self.base);self.owner.login('owner');self.admin=Client(self.base);self.admin.login('admin');self.manager=Client(self.base);self.manager.login('manager');self.new=Client(self.base);self.new.login('newcomer')
        self.day=date.fromisoformat(server.today())
    def tearDown(self):
        import gc
        gc.collect()
        try:
            self.folder.cleanup()
        except Exception:
            pass
    def test_verification_request_user(self):
        code,res=self.member.request('/verification/request',{'target_type':'user','target_id':'member','note':'verify me'})
        self.assertEqual(code,200)
        code,res=self.member.request('/verification/request',{'target_type':'user','target_id':'member'})
        self.assertEqual(code,409)  # already pending
    def test_verification_request_user_other(self):
        code,res=self.member.request('/verification/request',{'target_type':'user','target_id':'newcomer'})
        self.assertEqual(code,403)  # can only request for self
    def test_verification_request_resource(self):
        code,res=self.owner.request('/verification/request',{'target_type':'resource','target_id':'camera','note':'verify camera'})
        self.assertEqual(code,200)
        code,res=self.member.request('/verification/request',{'target_type':'resource','target_id':'camera'})
        self.assertEqual(code,403)  # not owner
    def test_verification_request_resource_already_verified(self):
        code,res=self.admin.request('/verification/request',{'target_type':'resource','target_id':'camera'})
        self.assertEqual(code,200)
        # Approve it
        code,res=self.admin.request('/admin/verify',{'target_type':'resource','target_id':'camera','decision':'approve','reason':'OK'},csrf=True,origin=self.base,method='PATCH')
        self.assertEqual(code,200)
        code,res=self.owner.request('/verification/request',{'target_type':'resource','target_id':'camera'})
        self.assertEqual(code,409)  # already verified
    def test_admin_verifications_queue(self):
        self.member.request('/verification/request',{'target_type':'user','target_id':'member','note':'verify me'})
        self.owner.request('/verification/request',{'target_type':'resource','target_id':'camera','note':'verify camera'})
        code,res=self.admin.request('/admin/verifications')
        self.assertEqual(code,200)
        self.assertEqual(len(res['users']),1)
        self.assertEqual(len(res['resources']),1)
        code,res=self.member.request('/admin/verifications')
        self.assertEqual(code,403)  # member cannot view
    def test_admin_verify_approve_user(self):
        self.member.request('/verification/request',{'target_type':'user','target_id':'member'})
        code,res=self.admin.request('/admin/verify',{'target_type':'user','target_id':'member','decision':'approve','reason':'verified ok'},method='PATCH')
        self.assertEqual(code,200)
        # Verify status changed
        with server.connect() as c:
            row=c.execute('SELECT verification_status FROM users WHERE id="member"').fetchone()
            self.assertEqual(row['verification_status'],'verified')
    def test_admin_verify_reject_user(self):
        self.member.request('/verification/request',{'target_type':'user','target_id':'member'})
        code,res=self.admin.request('/admin/verify',{'target_type':'user','target_id':'member','decision':'reject','reason':'missing docs'},method='PATCH')
        self.assertEqual(code,200)
        with server.connect() as c:
            row=c.execute('SELECT verification_status FROM users WHERE id="member"').fetchone()
            self.assertEqual(row['verification_status'],'rejected')
    def test_admin_verify_reject_no_reason(self):
        self.member.request('/verification/request',{'target_type':'user','target_id':'member'})
        code,res=self.admin.request('/admin/verify',{'target_type':'user','target_id':'member','decision':'reject','reason':''},method='PATCH')
        self.assertEqual(code,422)
        self.assertEqual(res['error']['code'],'invalid_field')
    def test_admin_verify_self_user(self):
        code,res=self.admin.request('/admin/verify',{'target_type':'user','target_id':'admin','decision':'approve','reason':'self'},method='PATCH')
        self.assertEqual(code,403)
        self.assertEqual(res['error']['code'],'self_verify')
    def test_admin_verify_own_resource(self):
        # owner requests, admin (who is also owner) tries to approve
        body={'name':'Test resource','category':'Test','location':'Test','description':'Test resource for self verify','rules':'Test rules','training':'','available_from':self.day.isoformat(),'available_to':(self.day+timedelta(days=30)).isoformat()}
        code,res=self.owner.request('/resources',body)
        self.assertEqual(code,201)
        rid=res['id']
        self.owner.request('/verification/request',{'target_type':'resource','target_id':rid})
        code,res=self.owner.request('/admin/verify',{'target_type':'resource','target_id':rid,'decision':'approve','reason':'self'},method='PATCH')
        self.assertEqual(code,403)
        self.assertEqual(res['error']['code'],'self_verify')
    def test_manager_verify_own_managed_resource(self):
        # Create resource, assign manager
        body={'name':'Managed resource','category':'Test','location':'Test','description':'Test','rules':'Test','training':'','available_from':self.day.isoformat(),'available_to':(self.day+timedelta(days=30)).isoformat()}
        code,res=self.owner.request('/resources',body)
        self.assertEqual(code,201)
        rid=res['id']
        self.owner.request('/bookings/'+rid+'/action',{'action':'assign_manager','manager_id':'manager'})
        self.owner.request('/verification/request',{'target_type':'resource','target_id':rid})
        code,res=self.manager.request('/admin/verify',{'target_type':'resource','target_id':rid,'decision':'approve','reason':'self'},method='PATCH')
        self.assertEqual(code,403)
        self.assertEqual(res['error']['code'],'self_verify')
    def test_verification_history(self):
        self.member.request('/verification/request',{'target_type':'user','target_id':'member'})
        self.admin.request('/admin/verify',{'target_type':'user','target_id':'member','decision':'approve','reason':'OK'},method='PATCH')
        code,res=self.member.request('/verification/history?target_type=user&target_id=member')
        self.assertEqual(code,200)
        self.assertEqual(len(res['history']),2)  # request + approve
        code,res=self.new.request('/verification/history?target_type=user&target_id=member')
        self.assertEqual(code,403)  # other user cannot view
    def test_notifications(self):
        self.member.request('/verification/request',{'target_type':'user','target_id':'member'})
        code,res=self.member.request('/notifications')
        self.assertEqual(code,200)
        self.assertEqual(res['unread_count'],1)
        # Mark as read
        code,res=self.member.request('/notifications/read',{'all':True},method='POST')
        self.assertEqual(code,200)
        code,res=self.member.request('/notifications')
        self.assertEqual(res['unread_count'],0)
    def test_notifications_own_only(self):
        # Admin creates notification for member by approving
        self.member.request('/verification/request',{'target_type':'user','target_id':'member'})
        self.admin.request('/admin/verify',{'target_type':'user','target_id':'member','decision':'approve','reason':'OK'},method='PATCH')
        code,res=self.member.request('/notifications')
        self.assertEqual(code,200)
        self.assertEqual(res['unread_count'],1)
        # Admin cannot read member's notifications
        code,res=self.admin.request('/notifications')
        self.assertEqual(code,200)
        self.assertEqual(res['unread_count'],0)  # admin has own, not member's
    def test_patch_resource_mass_assignment(self):
        body={'name':'Test resource','category':'Test','location':'Test','description':'Test','rules':'Test','training':'','available_from':self.day.isoformat(),'available_to':(self.day+timedelta(days=30)).isoformat()}
        code,res=self.owner.request('/resources',body)
        self.assertEqual(code,201)
        rid=res['id']
        # Try to inject forbidden fields
        code,res=self.owner.request('/resources/'+rid,{'verification_status':'verified','role':'admin'},method='PATCH')
        self.assertEqual(code,200)
        with server.connect() as c:
            row=c.execute('SELECT verification_status FROM resources WHERE id=?',(rid,)).fetchone()
            self.assertEqual(row['verification_status'],'unverified')  # unchanged
    def test_patch_verified_resource_resets(self):
        body={'name':'Test resource','category':'Test','location':'Test','description':'Test','rules':'Test','training':'','available_from':self.day.isoformat(),'available_to':(self.day+timedelta(days=30)).isoformat()}
        code,res=self.owner.request('/resources',body)
        self.assertEqual(code,201)
        rid=res['id']
        # Approve it
        self.owner.request('/verification/request',{'target_type':'resource','target_id':rid})
        self.admin.request('/admin/verify',{'target_type':'resource','target_id':rid,'decision':'approve','reason':'OK'},method='PATCH')
        # Now patch it
        code,res=self.owner.request('/resources/'+rid,{'name':'New name'},method='PATCH')
        self.assertEqual(code,200)
        with server.connect() as c:
            row=c.execute('SELECT verification_status FROM resources WHERE id=?',(rid,)).fetchone()
            self.assertEqual(row['verification_status'],'unverified')  # reset
    def test_assign_manager_self_assign(self):
        body={'name':'Test resource','category':'Test','location':'Test','description':'Test','rules':'Test','training':'','available_from':self.day.isoformat(),'available_to':(self.day+timedelta(days=30)).isoformat()}
        code,res=self.owner.request('/resources',body)
        self.assertEqual(code,201)
        rid=res['id']
        code,res=self.manager.request('/bookings/'+rid+'/action',{'action':'assign_manager','manager_id':'manager'})
        self.assertEqual(code,403)
        self.assertEqual(res['error']['code'],'self_assign')
