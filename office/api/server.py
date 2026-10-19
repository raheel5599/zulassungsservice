"""Same-origin portal API. No external services or public file bucket."""
import base64, hashlib, hmac, json, os, re, secrets, sqlite3, time, urllib.parse, uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DATA=Path(os.environ.get('DATA_DIR','/data')); DATA.mkdir(parents=True,exist_ok=True)
os.chmod(DATA,0o700); (DATA/'files').mkdir(exist_ok=True)
DB=DATA/'portal.sqlite3'; ORIGIN=os.environ.get('PUBLIC_ORIGIN','https://zulassung.tariq-itconsulting.de'); SECURE=os.environ.get('COOKIE_SECURE','1')=='1'

class Connection(sqlite3.Connection):
    def __exit__(self,*args):
        try:return super().__exit__(*args)
        finally:self.close()
def db():
    c=sqlite3.connect(DB,timeout=10,factory=Connection); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c
with db() as c:
    c.executescript('''PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, username TEXT UNIQUE, name TEXT NOT NULL, role TEXT NOT NULL, password TEXT, invite_hash TEXT, invite_expires REAL, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY,dealer_id TEXT NOT NULL REFERENCES users(id),payload TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,order_id TEXT NOT NULL REFERENCES orders(id),driver_id TEXT NOT NULL REFERENCES users(id),payload TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS handovers(id TEXT PRIMARY KEY,task_id TEXT NOT NULL UNIQUE REFERENCES tasks(id),payload TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS files(id TEXT PRIMARY KEY,order_id TEXT NOT NULL REFERENCES orders(id),task_id TEXT REFERENCES tasks(id),owner_id TEXT NOT NULL REFERENCES users(id),name TEXT NOT NULL,mime TEXT NOT NULL,size INTEGER NOT NULL,purpose TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'Hochgeladen',kind TEXT NOT NULL DEFAULT 'Sonstiges',created TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS states(user_id TEXT NOT NULL REFERENCES users(id),key TEXT NOT NULL,value TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,PRIMARY KEY(user_id,key));
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,order_id TEXT,actor_id TEXT NOT NULL,action TEXT NOT NULL,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reads(user_id TEXT NOT NULL,event_id INTEGER NOT NULL,PRIMARY KEY(user_id,event_id));
CREATE TABLE IF NOT EXISTS attempts(key TEXT PRIMARY KEY,count INTEGER NOT NULL,until REAL NOT NULL);
''')
    if not c.execute('SELECT 1 FROM users LIMIT 1').fetchone() and not (DATA/'setup-code').exists():
        (DATA/'setup-code').write_text(secrets.token_urlsafe(24)); os.chmod(DATA/'setup-code',0o600)
os.chmod(DB,0o600)

def digest(s): return hashlib.sha256(s.encode()).hexdigest()
def stamp(): return datetime.now().astimezone().isoformat(timespec='seconds')
def password_hash(s):
    if not isinstance(s,str) or not 12<=len(s)<=256: raise Problem(400,'Das Passwort muss 12 bis 256 Zeichen lang sein.')
    salt=secrets.token_bytes(16); key=hashlib.pbkdf2_hmac('sha256',s.encode(),salt,600000)
    return salt.hex()+':'+key.hex()
def password_ok(s,stored):
    if not stored or not isinstance(s,str) or len(s)>256:return False
    salt,key=stored.split(':'); return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',s.encode(),bytes.fromhex(salt),600000).hex(),key)
class Problem(Exception):
    def __init__(self,status,message): self.status=status;self.message=message

def require(value,message='Unzulässige Anfrage.',status=400):
    if not value: raise Problem(status,message)
def staff(u): return u['role'] in ('admin','office')
def safe_user(u): return {k:u[k] for k in ('id','username','name','role')}
def row_payload(r): return {**json.loads(r['payload']),'_version':r['version']}
def order_access(c,u,oid):
    r=c.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone();require(r,'Auftrag nicht gefunden.',404)
    permitted=staff(u) or r['dealer_id']==u['id'] or (u['role']=='driver' and c.execute('SELECT 1 FROM tasks WHERE order_id=? AND driver_id=?',(oid,u['id'])).fetchone())
    require(permitted,'Kein Zugriff auf diesen Auftrag.',403);return r

