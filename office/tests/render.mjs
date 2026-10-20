import {build} from 'esbuild';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {outputFiles}=await build({stdin:{contents:`
export {default as App} from './src/App';
export {default as Dealer} from './src/Dealer';
export {default as Driver} from './src/Driver';
export {default as Modules} from './src/Modules';
export {default as AuthorityWorkspace,weekCounts,weekStart} from './src/Authority';
export {Context,AccountsPanel} from './src/Connection';`,resolveDir:process.cwd(),loader:'tsx'},bundle:true,write:false,format:'cjs',platform:'node',packages:'external',jsx:'automatic'});
const mod={exports:{}};new Function('require','module','exports',outputFiles[0].text)(require,mod,mod.exports);
const {App,Dealer,Driver,Modules,Context,AccountsPanel,AuthorityWorkspace,weekCounts,weekStart}=mod.exports;
const React=require('react');const {renderToString}=require('react-dom/server');
const id='TQ-2026-TEST1234';const order={id,vehicle:'Test Fahrzeug',type:'Neuzulassung',customer:'Test Händler',plate:'FB A 123',status:'Neu',employee:'Office',date:'19.10.2026',dealerId:'dealer',vin:'12345678901234567',form:{street:'Teststraße 1',city:'Teststadt'},_version:1};
const task={id:'F-test',orderId:id,driverId:'driver',tour:1,date:'2026-10-19',time:'10:00',type:'Übergabe',customer:'Test Händler',contact:'Testkontakt',address:'Teststraße 1',phone:'',plate:'FB A 123',status:'Geplant',_version:1};
let count=0;
for(const populated of [false,true])for(const role of ['admin','dealer','driver']){
 const data={user:{id:role,name:'Testnutzer',username:'test',role},people:[{id:'dealer',name:'Test Händler',role:'dealer',username:'dealer'},{id:'driver',name:'Test Fahrer',role:'driver',username:'driver'}],orders:populated?[order]:[],stops:populated?[task]:[],handovers:populated?[{id:'U-F-test',orderId:id,taskId:task.id,customer:'Test Händler',address:'Teststraße 1',time:'10:00',kind:'Dokumente',status:'Offen',items:[],_version:1}]:[],files:populated?[{id:'file',name:'Test.pdf',order:id,type:'Vollmacht',status:'Hochgeladen',date:'2026-10-19',size:'1 MB',url:'/api/files/file/content',purpose:'document',_version:1}]:[],events:populated?[{id:1,order_id:id,action:'Auftrag angelegt',created:'2026-10-19T10:00:00Z',actorName:'Testnutzer',read:false}]:[],states:{},authorities:populated?[{id:'friedberg',name:'Friedberg',mode:'Termin',weeklyMinimum:20,weeklyLimit:null,_version:1}]:[],authorityVisits:populated?[{id:'Z-test',authorityId:'friedberg',authorityName:'Friedberg',kind:'Termin',date:'2026-10-20',time:'10:00',status:'Geplant',orderIds:[id],confirmation:'Test-123',_version:1}]:[]};
 const value={data,refresh:async()=>{},updateList(){},saveState(){},request:async()=>({}),notify(){},logout:async()=>{}};
 const pages=role==='dealer'?['Dashboard','Aufträge','Neuer Auftrag','Auftragsdetails','Dokumente','Abholservice','Rechnungen','Nachrichten','Einstellungen']:role==='driver'?['Dashboard','Meine Touren','Aufträge','Route & Navigation','Übergaben','Fahrzeug','Nachrichten','Einstellungen']:['Dashboard','Dokumente','Touren & Abholung','Rechnungen','Kennzeichen','Nachrichten','Einstellungen','Mitarbeiter','Zulassungsstelle'];
 for(const page of pages){
  global.window={location:{search:page==='Auftragsdetails'?'?auftrag='+id:'?seite='+encodeURIComponent(page),pathname:role==='dealer'?'/haendler':role==='driver'?'/fahrer':'/'},history:{replaceState(){}},scrollTo(){}};global.location=window.location;
  const Component=role==='dealer'?Dealer:role==='driver'?Driver:page==='Dashboard'?App:page==='Mitarbeiter'?AccountsPanel:page==='Zulassungsstelle'?AuthorityWorkspace:Modules;
  const html=renderToString(React.createElement(Context.Provider,{value},React.createElement(Component,{section:page,onOpenOrder(){}})));
  if(html.includes('undefined')||html.length<100)throw Error('Invalid rendered content: '+role+' '+page+' populated='+populated);
  if(role==='admin'&&populated&&page==='Dashboard'&&!html.includes('Test Fahrzeug'))throw Error('Office does not render canonical order');
  count++;
 }
}
console.log('PASS: '+count+' populated and empty portal views render with versioned server data.');

const fake=[{id:'1',authorityId:'a',kind:'Händlerschalter',date:'2026-12-31',status:'Abgegeben',orderIds:['a','b']},{id:'2',authorityId:'a',kind:'Händlerschalter',date:'2027-01-01',status:'Geplant',orderIds:['b','c']},{id:'3',authorityId:'a',kind:'Händlerschalter',date:'2026-12-31',status:'Storniert',orderIds:['d']},{id:'4',authorityId:'a',kind:'Termin',date:'2026-12-31',status:'Abgegeben',orderIds:['e']}];
const counts=weekCounts(fake,'a','2027-01-01',20,25);
if(weekStart('2027-01-03')!=='2026-12-28'||counts.submitted!==2||counts.reserved!==1||counts.remainingMinimum!==18||counts.remainingCapacity!==22)throw Error('Incorrect weekly counter');
if(weekCounts(fake,'a','2027-01-04').submitted!==0||weekCounts(fake,'a','2027-01-01').remainingCapacity!==null)throw Error('Incorrect next-week/unlimited counter');
console.log('PASS: week boundaries, unique cases, cancellations, appointment exclusion and optional capacity.');
