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
  o=self.order();updated,_=self.call('PATCH','/api/orders/'+o['id'],{'patch':{'status':'In Prüfung'},'expectedVersion':1},self.office);self.assertEqual(updated['status'],'In Prüfung')
  self.call('PATCH','/api/orders/'+o['id'],{'patch':{'plate':'FB B 222'},'expectedVersion':1},self.office,409)
  visible=next(x for x in self.snapshot(self.dealer)['orders'] if x['id']==o['id']);self.assertEqual(visible['status'],'In Prüfung')
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

 def authority_config(self,name=None,mode='Termin',limit=None):
  name=name or 'Teststelle-'+uuid.uuid4().hex[:8]
  return self.call('PUT','/api/authorities',{'name':name,'mode':mode,'weeklyMinimum':20,'weeklyLimit':limit,'expectedVersion':0},self.office)[0]
 def visit(self,config,orders,day=None,clock='09:00',expect=201):
  return self.call('POST','/api/authority-visits',{'authorityId':config['id'],'kind':config['mode'],'orderIds':[o['id'] for o in orders],'date':day or self.mod.date.today().isoformat(),'time':clock,'confirmation':'REF-123','note':'Testnotiz','address':'Testschalter'},self.office,expect)[0]
 def current_order(self,oid):return next(o for o in self.snapshot(self.admin)['orders'] if o['id']==oid)
 def order_status(self,oid,status):
  o=self.current_order(oid)
  return self.call('PATCH','/api/orders/'+oid,{'expectedVersion':o['_version'],'patch':{'status':status}},self.office)[0]
 def counter(self,config,day=None):
  q=urllib.parse.urlencode({'id':config['id'],'date':day or self.mod.date.today().isoformat()})
  return self.call('GET','/api/authorities/counter?'+q,cookie=self.office)[0]
 def test_12_appointment_links_edit_cancel_and_acl(self):
  config=self.authority_config();o=self.order();v=self.visit(config,[o]);linked=self.current_order(o['id']);self.assertEqual(linked['authorityVisit']['id'],v['id'])
  self.assertTrue(any(x['id']==v['id'] for x in self.snapshot(self.admin)['authorityVisits']))
  for cookie in [self.dealer,self.driver]:
   snap=self.snapshot(cookie);self.assertEqual(snap['authorityVisits'],[]);self.assertEqual(snap['authorities'],[])
   self.call('POST','/api/authority-visits',{},cookie,403)
   self.call('PUT','/api/authorities',{},cookie,403)
   self.call('PATCH','/api/authority-visits/'+v['id'],{'action':'cancel','expectedVersion':1},cookie,403)
  self.visit(config,[o],clock='11:00',expect=409)
  self.call('PATCH','/api/orders/'+o['id'],{'patch':{'office':'Andere Stelle'},'expectedVersion':linked['_version']},self.dealer,409)
  v,_=self.call('PATCH','/api/authority-visits/'+v['id'],{'action':'update','patch':{'time':'10:30','confirmation':'NEW-REF'},'expectedVersion':1},self.office)
  self.assertEqual(self.current_order(o['id'])['authorityVisit']['time'],'10:30')
  self.call('PATCH','/api/authority-visits/'+v['id'],{'action':'cancel','expectedVersion':1},self.office,409)
  self.call('PATCH','/api/authority-visits/'+v['id'],{'action':'cancel','expectedVersion':2},self.office)
  self.assertNotIn('authorityVisit',self.current_order(o['id']));self.assertEqual(self.counter(config)['submitted'],0)
 def test_13_minimum_is_not_a_limit_and_submission_statuses(self):
  config=self.authority_config(mode='Händlerschalter');orders=[self.order() for _ in range(21)];v=self.visit(config,orders)
  count=self.counter(config);self.assertEqual((count['submitted'],count['reserved'],count['remainingMinimum'],count['remainingCapacity']),(0,21,20,None))
  self.call('PATCH','/api/authority-visits/'+v['id'],{'action':'submit','expectedVersion':1},self.office,409)
  for o in orders:self.order_status(o['id'],'Vollständig geprüft')
  self.call('PATCH','/api/authority-visits/'+v['id'],{'action':'submit','expectedVersion':1},self.office)
  count=self.counter(config);self.assertEqual((count['submitted'],count['reserved'],count['remainingMinimum']),(21,0,0))
  o=self.current_order(orders[0]['id']);self.assertEqual(o['status'],'Bei Behörde');self.assertIn('authoritySubmittedAt',o)
  self.order_status(o['id'],'Fertig');self.order_status(o['id'],'Unterlagen zurück im Office')
  self.assertEqual(self.current_order(o['id'])['status'],'Unterlagen zurück im Office')
  self.call('PATCH','/api/authority-visits/'+v['id'],{'action':'cancel','expectedVersion':2},self.office,409)
  nextweek=(self.mod.date.fromisoformat(count['week'])+self.mod.timedelta(days=7)).isoformat();self.assertEqual(self.counter(config,nextweek)['submitted'],0)
 def test_14_capacity_cancel_and_atomic_reservations(self):
  config=self.authority_config(mode='Händlerschalter',limit=20);orders=[self.order() for _ in range(21)];v=self.visit(config,orders[:19]);self.assertEqual(self.counter(config)['remainingCapacity'],1)
  from concurrent.futures import ThreadPoolExecutor
  def race(order):
   b={'authorityId':config['id'],'kind':config['mode'],'orderIds':[order['id']],'date':self.mod.date.today().isoformat(),'time':'10:00'}
   req=urllib.request.Request(self.base+'/api/authority-visits',data=json.dumps(b).encode(),method='POST',headers={'Origin':'http://test.local','Cookie':self.office,'Content-Type':'application/json'})
   try:r=urllib.request.urlopen(req)
   except urllib.error.HTTPError as e:r=e
   r.read();return r.status
  with ThreadPoolExecutor(max_workers=2) as pool:statuses=sorted(pool.map(race,orders[19:]))
  self.assertEqual(statuses,[201,409]);self.assertEqual(self.counter(config)['remainingCapacity'],0)
  self.call('PATCH','/api/authority-visits/'+v['id'],{'action':'cancel','expectedVersion':1},self.office);self.assertEqual(self.counter(config)['remainingCapacity'],19)
 def test_15_modes_cannot_be_mixed(self):
  config=self.authority_config();o=self.order();v=self.visit(config,[o]);body={**config,'mode':'Händlerschalter','expectedVersion':1}
  self.call('PUT','/api/authorities',body,self.office,409)
  self.order_status(o['id'],'Vollständig geprüft');self.call('PATCH','/api/authority-visits/'+v['id'],{'action':'submit','expectedVersion':1},self.office)
  config,_=self.call('PUT','/api/authorities',body,self.office);other=self.order();self.visit(config,[other],expect=409)
  nextweek=(self.mod.date.fromisoformat(self.mod.authority_week(self.mod.date.today().isoformat()))+self.mod.timedelta(days=7)).isoformat()
  self.visit(config,[other],day=nextweek)
 def test_16_quality_dates_and_document_changes(self):
  config=self.authority_config();o=self.order();tomorrow=(self.mod.date.today()+self.mod.timedelta(days=1)).isoformat();v=self.visit(config,[o],day=tomorrow)
  self.call('PATCH','/api/authority-visits/'+v['id'],{'action':'submit','expectedVersion':1},self.office,409)
  self.call('PATCH','/api/authority-visits/'+v['id'],{'action':'update','patch':{'date':'2026-02-30'},'expectedVersion':1},self.office,400)
  v,_=self.call('PATCH','/api/authority-visits/'+v['id'],{'action':'update','patch':{'date':self.mod.date.today().isoformat()},'expectedVersion':1},self.office)
  self.order_status(o['id'],'Vollständig geprüft')
  f,_=self.call('POST','/api/files',b'%PDF-1.4 Test',self.dealer,201,{'Content-Type':'application/pdf','X-Order-Id':o['id']})
  self.assertEqual(self.current_order(o['id'])['status'],'In Prüfung')
  self.call('PATCH','/api/authority-visits/'+v['id'],{'action':'submit','expectedVersion':2},self.office,409)
  current=self.current_order(o['id']);self.call('PATCH','/api/orders/'+o['id'],{'patch':{'status':'Vollständig geprüft'},'expectedVersion':current['_version']},self.office,409)
  self.call('PATCH','/api/files/'+f['id'],{'patch':{'status':'Freigegeben'},'expectedVersion':1},self.office)
  self.order_status(o['id'],'Vollständig geprüft');self.call('PATCH','/api/authority-visits/'+v['id'],{'action':'submit','expectedVersion':2},self.office)
 def test_17_collection_retries_preserve_later_workflow(self):
  o=self.order();task=self.assign(o)
  self.call('PATCH','/api/stops/'+task['id'],{'patch':{'status':'Erledigt'},'expectedVersion':1},self.driver)
  self.order_status(o['id'],'Vollständig geprüft')
  self.call('PATCH','/api/stops/'+task['id'],{'patch':{'status':'Erledigt'},'expectedVersion':2},self.driver)
  self.assertEqual(self.current_order(o['id'])['status'],'Vollständig geprüft')
 def test_18_persist_authority_plan_after_restart(self):
  config=self.authority_config();o=self.order();v=self.visit(config,[o]);self.server.shutdown();self.server.server_close()
  type(self).server=self.mod.ThreadingHTTPServer(('127.0.0.1',0),self.mod.Handler);type(self).thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();type(self).base='http://127.0.0.1:'+str(self.server.server_port)
  snap=self.snapshot(self.office);self.assertTrue(any(x['id']==config['id'] for x in snap['authorities']));self.assertTrue(any(x['id']==v['id'] for x in snap['authorityVisits']));self.assertEqual(self.current_order(o['id'])['authorityVisit']['time'],'09:00')

 def test_19_delayed_submission_counts_actual_week(self):
  config=self.authority_config(mode='Händlerschalter');o=self.order();thisweek=self.mod.date.fromisoformat(self.mod.authority_week(self.mod.date.today().isoformat()));lastweek=(thisweek-self.mod.timedelta(days=7)).isoformat();v=self.visit(config,[o],day=lastweek)
  self.assertEqual(self.counter(config,lastweek)['reserved'],1);self.assertEqual(self.counter(config)['reserved'],0)
  self.order_status(o['id'],'Vollständig geprüft');self.call('PATCH','/api/authority-visits/'+v['id'],{'action':'submit','expectedVersion':1},self.office)
  self.assertEqual(self.counter(config,lastweek)['submitted'],0);self.assertEqual(self.counter(config)['submitted'],1)

 def test_20_appointments_can_be_saved_before_orders_exist(self):
  config=self.authority_config();v=self.visit(config,[])
  self.assertEqual(v['orderIds'],[])
  self.call('PATCH','/api/authority-visits/'+v['id'],{'action':'submit','expectedVersion':1},self.office,409)
  o=self.order();v,_=self.call('PATCH','/api/authority-visits/'+v['id'],{'action':'update','patch':{'orderIds':[o['id']]},'expectedVersion':1},self.office)
  self.assertEqual(self.current_order(o['id'])['authorityVisit']['id'],v['id'])

if __name__=='__main__':unittest.main()