def visible_orders(c,u):
    if staff(u): rows=c.execute('SELECT * FROM orders ORDER BY rowid DESC').fetchall()
    elif u['role']=='dealer': rows=c.execute('SELECT * FROM orders WHERE dealer_id=? ORDER BY rowid DESC',(u['id'],)).fetchall()
    else: rows=c.execute('SELECT DISTINCT o.* FROM orders o JOIN tasks t ON t.order_id=o.id WHERE t.driver_id=? ORDER BY o.rowid DESC',(u['id'],)).fetchall()
    return rows

def validate_order(payload):
    for key in ('vehicle','variant','plate','type','office','priority','vin','holder','status','employee','plateStatus'):
        require(isinstance(payload.get(key,''),str) and len(payload.get(key,''))<=500,'Ungültiges Auftragsfeld: '+key)
    require(payload.get('vehicle','').strip() and payload.get('type','').strip(),'Fahrzeug und Vorgangsart erforderlich.')
    form=payload.get('form',{})
    require(isinstance(form,dict) and len(form)<=80 and all(isinstance(k,str) and len(k)<=100 and (isinstance(v,bool) or isinstance(v,str) and len(v)<=5000) for k,v in form.items()),'Ungültige Formulardaten.')

def file_json(r):return {'id':r['id'],'name':r['name'],'order':r['order_id'],'taskId':r['task_id'],'type':r['kind'],'status':r['status'],'date':r['created'][:10],'size':str(round(r['size']/1024/1024,2))+' MB','url':'/api/files/'+r['id']+'/content','purpose':r['purpose'],'local':False,'_version':r['version']}
def event(c,u,oid,action): c.execute('INSERT INTO events(order_id,actor_id,action,created) VALUES(?,?,?,?)',(oid,u['id'],action,stamp()))
def version(r,body):require(isinstance(body.get('expectedVersion'),int) and r['version']==body['expectedVersion'],'Die Daten wurden zwischenzeitlich geändert. Bitte erneut versuchen.',409)

