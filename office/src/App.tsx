import { useMemo, useState } from 'react';
import { LayoutDashboard, ClipboardList, PlusCircle, Users, FolderOpen, Truck, Receipt, CarFront, UserRoundCog, MessageCircle, Settings, Search, Bell, Menu, X, FileCheck2, Building2, BadgeCheck, AlertCircle, ArrowRight, Clock3, PackageCheck, Check, ExternalLink } from 'lucide-react';

type Section = 'Dashboard'|'Aufträge'|'Neuer Auftrag'|'Händler & Privatkunden'|'Dokumente'|'Touren & Abholung'|'Rechnungen'|'Kennzeichen'|'Mitarbeiter'|'Nachrichten'|'Einstellungen';
type Order = { id:string; vehicle:string; type:string; customer:string; plate:string; status:string; employee:string; date:string };
const nav: {name:Section; icon:typeof LayoutDashboard}[] = [
 {name:'Dashboard',icon:LayoutDashboard},{name:'Aufträge',icon:ClipboardList},{name:'Neuer Auftrag',icon:PlusCircle},
 {name:'Händler & Privatkunden',icon:Users},{name:'Dokumente',icon:FolderOpen},{name:'Touren & Abholung',icon:Truck},
 {name:'Rechnungen',icon:Receipt},{name:'Kennzeichen',icon:CarFront},{name:'Mitarbeiter',icon:UserRoundCog},
 {name:'Nachrichten',icon:MessageCircle},{name:'Einstellungen',icon:Settings}
];
const initial:Order[] = [
 {id:'TQ-2026-1001',vehicle:'VW Golf 1.5 eTSI',type:'Neuzulassung',customer:'Autohaus Mustermann',plate:'FB · TA 123',status:'Bei Behörde',employee:'Office',date:'19.10.2026'},
 {id:'TQ-2026-1002',vehicle:'Audi A4 40 TDI',type:'Ummeldung',customer:'Autohaus Wetterau',plate:'FB · AW 456',status:'Fertig',employee:'Office',date:'19.10.2026'},
 {id:'TQ-2026-1003',vehicle:'BMW 320d',type:'Abmeldung',customer:'Privatkunde M. Weber',plate:'FB · MW 21',status:'Unterlagen fehlen',employee:'Office',date:'19.10.2026'},
 {id:'TQ-2026-1004',vehicle:'Mercedes C 200',type:'Wiederzulassung',customer:'Autohaus Mitte',plate:'FB · TC 789',status:'In Prüfung',employee:'Office',date:'19.10.2026'},
 {id:'TQ-2026-1005',vehicle:'Skoda Octavia',type:'Neuzulassung',customer:'Autohaus Friedberg',plate:'FB · SO 404',status:'Abgeholt',employee:'Office',date:'19.10.2026'}
];
const modules:Record<Section,string> = {
 'Dashboard':'Zentrale Steuerung für Aufträge, Dokumente, Touren und Rechnungen.',
 'Aufträge':'Alle Zulassungsvorgänge zentral verwalten und bearbeiten.',
 'Neuer Auftrag':'Neuen Zulassungsvorgang für Privatkunden oder Autohäuser erfassen.',
 'Händler & Privatkunden':'Geschäftskunden und Privatkunden zentral verwalten.',
 'Dokumente':'Unterlagen prüfen, nachfordern und freigeben.',
 'Touren & Abholung':'Fahrer, Abholungen und Rücklieferungen koordinieren.',
 'Rechnungen':'Rechnungen, Zahlungen und Gutschriften verwalten.',
 'Kennzeichen':'Kennzeichenaufträge, Produktion und Ausgabe verwalten.',
 'Mitarbeiter':'Mitarbeiterkonten, Rollen und Verantwortlichkeiten verwalten.',
 'Nachrichten':'Kommunikation mit Händlern, Kunden und Fahrern.',
 'Einstellungen':'System, Unternehmen und Benachrichtigungen verwalten.'
};
const color=(s:string)=>s==='Fertig'?'ok':s==='Unterlagen fehlen'?'danger':s==='In Prüfung'?'warn':'blue';
export default function App(){
 const [section,setSection]=useState<Section>('Dashboard');
 const [orders,setOrders]=useState<Order[]>(initial);
 const [query,setQuery]=useState('');
 const [selected,setSelected]=useState<string|null>(null);
 const [mobile,setMobile]=useState(false);
 const [draft,setDraft]=useState({vehicle:'',customer:'',plate:'',type:'Neuzulassung'});
 const filtered=useMemo(()=>orders.filter(o=>Object.values(o).some(v=>v.toLowerCase().includes(query.toLowerCase()))),[orders,query]);
 const active=orders.find(o=>o.id===selected);
 const navigate=(to:Section)=>{setSection(to);setMobile(false);setSelected(null)};
 const add=()=>{if(!draft.vehicle.trim()||!draft.customer.trim())return;const id='TQ-2026-'+String(1001+orders.length);setOrders(v=>[{...draft,id,status:'Neu',employee:'Office',date:new Date().toLocaleDateString('de-DE')},...v]);setDraft({vehicle:'',customer:'',plate:'',type:'Neuzulassung'});navigate('Aufträge');setSelected(id)};
 const changeStatus=(id:string,status:string)=>setOrders(v=>v.map(o=>o.id===id?{...o,status}:o));
 return <div className="shell">
  <aside className={'sidebar '+(mobile?'expanded':'')}>
   <div className="logo"><img src="/logo-ug.png" alt="TARIQ Zulassungsservice UG (haftungsbeschränkt)" /></div>
   <nav>{nav.map(({name,icon:Icon})=><button key={name} className={section===name?'active':''} onClick={()=>navigate(name)}><Icon size={20}/><span>{name}</span>{name==='Nachrichten'&&<small>3</small>}</button>)}</nav>
   <div className="slogan"><div className="road">◆</div>SCHNELL.<br/>ZUVERLÄSSIG.<br/>KOMPETENT.<br/><em>FÜR IHREN ZULASSUNGSSERVICE.</em></div>
  </aside>
  {mobile&&<button className="overlay" aria-label="Menü schließen" onClick={()=>setMobile(false)} />}
  <div className="workspace">
   <header className="topbar"><button className="mobile-menu" onClick={()=>setMobile(!mobile)} aria-label="Menü öffnen">{mobile?<X/>:<Menu/>}</button><div className="global-search"><Search size={18}/><input aria-label="Aufträge suchen" placeholder="Aufträge, Kennzeichen, Kunden oder Vorgangsnummer suchen ..." value={query} onChange={e=>setQuery(e.target.value)}/></div><div className="account"><Bell size={20}/><span className="avatar">T</span><div><strong>TARIQ Office</strong><small>Administrator · Demo</small></div></div></header>
   <main><div className="hero"><div><h1>{section==='Dashboard'?'Office Dashboard':section==='Aufträge'?'Auftragsverwaltung':section==='Kennzeichen'?'Kennzeichenproduktion':section==='Touren & Abholung'?'Tourenplanung & Abholservice':section}</h1><p>{modules[section]}</p></div><div className="hero-tag">ZULASSUNG LEICHT GEMACHT.<br/><small>IHR PARTNER IM AUTOHANDEL.</small></div></div>
   {section==='Dashboard'&&<><div className="kpis">
    {[['24','Offene Aufträge',ClipboardList],['12','Heute bei Zulassungsstelle',Building2],['18','Dokumente zu prüfen',FileCheck2],['7','Offene Rechnungen',Receipt],['32','Kennzeichen heute',CarFront]].map(([n,label,Icon],i)=><button className="kpi" key={String(label)} onClick={()=>navigate((['Aufträge','Aufträge','Dokumente','Rechnungen','Kennzeichen'] as Section[])[i])}><span className="bubble"><Icon size={23}/></span><div><b>{n as string}</b><span>{label as string}</span></div><ArrowRight size={15}/></button>)}
    </div><div className="columns"><section className="panel"><div className="panel-title"><h2>Aktuelle Vorgänge</h2><button onClick={()=>navigate('Aufträge')}>Alle Vorgänge <ArrowRight size={15}/></button></div><OrdersTable orders={filtered.slice(0,6)} onSelect={setSelected}/></section><section className="panel"><div className="panel-title"><h2>Heutige Aufgaben</h2></div>{['Unterlagen für TQ-2026-1003 nachfordern','Fertige Kennzeichen kontrollieren','Dokumente von Autohaus Wetterau prüfen','Abholbestätigung vom Fahrer einholen'].map((t,i)=><label className="task" key={t}><input type="checkbox" defaultChecked={i===0}/><span>{t}</span><small>{9+i*2}:00</small></label>)}<div className="panel-title"><h2>Nächste Tour / Abholung</h2></div><div className="pickup"><Truck/><div><b>Friedberg & Wetterau</b><small>Tour noch nicht bestätigt</small></div></div></section></div><div className="bottom-row"><section className="panel"><div className="panel-title"><h2>Letzte Aktivitäten</h2></div><p className="muted">Demo-Ansicht: Die echten Statusänderungen erscheinen nach Anbindung des Backends hier automatisch.</p></section><section className="panel"><h2>Schnellaktionen</h2><div className="actions"><button onClick={()=>navigate('Neuer Auftrag')}><PlusCircle size={18}/> Neuer Auftrag</button><button onClick={()=>navigate('Dokumente')}><FileCheck2 size={18}/> Dokument prüfen</button><button onClick={()=>navigate('Rechnungen')}><Receipt size={18}/> Rechnungen</button><button onClick={()=>navigate('Kennzeichen')}><CarFront size={18}/> Kennzeichen</button></div></section></div></>}
   {section==='Aufträge'&&<div className="panel"><div className="panel-title"><h2>Alle Aufträge ({filtered.length})</h2><button className="gold-btn" onClick={()=>navigate('Neuer Auftrag')}><PlusCircle size={16}/> Neuer Auftrag</button></div><OrdersTable orders={filtered} onSelect={setSelected}/></div>}
   {section==='Neuer Auftrag'&&<div className="form-wrap"><div className="panel"><h2>1. Fahrzeug- und Halterdaten</h2><div className="form-grid"><label>Fahrzeug / Modell<input value={draft.vehicle} onChange={e=>setDraft({...draft,vehicle:e.target.value})} placeholder="z. B. VW Golf" required/></label><label>Kunde / Autohaus<input value={draft.customer} onChange={e=>setDraft({...draft,customer:e.target.value})} placeholder="Kundenname" required/></label><label>Kennzeichen<input value={draft.plate} onChange={e=>setDraft({...draft,plate:e.target.value})} placeholder="FB · TA 123"/></label><label>Vorgangsart<select value={draft.type} onChange={e=>setDraft({...draft,type:e.target.value})}>{['Neuzulassung','Ummeldung','Abmeldung','Wiederzulassung','Halterwechsel'].map(t=><option key={t}>{t}</option>)}</select></label></div><button className="gold-btn" onClick={add}>Demo-Auftrag anlegen <ArrowRight size={17}/></button><p className="muted">Nur lokale Demo-Daten. Die Eingaben werden noch nicht auf einem Server gespeichert.</p></div><div className="panel"><h2>Auftragszusammenfassung</h2><p><strong>Fahrzeug:</strong> {draft.vehicle||'Noch nicht angegeben'}</p><p><strong>Kunde:</strong> {draft.customer||'Noch nicht angegeben'}</p><p><strong>Vorgang:</strong> {draft.type}</p><div className="alert"><AlertCircle size={20}/> Dokumentenupload und Pflichtfeldprüfung folgen mit dem Backend.</div></div></div>}
   {!['Dashboard','Aufträge','Neuer Auftrag'].includes(section)&&<div className="panel placeholder"><div className="placeholder-icon"><PackageCheck size={34}/></div><h2>{section}</h2><p>{modules[section]}</p><p>Dieser Menübereich ist als nächster Entwicklungsschritt vorgesehen. Die Navigation und das einheitliche Office-Design stehen bereits.</p><button className="gold-btn" onClick={()=>navigate('Dashboard')}>Zum Dashboard <ArrowRight size={17}/></button></div>}
   </main><footer>© {new Date().getFullYear()} TARIQ Zulassungsservice UG (haftungsbeschränkt) · Demo-Oberfläche, nicht produktiv</footer>
  </div>
  {active&&<div className="drawer-cover" onClick={()=>setSelected(null)}><aside className="drawer" onClick={e=>e.stopPropagation()}><button className="drawer-close" onClick={()=>setSelected(null)} aria-label="Schließen"><X size={20}/></button><h2>Vorgangsdetails</h2><p className={'status '+color(active.status)}>{active.status}</p><h3>{active.vehicle}</h3><p><strong>Auftrag:</strong> {active.id}</p><p><strong>Kunde:</strong> {active.customer}</p><p><strong>Vorgangsart:</strong> {active.type}</p><p><strong>Kennzeichen:</strong> {active.plate||'Offen'}</p><p><strong>Bearbeiter:</strong> {active.employee}</p><hr/><label>Status ändern<select value={active.status} onChange={e=>changeStatus(active.id,e.target.value)}>{['Neu','Abgeholt','In Prüfung','Unterlagen fehlen','Bei Behörde','Fertig'].map(s=><option key={s}>{s}</option>)}</select></label><p className="muted">Änderung erfolgt derzeit nur im Browser. Später werden Händler und Fahrer automatisch informiert.</p><button className="gold-btn" onClick={()=>setSelected(null)}>Schließen <Check size={16}/></button></aside></div>}
 </div>;
}
function OrdersTable({orders,onSelect}:{orders:Order[];onSelect:(id:string)=>void}){return <div className="table-scroll"><table><thead><tr><th>Vorgang</th><th>Fahrzeug</th><th>Vorgangsart</th><th>Kunde</th><th>Kennzeichen</th><th>Status</th><th>Bearbeiter</th><th></th></tr></thead><tbody>{orders.map(o=><tr key={o.id} onClick={()=>onSelect(o.id)}><td className="mono">{o.id}</td><td><strong>{o.vehicle}</strong></td><td>{o.type}</td><td>{o.customer}</td><td>{o.plate||'–'}</td><td><span className={'status '+color(o.status)}>{o.status}</span></td><td>{o.employee}</td><td><ExternalLink size={15}/></td></tr>)}</tbody></table>{orders.length===0&&<p className="muted">Keine passenden Aufträge gefunden.</p>}</div>}
