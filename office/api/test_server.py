import base64, importlib.util, json, os, tempfile, threading, unittest, urllib.error, urllib.parse, urllib.request, uuid
from pathlib import Path

class PortalTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();os.environ.update(DATA_DIR=cls.tmp.name,PUBLIC_ORIGIN='http://test.local',COOKIE_SECURE='0')
  spec=importlib.util.spec_from_file_location('portal_api',Path(__file__).with_name('server.py'));cls.mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.mod)
  cls.server=cls.mod.ThreadingHTTPServer(('127.0.0.1',0),cls.mod.Handler);cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start();cls.base='http://127.0.0.1:'+str(cls.server.server_port)
  code=(Path(cls.tmp.name)/'setup-code').read_text();r,cls.admin=cls.call('POST','/api/auth/setup',{'code':code,'username':'admin','name':'Office Leitung','password':'test-password-12345'})
  cls.dealer,cls.dealer_id=cls.account('dealer','Autohaus A','dealer-a');cls.other,cls.other_id=cls.account('dealer','Autohaus B','dealer-b');cls.driver,cls.driver_id=cls.account('driver','Fahrer A','driver-a');cls.driver_b,cls.driver_b_id=cls.account('driver','Fahrer B','driver-b');cls.office,cls.office_id=cls.account('office','Office A','office-a')
 @classmethod
 def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.tmp.cleanup()
 @classmethod
 def call(cls,method,path,body=None,cookie=None,expect=200,headers=None):
  h={'Origin':'http://test.local'}
  if cookie:h['Cookie']=cookie
  if isinstance(body,dict):body=json.dumps(body).encode();h['Content-Type']='application/json'
  if headers:h.update(headers)
  req=urllib.request.Request(cls.base+path,data=body,method=method,headers=h)
  try:r=urllib.request.urlopen(req,timeout=10)
  except urllib.error.HTTPError as e:r=e
  data=r.read();status=r.status;ck=r.headers.get('Set-Cookie','').split(';')[0] or cookie
  if r.headers.get_content_type()=='application/json':data=json.loads(data)
  if status!=expect:raise AssertionError((method,path,status,expect,data))
  return data,ck
 @classmethod
 def account(cls,role,name,username):
  r,_=cls.call('POST','/api/users',{'role':role,'name':name},cls.admin,201);token=urllib.parse.parse_qs(urllib.parse.urlparse(r['invitation']).query)['einladung'][0]
  a,c=cls.call('POST','/api/auth/accept-invite',{'token':token,'username':username,'password':'test-password-12345'},expect=200);return c,a['user']['id']
 def order(self,cookie=None):
  r,_=self.call('POST','/api/orders',{'vehicle':'VW Golf','type':'Neuzulassung','plate':'FB A 123','form':{'street':'Teststraße 1','city':'Friedberg'}},cookie or self.dealer,201);return r
 def snapshot(self,cookie):return self.call('GET','/api/snapshot',cookie=cookie)[0]
 def assign(self,order,kind='Abholung',driver=None):
  return self.call('POST','/api/orders/'+order['id']+'/assign',{'driverId':driver or self.driver_id,'type':kind,'address':'Teststraße 1, Friedberg','tour':1,'date':'2026-10-19','time':'10:00'},self.admin,201)[0]
 def test_01_auth_and_origin(self):
  self.call('GET','/api/snapshot',expect=401)
  self.call('POST','/api/orders',{'vehicle':'Test'},self.dealer,403,{'Origin':'https://evil.invalid'})
  self.call('POST','/api/auth/setup',{'code':'wrong','username':'x','password':'not-valid'},expect=409)
  self.assertFalse((Path(self.tmp.name)/'setup-code').exists())
 def test_02_tenant_isolation_and_fields(self):
  o=self.order();self.assertTrue(any(x['id']==o['id'] for x in self.snapshot(self.admin)['orders']));self.assertFalse(any(x['id']==o['id'] for x in self.snapshot(self.other)['orders']));self.assertFalse(any(x['id']==o['id'] for x in self.snapshot(self.driver)['orders']))
  self.call('PATCH','/api/orders/'+o['id'],{'patch':{'plate':'X'},'expectedVersion':1},self.other,403)
  self.call('PATCH','/api/orders/'+o['id'],{'patch':{'status':'Fertig'},'expectedVersion':1},self.dealer,403)
  self.call('PATCH','/api/orders/'+o['id'],{'patch':{'dealerId':self.other_id},'expectedVersion':1},self.dealer,403)
 def test_03_status_and_version_conflict(self):
  o=self.order();updated,_=self.call('PATCH','/api/orders/'+o['id'],{'patch':{'status':'Bei Behörde'},'expectedVersion':1},self.office);self.assertEqual(updated['status'],'Bei Behörde')
  self.call('PATCH','/api/orders/'+o['id'],{'patch':{'plate':'FB B 222'},'expectedVersion':1},self.office,409)
  visible=next(x for x in self.snapshot(self.dealer)['orders'] if x['id']==o['id']);self.assertEqual(visible['status'],'Bei Behörde')
 def test_04_driver_assignment_and_collection(self):
  o=self.order();self.call('POST','/api/orders/'+o['id']+'/assign',{'driverId':self.driver_id},self.dealer,403)
  task=self.assign(o);self.assertTrue(any(t['id']==task['id'] for t in self.snapshot(self.driver)['stops']));self.assertFalse(any(t['id']==task['id'] for t in self.snapshot(self.driver_b)['stops']));self.assertTrue(any(t['id']==task['id'] for t in self.snapshot(self.dealer)['stops']))
  self.call('PATCH','/api/stops/'+task['id'],{'patch':{'status':'Erledigt'},'expectedVersion':1},self.driver_b,403)
  self.call('PATCH','/api/stops/'+task['id'],{'patch':{'status':'Erledigt'},'expectedVersion':1},self.driver)
  self.assertEqual(next(x for x in self.snapshot(self.dealer)['orders'] if x['id']==o['id'])['status'],'Abgeholt')
 def test_05_document_upload_access_and_review(self):
  o=self.order();payload=b'%PDF-1.4\nTest document\n';f,_=self.call('POST','/api/files',payload,self.dealer,201,{'Content-Type':'application/pdf','X-File-Name':'Vollmacht.pdf','X-Order-Id':o['id']})
  self.assertTrue(any(x['id']==f['id'] for x in self.snapshot(self.admin)['files']));self.call('GET',f['url'],cookie=self.other,expect=403);raw,_=self.call('GET',f['url'],cookie=self.dealer);self.assertEqual(raw,payload)
  self.call('PATCH','/api/files/'+f['id'],{'patch':{'status':'Freigegeben'},'expectedVersion':1},self.dealer,403)
  self.call('PATCH','/api/files/'+f['id'],{'patch':{'status':'Freigegeben'},'expectedVersion':1},self.office)
  self.assertEqual(next(x for x in self.snapshot(self.dealer)['files'] if x['id']==f['id'])['status'],'Freigegeben')
  self.call('POST','/api/files',b'<script>bad</script>',self.dealer,400,{'Content-Type':'application/pdf','X-File-Name':'fake.pdf','X-Order-Id':o['id']})
 def test_06_return_requires_real_bound_proof_and_signature(self):
  o=self.order();task=self.assign(o,'Übergabe');h=next(h for h in self.snapshot(self.driver)['handovers'] if h['taskId']==task['id'])
  self.call('PATCH','/api/stops/'+task['id'],{'patch':{'status':'Erledigt'},'expectedVersion':1},self.driver,409)
  self.call('PATCH','/api/handovers/'+h['id'],{'patch':{'status':'Bestätigt','items':['Kennzeichen'],'recipient':'Empfänger','signature':'bad'},'expectedVersion':1},self.driver,400)
  png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jX1kAAAAASUVORK5CYII=');f,_=self.call('POST','/api/files',png,self.driver,201,{'Content-Type':'image/png','X-File-Name':'proof.png','X-Order-Id':o['id'],'X-Task-Id':task['id'],'X-Purpose':'proof'})
  self.call('GET',f['url'],cookie=self.dealer,expect=403)
  sig='data:image/png;base64,'+base64.b64encode(png).decode();self.call('PATCH','/api/handovers/'+h['id'],{'patch':{'status':'Bestätigt','items':['Kennzeichen'],'recipient':'Empfänger','signature':sig,'photoId':f['id']},'expectedVersion':1},self.driver)
  self.call('PATCH','/api/stops/'+task['id'],{'patch':{'status':'Erledigt'},'expectedVersion':1},self.driver)
  self.assertEqual(next(x for x in self.snapshot(self.dealer)['orders'] if x['id']==o['id'])['status'],'Ausgeliefert')
 def test_07_private_preferences_and_notifications(self):
  self.call('PUT','/api/state/tariq-profile',{'value':{'name':'A'},'expectedVersion':0},self.dealer)
  self.assertNotIn('tariq-profile',self.snapshot(self.other)['states'])
  self.call('PUT','/api/state/tariq-profile',{'value':{'name':'B'},'expectedVersion':0},self.dealer,409)
  o=self.order();self.call('PATCH','/api/orders/'+o['id'],{'patch':{'status':'In Prüfung'},'expectedVersion':1},self.office)
  events=[e for e in self.snapshot(self.dealer)['events'] if e['order_id']==o['id']];event=events[0];self.assertFalse(event['read']);self.call('POST','/api/events/'+str(event['id'])+'/read',{},self.dealer);self.assertTrue(next(e for e in self.snapshot(self.dealer)['events'] if e['id']==event['id'])['read'])
 def test_08_pickup_request_and_duplicate_assignment(self):
  o=self.order();self.call('POST','/api/orders/'+o['id']+'/pickup-request',{'address':'Straße 1','date':'2026-10-20','time':'10:00','expectedVersion':1},self.dealer)
  self.assertEqual(next(x for x in self.snapshot(self.admin)['orders'] if x['id']==o['id'])['pickupRequest']['status'],'Angefragt')
  self.assign(o);self.call('POST','/api/orders/'+o['id']+'/assign',{'driverId':self.driver_id,'type':'Abholung','address':'Straße 1'},self.admin,409)
 def test_09_login_logout(self):
  _,cookie=self.call('POST','/api/auth/login',{'username':'dealer-a','password':'test-password-12345'});self.call('POST','/api/auth/logout',{},cookie);self.call('GET','/api/snapshot',cookie=cookie,expect=401)

 def test_10_pickup_on_creation_and_input_validation(self):
  o,_=self.call('POST','/api/orders',{'vehicle':'Test Auto','type':'Ummeldung','form':{'pickupDate':'2026-10-20','pickupTime':'11:00','street':'Teststraße 2','city':'Teststadt'}},self.dealer,201)
  self.assertEqual(o['pickupRequest']['status'],'Angefragt')
  self.assertEqual(o['pickupRequest']['time'],'11:00')
  self.call('PATCH','/api/orders/'+o['id'],{'patch':{'vehicle':{'unexpected':'object'}},'expectedVersion':1},self.office,400)
  self.call('POST','/api/orders',{'vehicle':'Test','type':['invalid']},self.dealer,400)
 def test_11_database_survives_server_restart(self):
  o=self.order();self.server.shutdown();self.server.server_close()
  type(self).server=self.mod.ThreadingHTTPServer(('127.0.0.1',0),self.mod.Handler)
  type(self).thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();type(self).base='http://127.0.0.1:'+str(self.server.server_port)
  self.assertTrue(any(x['id']==o['id'] for x in self.snapshot(self.admin)['orders']))
  self.assertFalse((Path(self.tmp.name)/'setup-code').exists())

if __name__=='__main__':unittest.main()