class Handler(BaseHTTPRequestHandler):
    server_version='PortalAPI'
    def log_message(self,fmt,*args):
        # Never log URL queries, cookies, invitation tokens, filenames or request bodies.
        print(self.command,self.path.split('?')[0],flush=True)
    def reply(self,status=200,data=None,cookie=None):
        if status<400 and getattr(self,'db_connection',None):self.db_connection.commit()
        b=json.dumps(data if data is not None else {},ensure_ascii=False).encode();self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        if cookie:self.send_header('Set-Cookie',cookie)
        self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
    def body(self,limit=1048576):
        try:n=int(self.headers.get('Content-Length','0'))
        except ValueError:raise Problem(400,'Ungültige Länge.')
        require(0<n<=limit,'Anfrage ist leer oder zu groß.',413);return self.rfile.read(n)
    def json(self):
        require(self.headers.get_content_type()=='application/json','JSON erwartet.',415)
        try:b=json.loads(self.body())
        except (ValueError,UnicodeDecodeError):raise Problem(400,'Ungültiges JSON.')
        require(isinstance(b,dict));return b
    def auth(self,c,optional=False):
        token=None
        for part in self.headers.get('Cookie','').split(';'):
            if part.strip().startswith('tq_session='):token=part.strip().split('=',1)[1]
        u=c.execute('SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>? AND u.active=1',(digest(token or ''),time.time())).fetchone()
        if not optional:require(u,'Bitte anmelden.',401)
        return u
    def cookie(self,token,maxage=43200):return 'tq_session='+token+'; Path=/; HttpOnly; SameSite=Lax; Max-Age='+str(maxage)+('; Secure' if SECURE else '')
    def session(self,c,u):
        token=secrets.token_urlsafe(32);c.execute('DELETE FROM sessions WHERE expires<?',(time.time(),));c.execute('INSERT INTO sessions VALUES(?,?,?)',(digest(token),u['id'],time.time()+43200));return self.cookie(token)
    def rate(self,c,key):
        row=c.execute('SELECT * FROM attempts WHERE key=?',(key,)).fetchone()
        if row and row['until']>time.time() and row['count']>=8:raise Problem(429,'Zu viele Versuche. Bitte in 15 Minuten erneut versuchen.')
        if not row or row['until']<=time.time():c.execute('INSERT OR REPLACE INTO attempts VALUES(?,1,?)',(key,time.time()+900))
        else:c.execute('UPDATE attempts SET count=count+1 WHERE key=?',(key,))
        c.commit()
    def handle_api(self):
        route=urllib.parse.urlparse(self.path);p=route.path;method=self.command
        if method in ('POST','PATCH','PUT','DELETE'):require(self.headers.get('Origin')==ORIGIN,'Anfrage aus nicht erlaubter Herkunft.',403)
        with db() as c:
            self.db_connection=c
            if p=='/api/health' and method=='GET':self.reply(data={'ok':True});return
            if p=='/api/auth/state' and method=='GET':
                u=self.auth(c,True);self.reply(data={'setupRequired':not bool(c.execute('SELECT 1 FROM users LIMIT 1').fetchone()),'user':safe_user(u) if u else None});return
            if p in ('/api/auth/setup','/api/auth/login','/api/auth/accept-invite') and method=='POST':
                b=self.json();key=self.headers.get('X-Real-IP',self.client_address[0])+':'+p+(':'+str(b.get('username','')).strip().lower() if p.endswith('/login') else '');self.rate(c,key);c.execute('BEGIN IMMEDIATE')
                if p.endswith('/setup'):
                    require(not c.execute('SELECT 1 FROM users LIMIT 1').fetchone(),'Einrichtung bereits abgeschlossen.',409)
                    require((DATA/'setup-code').exists() and hmac.compare_digest(str(b.get('code','')),(DATA/'setup-code').read_text().strip()),'Einrichtungscode ungültig.',403)
                    username=str(b.get('username','')).strip().lower();name=str(b.get('name','')).strip()
                    require(re.fullmatch(r'[a-z0-9_.@-]{3,100}',username) and 1<=len(name)<=150,'Name oder Benutzername ungültig.')
                    uid=uuid.uuid4().hex;c.execute('INSERT INTO users(id,username,name,role,password) VALUES(?,?,?,?,?)',(uid,username,name,'admin',password_hash(b.get('password'))));u=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
                elif p.endswith('/accept-invite'):
                    u=c.execute('SELECT * FROM users WHERE invite_hash=? AND invite_expires>? AND active=1',(digest(str(b.get('token',''))),time.time())).fetchone();require(u,'Einladung ungültig oder abgelaufen.',403)
                    username=str(b.get('username','')).strip().lower();require(re.fullmatch(r'[a-z0-9_.@-]{3,100}',username),'Benutzername ungültig.')
                    require(not c.execute('SELECT 1 FROM users WHERE username=? AND id!=?',(username,u['id'])).fetchone(),'Benutzername bereits vergeben.',409)
                    c.execute('DELETE FROM sessions WHERE user_id=?',(u['id'],));c.execute('UPDATE users SET username=?,password=?,invite_hash=NULL,invite_expires=NULL WHERE id=?',(username,password_hash(b.get('password')),u['id']));u=c.execute('SELECT * FROM users WHERE id=?',(u['id'],)).fetchone()
                else:
                    u=c.execute('SELECT * FROM users WHERE username=? AND active=1',(str(b.get('username','')).strip().lower(),)).fetchone();require(u and password_ok(b.get('password'),u['password']),'Anmeldedaten ungültig.',401)
                cookie=self.session(c,u);c.commit()
                if p.endswith('/setup'):(DATA/'setup-code').unlink(missing_ok=True)
                self.reply(data={'user':safe_user(u)},cookie=cookie);return
            u=self.auth(c)
            if p=='/api/auth/logout' and method=='POST':
                for v in self.headers.get('Cookie','').split(';'):
                    if v.strip().startswith('tq_session='):c.execute('DELETE FROM sessions WHERE token_hash=?',(digest(v.strip().split('=',1)[1]),))
                self.reply(data={'ok':True},cookie=self.cookie('',0));return
            if p=='/api/snapshot' and method=='GET':
                rows=visible_orders(c,u);ids=[r['id'] for r in rows];orders=[{**row_payload(r),'dealerId':r['dealer_id']} for r in rows]
                tasks=c.execute('SELECT * FROM tasks'+('' if staff(u) else ' WHERE driver_id=?'),() if staff(u) else (u['id'],)).fetchall() if u['role']!='dealer' else [t for t in c.execute('SELECT * FROM tasks').fetchall() if t['order_id'] in ids]
                taskids={r['id'] for r in tasks};hands=[row_payload(r) for r in c.execute('SELECT * FROM handovers').fetchall() if r['task_id'] in taskids] if u['role']!='dealer' else []
                files=[file_json(r) for r in c.execute('SELECT * FROM files ORDER BY rowid DESC').fetchall() if r['order_id'] in ids and (u['role']!='dealer' or r['purpose']=='document') and (u['role']!='driver' or r['purpose']=='document' or r['task_id'] in taskids)]
                states={r['key']:{'value':json.loads(r['value']),'version':r['version']} for r in c.execute('SELECT * FROM states WHERE user_id=?',(u['id'],))}
                people=[safe_user(r) for r in c.execute('SELECT * FROM users WHERE active=1')] if staff(u) else []
                events=[{**dict(r),'read':r['actor_id']==u['id'] or bool(c.execute('SELECT 1 FROM reads WHERE user_id=? AND event_id=?',(u['id'],r['id'])).fetchone())} for r in c.execute('SELECT e.id,e.order_id,e.actor_id,e.action,e.created,u.name AS actorName FROM events e JOIN users u ON u.id=e.actor_id ORDER BY e.id DESC LIMIT 200') if r['order_id'] in ids]
                self.reply(data={'user':safe_user(u),'orders':orders,'stops':[row_payload(r) for r in tasks],'handovers':hands,'files':files,'states':states,'people':people,'events':events});return
            if p=='/api/users' and method=='POST':
                require(u['role']=='admin','Nur Administratoren dürfen Konten anlegen.',403);b=self.json();role=b.get('role');name=str(b.get('name','')).strip();require(role in ('office','dealer','driver') and 1<=len(name)<=150,'Name oder Rolle ungültig.')
                token=secrets.token_urlsafe(32);uid=uuid.uuid4().hex;c.execute('INSERT INTO users(id,name,role,invite_hash,invite_expires) VALUES(?,?,?,?,?)',(uid,name,role,digest(token),time.time()+86400));self.reply(201,{'id':uid,'invitation':ORIGIN+('/haendler' if role=='dealer' else '/fahrer' if role=='driver' else '/')+'?einladung='+token});return
            if p.startswith('/api/state/') and method=='PUT':
                key=urllib.parse.unquote(p[len('/api/state/'):]);require(re.fullmatch(r'tariq-[a-zA-Z0-9_-]{1,100}',key),'Ungültiger Schlüssel.');b=self.json();require('value' in b)
                payload=json.dumps(b['value']);require(len(payload)<200000,'Datensatz zu groß.',413);c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT * FROM states WHERE user_id=? AND key=?',(u['id'],key)).fetchone();old=r['version'] if r else 0;require(b.get('expectedVersion')==old,'Daten wurden geändert. Bitte erneut versuchen.',409)
                c.execute('INSERT INTO states VALUES(?,?,?,?) ON CONFLICT(user_id,key) DO UPDATE SET value=excluded.value,version=excluded.version',(u['id'],key,payload,old+1));self.reply(data={'version':old+1});return
            if p=='/api/orders' and method=='POST':
                require(staff(u) or u['role']=='dealer','Keine Berechtigung.',403);b=self.json();dealerid=u['id'] if u['role']=='dealer' else b.get('dealerId');dealer=c.execute('SELECT * FROM users WHERE id=? AND role=? AND active=1',(dealerid,'dealer')).fetchone();require(dealer,'Bitte ein Händlerkonto auswählen.')
                require(isinstance(b.get('vehicle'),str) and 1<=len(b['vehicle'].strip())<=200 and b.get('type'),'Fahrzeug und Vorgangsart erforderlich.')
                oid=b.get('id') or 'TQ-'+datetime.now().strftime('%Y')+'-'+uuid.uuid4().hex[:8].upper();require(isinstance(oid,str) and re.fullmatch(r'TQ-[0-9]{4}-[A-Za-z0-9]{4,32}',oid),'Ungültige Auftragsnummer.');require(not c.execute('SELECT 1 FROM orders WHERE id=?',(oid,)).fetchone(),'Auftragsnummer bereits vorhanden.',409);payload={**{k:'' for k in ('variant','plate','office','priority','vin','holder')},**{k:v for k,v in b.items() if k in ('vehicle','variant','plate','type','office','priority','vin','holder','form')}};validate_order(payload);payload.update(id=oid,customer=dealer['name'],status='Neu',employee='Office',date=datetime.now().strftime('%d.%m.%Y'))
                form=payload.get('form',{})
                if isinstance(form,dict) and form.get('pickupDate'):
                    require(re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',str(form['pickupDate'])),'Ungültiges Abholdatum.')
                    payload['pickupRequest']={'date':form['pickupDate'],'time':str(form.get('pickupTime','09:00'))[:30],'address':', '.join(str(form.get(k,'')) for k in ('street','zip','city'))[:500],'status':'Angefragt'}
                c.execute('INSERT INTO orders(id,dealer_id,payload) VALUES(?,?,?)',(oid,dealerid,json.dumps(payload)));event(c,u,oid,'Auftrag angelegt');self.reply(201,{**payload,'dealerId':dealerid,'_version':1});return
            m=re.fullmatch(r'/api/events/([0-9]+)/read',p)
            if m and method=='POST':
                r=c.execute('SELECT * FROM events WHERE id=?',(int(m[1]),)).fetchone();require(r,'Mitteilung nicht gefunden.',404);order_access(c,u,r['order_id']);c.execute('INSERT OR IGNORE INTO reads VALUES(?,?)',(u['id'],r['id']));self.reply(data={'ok':True});return
            m=re.fullmatch(r'/api/orders/([^/]+)/pickup-request',p)
            if m and method=='POST':
                require(staff(u) or u['role']=='dealer','Keine Berechtigung.',403);b=self.json();c.execute('BEGIN IMMEDIATE');r=order_access(c,u,m[1]);version(r,b);require(isinstance(b.get('address'),str) and 1<=len(b['address'])<=500 and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',str(b.get('date',''))),'Adresse oder Datum ungültig.')
                payload=json.loads(r['payload']);require(not payload.get('pickupRequest') or payload['pickupRequest'].get('status')!='Geplant','Abholung ist bereits geplant.',409);payload['pickupRequest']={'address':b['address'],'date':b['date'],'time':str(b.get('time','09:00'))[:30],'status':'Angefragt'};c.execute('UPDATE orders SET payload=?,version=version+1 WHERE id=?',(json.dumps(payload),r['id']));event(c,u,r['id'],'Abholung angefragt');self.reply(data={**payload,'_version':r['version']+1});return
            m=re.fullmatch(r'/api/orders/([^/]+)',p)
            if m and method=='PATCH':
                b=self.json();c.execute('BEGIN IMMEDIATE');r=order_access(c,u,m[1]);require(staff(u) or u['role']=='dealer','Keine Berechtigung.',403);version(r,b);old=json.loads(r['payload']);patch=b.get('patch',{});require(isinstance(patch,dict));allowed={'vehicle','variant','plate','type','office','priority','vin','holder','form'}
                if staff(u):allowed|={'status','employee','plateStatus'}
                else:require(old['status'] in ('Neu','Unterlagen fehlen'),'Dieser Auftrag wird bereits bearbeitet.',409)
                require(set(patch)<=allowed,'Diese Felder dürfen Sie nicht ändern.',403)
                if 'plateStatus' in patch:require(patch['plateStatus'] in ('Offen','In Vorbereitung','In Produktion','Fertig','Zur Abholung','Abgeholt'),'Ungültiger Produktionsstatus.')
                if 'status' in patch:require(patch['status'] in ('Neu','Abgeholt','In Prüfung','Unterlagen fehlen','Bei Behörde','Fertig','Ausgeliefert'),'Ungültiger Status.')
                payload={**old,**patch};validate_order(payload);c.execute('UPDATE orders SET payload=?,version=version+1 WHERE id=?',(json.dumps(payload),r['id']));event(c,u,r['id'],'Auftrag aktualisiert'+(' · '+patch['status'] if 'status' in patch else ''));self.reply(data={**payload,'dealerId':r['dealer_id'],'_version':r['version']+1});return
            m=re.fullmatch(r'/api/orders/([^/]+)/assign',p)
            if m and method=='POST':
                require(staff(u),'Nur Office darf Fahrer zuweisen.',403);b=self.json();c.execute('BEGIN IMMEDIATE');r=order_access(c,u,m[1]);require(str(b.get('tour',1)).isdigit() and 1<=int(b.get('tour',1))<=100,'Ungültige Tour.');d=c.execute('SELECT * FROM users WHERE id=? AND role=? AND active=1',(b.get('driverId'),'driver')).fetchone();require(d,'Fahrer nicht gefunden.');require(b.get('type') in ('Abholung','Übergabe') and isinstance(b.get('address'),str) and b['address'].strip(),'Art und Adresse erforderlich.')
                require(not c.execute('SELECT 1 FROM tasks WHERE order_id=? AND json_extract(payload,\'$.type\')=? AND json_extract(payload,\'$.status\')!=?',(r['id'],b['type'],'Erledigt')).fetchone(),'Für diesen Auftrag besteht bereits ein offener Transport.',409)
                oid=r['id'];order=json.loads(r['payload']);tid='F-'+uuid.uuid4().hex[:12];payload={'id':tid,'orderId':oid,'tour':int(b.get('tour',1)),'date':str(b.get('date',datetime.now().strftime('%Y-%m-%d'))),'time':str(b.get('time','09:00')),'type':b['type'],'customer':order['customer'],'contact':str(b.get('contact',order.get('holder',''))),'address':b['address'].strip(),'phone':str(b.get('phone','')),'plate':order.get('plate',''),'status':'Geplant','driverId':d['id']}
                c.execute('INSERT INTO tasks(id,order_id,driver_id,payload) VALUES(?,?,?,?)',(tid,oid,d['id'],json.dumps(payload)))
                if b['type']=='Übergabe':
                    h={'id':'U-'+tid,'taskId':tid,'orderId':oid,'customer':order['customer'],'address':payload['address'],'time':payload['time'],'kind':'Dokumente / Kennzeichen','status':'Offen','items':[]};c.execute('INSERT INTO handovers(id,task_id,payload) VALUES(?,?,?)',(h['id'],tid,json.dumps(h)))
                if order.get('pickupRequest') and b['type']=='Abholung':
                    order['pickupRequest']['status']='Geplant';order['pickupRequest']['taskId']=tid;c.execute('UPDATE orders SET payload=?,version=version+1 WHERE id=?',(json.dumps(order),oid))
                event(c,u,oid,b['type']+' an '+d['name']+' zugewiesen');self.reply(201,{**payload,'_version':1});return
            m=re.fullmatch(r'/api/stops/([^/]+)',p)
            if m and method=='PATCH':
                b=self.json();c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT * FROM tasks WHERE id=?',(m[1],)).fetchone();require(r,'Transport nicht gefunden.',404);require(staff(u) or r['driver_id']==u['id'],'Keine Berechtigung.',403);version(r,b);patch=b.get('patch',{});require(set(patch)<=set(('status','arrivedAt','completedAt')),'Nicht erlaubte Änderung.',403);old=json.loads(r['payload']);s=patch.get('status');require(s in ('Geplant','In Bearbeitung','Angekommen','Erledigt'),'Ungültiger Status.');require(old['status']!='Erledigt' or s=='Erledigt','Abgeschlossener Transport darf nicht zurückgesetzt werden.',409)
                if s=='Erledigt' and old['type']=='Übergabe':
                    h=c.execute('SELECT payload FROM handovers WHERE task_id=?',(r['id'],)).fetchone();require(h and json.loads(h['payload'])['status']=='Bestätigt','Bitte zuerst die Übergabe bestätigen.',409)
                payload={**old,'status':s};payload.update({'arrivedAt':datetime.now().strftime('%H:%M')} if s=='Angekommen' else {'completedAt':datetime.now().strftime('%H:%M')} if s=='Erledigt' else {})
                c.execute('UPDATE tasks SET payload=?,version=version+1 WHERE id=?',(json.dumps(payload),r['id']))
                if s=='Erledigt':
                    o=c.execute('SELECT payload FROM orders WHERE id=?',(r['order_id'],)).fetchone();op=json.loads(o['payload']);op['status']='Abgeholt' if old['type']=='Abholung' else 'Ausgeliefert';c.execute('UPDATE orders SET payload=?,version=version+1 WHERE id=?',(json.dumps(op),r['order_id']))
                event(c,u,r['order_id'],old['type']+' · '+s);self.reply(data={**payload,'_version':r['version']+1});return
            m=re.fullmatch(r'/api/handovers/([^/]+)',p)
            if m and method=='PATCH':
                b=self.json();c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT h.*,t.driver_id,t.order_id FROM handovers h JOIN tasks t ON t.id=h.task_id WHERE h.id=?',(m[1],)).fetchone();require(r,'Übergabe nicht gefunden.',404);require(staff(u) or r['driver_id']==u['id'],'Keine Berechtigung.',403);version(r,b);old=json.loads(r['payload']);require(old['status']!='Bestätigt','Übergabe bereits bestätigt.',409);patch=b.get('patch',{});require(set(patch)<=set(('items','recipient','signature','status','confirmedAt','photoId','photoName')),'Ungültige Felder.',403);payload={**old,**patch};items=payload.get('items');require(isinstance(items,list) and len(items)<=20 and all(isinstance(x,str) and len(x)<=200 for x in items),'Positionen ungültig.')
                if payload.get('status')=='Bestätigt':
                    sig=payload.get('signature','');require(isinstance(sig,str) and sig.startswith('data:image/png;base64,') and len(sig)<250000 and payload.get('recipient','').strip() and items,'Name, Positionen und Unterschrift erforderlich.')
                    try:raw=base64.b64decode(sig.split(',',1)[1],validate=True)
                    except ValueError:raise Problem(400,'Unterschrift ungültig.')
                    require(raw.startswith(b'\x89PNG\r\n\x1a\n'),'Unterschrift ungültig.')
                    f=c.execute('SELECT * FROM files WHERE id=? AND task_id=? AND purpose=?',(payload.get('photoId'),r['task_id'],'proof')).fetchone();require(f,'Ein zugehöriges Nachweisfoto ist erforderlich.');payload['confirmedAt']=datetime.now().strftime('%H:%M');event(c,u,r['order_id'],'Übergabe bestätigt')
                else:require(payload.get('status')=='Offen','Ungültiger Status.')
                c.execute('UPDATE handovers SET payload=?,version=version+1 WHERE id=?',(json.dumps(payload),r['id']));self.reply(data={**payload,'_version':r['version']+1});return
            if p=='/api/files' and method=='POST':
                oid=self.headers.get('X-Order-Id','');order_access(c,u,oid);purpose=self.headers.get('X-Purpose','document');tid=self.headers.get('X-Task-Id') or None;require(purpose in ('document','proof'))
                if purpose=='proof':
                    task=c.execute('SELECT * FROM tasks WHERE id=? AND order_id=?',(tid,oid)).fetchone();require(task and (staff(u) or task['driver_id']==u['id']),'Kein Zugriff auf diesen Nachweis.',403)
                else:require(staff(u) or u['role']=='dealer','Keine Berechtigung zum Dokumentenupload.',403)
                mime=self.headers.get_content_type();require(mime in ('application/pdf','image/png','image/jpeg','image/webp','image/heic','image/heif'),'Dateityp nicht unterstützt.',415);require(purpose!='proof' or mime.startswith('image/'),'Nachweis muss ein Bild sein.')
                raw=self.body(10*1024*1024);magic={'application/pdf':raw.startswith(b'%PDF-'),'image/png':raw.startswith(b'\x89PNG\r\n\x1a\n'),'image/jpeg':raw.startswith(b'\xff\xd8\xff'),'image/webp':raw.startswith(b'RIFF') and raw[8:12]==b'WEBP','image/heic':raw[4:8]==b'ftyp','image/heif':raw[4:8]==b'ftyp'};require(magic[mime],'Dateiinhalt passt nicht zum Dateityp.')
                name=Path(urllib.parse.unquote(self.headers.get('X-File-Name','Dokument'))).name;name=re.sub(r'[\x00-\x1f\x7f]','',name)[:200] or 'Dokument';fid=uuid.uuid4().hex;path=DATA/'files'/fid;path.write_bytes(raw);os.chmod(path,0o600)
                try:c.execute('INSERT INTO files(id,order_id,task_id,owner_id,name,mime,size,purpose,created) VALUES(?,?,?,?,?,?,?,?,?)',(fid,oid,tid,u['id'],name,mime,len(raw),purpose,stamp()));event(c,u,oid,'Nachweis hochgeladen' if purpose=='proof' else 'Dokument hochgeladen');c.commit()
                except Exception:path.unlink(missing_ok=True);raise
                self.reply(201,file_json(c.execute('SELECT * FROM files WHERE id=?',(fid,)).fetchone()));return
            m=re.fullmatch(r'/api/files/([^/]+)/content',p)
            if m and method=='GET':
                f=c.execute('SELECT * FROM files WHERE id=?',(m[1],)).fetchone();require(f,'Datei nicht gefunden.',404);order_access(c,u,f['order_id']);require(u['role']!='dealer' or f['purpose']=='document','Keine Berechtigung.',403);require(u['role']!='driver' or f['purpose']=='document' or c.execute('SELECT 1 FROM tasks WHERE id=? AND driver_id=?',(f['task_id'],u['id'])).fetchone(),'Keine Berechtigung.',403);raw=(DATA/'files'/f['id']).read_bytes();self.send_response(200);self.send_header('Content-Type',f['mime']);self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','private, no-store');self.send_header('Content-Security-Policy',"sandbox; default-src 'none'");self.send_header('Content-Disposition',('inline' if urllib.parse.parse_qs(route.query).get('inline')==['1'] else 'attachment')+"; filename*=UTF-8''"+urllib.parse.quote(f['name']));self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
            m=re.fullmatch(r'/api/files/([^/]+)',p)
            if m and method=='PATCH':
                b=self.json();c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT * FROM files WHERE id=?',(m[1],)).fetchone();require(r,'Datei nicht gefunden.',404);order_access(c,u,r['order_id']);version(r,b);patch=b.get('patch',{});require(isinstance(patch,dict));require(set(patch)<=({'status','type'} if staff(u) else {'type'}),'Keine Berechtigung für diese Änderung.',403);require(staff(u) or r['owner_id']==u['id'],'Keine Berechtigung.',403)
                status=patch.get('status',r['status']);kind=patch.get('type',r['kind']);require(status in ('Hochgeladen','In Prüfung','Freigegeben','Abgelehnt','Nachgefordert','Geprüft') and isinstance(kind,str) and len(kind)<=100)
                c.execute('UPDATE files SET status=?,kind=?,version=version+1 WHERE id=?',(status,kind,r['id']));self.reply(data=file_json(c.execute('SELECT * FROM files WHERE id=?',(r['id'],)).fetchone()));return
            raise Problem(404,'Endpunkt nicht gefunden.')
    def dispatch(self):
        try:self.handle_api()
        except Problem as e:self.reply(e.status,{'error':e.message})
        except (ValueError,TypeError,KeyError):self.reply(400,{'error':'Ungültige Eingaben.'})
        except Exception as e:print('API error:',type(e).__name__,flush=True);self.reply(500,{'error':'Serverfehler. Bitte erneut versuchen.'})
    do_GET=dispatch;do_POST=dispatch;do_PATCH=dispatch;do_PUT=dispatch;do_DELETE=dispatch

if __name__=='__main__':ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','8000'))),Handler).serve_forever()
