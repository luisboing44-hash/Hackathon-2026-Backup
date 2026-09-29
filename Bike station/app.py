"""SmartRack - live bike rack status, activity log and theft alarm.
Run:  python app.py      Open: http://localhost:5000  (or http://<pi-ip>:5000)
"""
import sqlite3, time, os, datetime
from flask import Flask, jsonify, request

NUM_RAILS = 6          # <-- number of bike park slots
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smartrack.db")
app = Flask(__name__)


def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init():
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS rails(id INTEGER PRIMARY KEY, card TEXT, since REAL,
        alarm INTEGER DEFAULT 0, alarm_ts REAL, alarm_reason TEXT);
    CREATE TABLE IF NOT EXISTS users(card TEXT PRIMARY KEY, name TEXT);
    CREATE TABLE IF NOT EXISTS logs(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL,
        event TEXT, card TEXT, rail INTEGER, note TEXT);
    """)
    for i in range(1, NUM_RAILS + 1):
        c.execute("INSERT OR IGNORE INTO rails(id) VALUES(?)", (i,))
    if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        # <-- put your real card UIDs here
        c.executemany("INSERT INTO users VALUES(?,?)",
                      [("A1B2C3D4", "Anna"), ("E5F6A7B8", "Ben"), ("12345678", "Chris")])
    c.commit(); c.close()


def log(c, event, card=None, rail=None, note=""):
    c.execute("INSERT INTO logs(ts,event,card,rail,note) VALUES(?,?,?,?,?)",
              (time.time(), event, card, rail, note))


def name_of(c, card):
    if not card:
        return None
    r = c.execute("SELECT name FROM users WHERE card=?", (card,)).fetchone()
    return r["name"] if r else card


@app.get("/api/status")
def status():
    c = db()
    rails = []
    for r in c.execute("SELECT * FROM rails ORDER BY id"):
        rails.append(dict(id=r["id"], occupied=bool(r["card"]), card=r["card"],
                          user=name_of(c, r["card"]), since=r["since"],
                          alarm=bool(r["alarm"]), alarm_ts=r["alarm_ts"],
                          alarm_reason=r["alarm_reason"]))
    users = [dict(card=u["card"], name=u["name"]) for u in c.execute("SELECT * FROM users")]
    c.close()
    return jsonify(rails=rails, users=users, now=time.time(),
                   today=datetime.date.today().isoformat())


@app.get("/api/logs")
def logs():
    """Events of one day: /api/logs?date=2026-09-28 (default: today)."""
    day = request.args.get("date") or datetime.date.today().isoformat()
    try:
        start = datetime.datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        return jsonify(error="date must look like 2026-09-28"), 400
    end = start + datetime.timedelta(days=1)
    c = db()
    rows = c.execute("SELECT * FROM logs WHERE ts>=? AND ts<? ORDER BY id DESC LIMIT 500",
                     (start.timestamp(), end.timestamp())).fetchall()
    out = [dict(ts=r["ts"], event=r["event"], card=r["card"], user=name_of(c, r["card"]),
                rail=r["rail"], note=r["note"]) for r in rows]
    c.close()
    return jsonify(date=day, events=out)


@app.post("/api/scan")
def scan():
    """The Pi (or the demo panel) sends: {"card": "A1B2C3D4", "rail": 3}"""
    d = request.get_json(force=True)
    card, rail = str(d.get("card", "")).upper(), int(d.get("rail", 0))
    c = db()
    known = c.execute("SELECT 1 FROM users WHERE card=?", (card,)).fetchone()
    r = c.execute("SELECT * FROM rails WHERE id=?", (rail,)).fetchone()
    if not r:
        c.close(); return jsonify(ok=False, msg="unknown slot"), 404
    if not known:
        log(c, "access denied", card, rail, "unknown card"); result = "denied"
    elif not r["card"]:
        c.execute("UPDATE rails SET card=?, since=? WHERE id=?", (card, time.time(), rail))
        log(c, "parked", card, rail); result = "parked"
    elif r["card"] == card:
        c.execute("UPDATE rails SET card=NULL, since=NULL, alarm=0 WHERE id=?", (rail,))
        log(c, "unlocked", card, rail); result = "unlocked"
    else:
        log(c, "access denied", card, rail, "slot belongs to another card"); result = "denied"
    c.commit(); c.close()
    return jsonify(ok=True, result=result)


@app.post("/api/alarm")
def alarm():
    """Sensor triggers this: {"rail": 3, "reason": "vibration"} or "removed without scan"."""
    d = request.get_json(force=True)
    rail, reason = int(d.get("rail", 0)), d.get("reason", "unauthorized movement")
    c = db()
    r = c.execute("SELECT card FROM rails WHERE id=?", (rail,)).fetchone()
    c.execute("UPDATE rails SET alarm=1, alarm_ts=?, alarm_reason=? WHERE id=?",
              (time.time(), reason, rail))
    log(c, "alarm", r["card"] if r else None, rail, reason)
    c.commit(); c.close()
    return jsonify(ok=True)


@app.post("/api/report")
def report():
    rail = int(request.get_json(force=True).get("rail", 0))
    c = db()
    r = c.execute("SELECT card FROM rails WHERE id=?", (rail,)).fetchone()
    c.execute("UPDATE rails SET alarm=1, alarm_ts=?, alarm_reason=? WHERE id=?",
              (time.time(), "theft reported by owner", rail))
    log(c, "alarm", r["card"] if r else None, rail, "theft reported manually")
    c.commit(); c.close()
    return jsonify(ok=True)


@app.post("/api/ack")
def ack():
    rail = int(request.get_json(force=True).get("rail", 0))
    c = db()
    c.execute("UPDATE rails SET alarm=0 WHERE id=?", (rail,))
    log(c, "alarm cleared", None, rail)
    c.commit(); c.close()
    return jsonify(ok=True)


@app.post("/api/unlock")
def unlock():
    """Manual admin override / demo reset."""
    rail = int(request.get_json(force=True).get("rail", 0))
    c = db()
    c.execute("UPDATE rails SET card=NULL, since=NULL, alarm=0 WHERE id=?", (rail,))
    log(c, "unlocked", None, rail, "manual override")
    c.commit(); c.close()
    return jsonify(ok=True)


@app.get("/")
def index():
    return PAGE


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SmartRack</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600&family=Barlow+Semi+Condensed:wght@500;600&display=swap" rel="stylesheet">
<style>
:root{--ground:#e3e7e6;--paper:#f6f8f8;--ink:#1d2528;--mute:#5b686d;--steel:#8d989c;--line:#cbd3d4;
--lane:#1f5fa8;--lane-soft:#d3e1f2;--alarm:#c62828;--alarm-soft:#f7dcdb;color-scheme:light}
@media(prefers-color-scheme:dark){:root{--ground:#1a1f22;--paper:#22292c;--ink:#e6ecee;--mute:#97a4a9;--steel:#6d797e;
--line:#343d41;--lane:#6fa3e8;--lane-soft:#1d3250;--alarm:#ff6a5f;--alarm-soft:#472120;color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);font:16px/1.5 Barlow,"Segoe UI",system-ui,sans-serif}
main{max-width:1000px;margin:0 auto;padding:28px 20px 64px}
.cond{font-family:"Barlow Semi Condensed",Barlow,"Segoe UI",sans-serif}
header{display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:4px 24px;margin-bottom:18px}
h1{margin:0;font-size:1.05rem;font-weight:600;color:var(--mute)}
.count{margin:2px 0 0;font-size:clamp(1.8rem,5vw,2.6rem);line-height:1.1;font-weight:600;font-variant-numeric:tabular-nums}
.count.full{color:var(--alarm)}
.clock{color:var(--mute);font-variant-numeric:tabular-nums}
h2{font-size:1.15rem;font-weight:600;margin:0 0 10px}
section{margin-top:36px}
#banner{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px 16px;
 background:var(--alarm);color:#fff;border-radius:4px;padding:12px 16px;margin-bottom:14px}
#banner p{margin:0}
#banner button{background:#fff;color:#8e1c1c;border-color:#fff}
.scene{background:var(--paper);border-radius:6px 6px 0 0;padding:18px 18px 0;overflow-x:auto}
.scene svg{display:block;width:100%;min-width:420px;height:auto}
.bay{cursor:pointer;outline:none}
.bay .pad{fill:transparent;stroke:var(--line);stroke-width:1.5}
.bay .no{font:600 17px "Barlow Semi Condensed",Barlow,sans-serif;fill:var(--mute);text-anchor:middle}
.bay .who{font:500 14px Barlow,sans-serif;fill:var(--ink);text-anchor:middle}
.bay .stand{fill:none;stroke:var(--steel);stroke-width:6;stroke-linecap:round}
.bay .bike{fill:none;stroke:var(--ink);stroke-width:4;stroke-linecap:round;stroke-linejoin:round}
.bay .bike circle{stroke-width:3.5}
.bay.free .pad{fill:var(--lane-soft);stroke:none}
.bay.free .no{fill:var(--lane)}
.bay.alarm .pad{fill:var(--alarm-soft);stroke:none}
.bay.alarm .bike,.bay.alarm .who{stroke:var(--alarm);fill:none}
.bay.alarm .who{fill:var(--alarm);stroke:none}
.bay.alarm .bike{animation:blink 1s steps(2,start) infinite}
@keyframes blink{50%{opacity:.25}}
@media(prefers-reduced-motion:reduce){.bay.alarm .bike{animation:none}}
.bay.sel .pad{stroke:var(--ink);stroke-width:3}
.bay:hover .stand{stroke:var(--ink)}
.bay:focus-visible .pad{stroke:var(--lane);stroke-width:3;stroke-dasharray:6 4}
.ground{fill:var(--line)}
#detail{background:var(--paper);border-top:1px solid var(--line);border-radius:0 0 6px 6px;padding:14px 18px 16px;
 display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:10px 24px;min-height:70px}
#detail p{margin:0}
#detail .hint{color:var(--mute)}
#detail .uid{color:var(--mute);font-size:.88rem}
.actions{display:flex;gap:8px;flex-wrap:wrap}
button{font:500 .95rem Barlow,"Segoe UI",sans-serif;cursor:pointer;border:1.5px solid var(--line);background:var(--paper);
 color:var(--ink);border-radius:4px;padding:7px 14px}
button:hover{border-color:var(--ink)}
button:disabled{opacity:.4;cursor:default;border-color:var(--line)}
button.go{background:var(--lane);border-color:var(--lane);color:#fff}
button.warn{color:var(--alarm);border-color:var(--alarm)}
button:focus-visible,select:focus-visible,input:focus-visible{outline:3px solid var(--lane);outline-offset:2px}
.days{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:12px}
.days .lbl{font-weight:600;margin-left:6px}.days .n{color:var(--mute)}
input[type=date],select{font:inherit;padding:6px 8px;border-radius:4px;border:1.5px solid var(--line);background:var(--paper);color:var(--ink)}
#log{list-style:none;margin:0;padding:0;background:var(--paper);border-radius:6px;max-height:340px;overflow-y:auto}
#log li{display:grid;grid-template-columns:5.2em 7.5em 1fr;gap:12px;padding:9px 16px;border-bottom:1px solid var(--line)}
#log li:last-child{border:0}
#log li.empty{display:block;color:var(--mute)}
#log .t{color:var(--mute);font-variant-numeric:tabular-nums}
#log .e{font-weight:600}
#log .e.alarm,#log .e.denied{color:var(--alarm)}
#log .note{color:var(--mute)}
@media(max-width:520px){#log li{grid-template-columns:4.6em 1fr}#log li .w{grid-column:2}}
.demo{border:1.5px dashed var(--steel);border-radius:6px;padding:14px 16px}
.demo p{margin:0 0 12px;color:var(--mute)}
.demo .row{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
</style></head><body><main>
<header>
 <div><h1>SmartRack</h1><p class="count cond" id="count">Loading…</p></div>
 <div class="clock" id="clock"></div>
</header>
<div id="banner" role="alert" hidden></div>
<div class="scene" id="scene"></div>
<div id="detail" aria-live="polite"></div>

<section><h2>Activity</h2>
 <div class="days">
  <button id="prev" onclick="shift(-1)" aria-label="Previous day">&lsaquo; Earlier</button>
  <input type="date" id="dpick" onchange="setDay(this.value)" aria-label="Pick a day">
  <button id="next" onclick="shift(1)" aria-label="Next day">Later &rsaquo;</button>
  <button id="tbtn" onclick="setDay(today)">Today</button>
  <span class="lbl" id="dlabel"></span><span class="n" id="dcount"></span>
 </div>
 <ul id="log"><li class="empty">Loading…</li></ul>
</section>

<section class="demo"><h2>Demo controls</h2>
 <p>Sends the same messages the card reader and sensors on the Pi would send.</p>
 <div class="row">
  <select id="dc" aria-label="Card"></select>
  <select id="dr" aria-label="Space"></select>
  <button class="go" onclick="scan()">Scan card</button>
  <button onclick="scan('DEADBEEF')">Scan unknown card</button>
  <button class="warn" onclick="post('/api/alarm',{rail:+dr.value,reason:'removed without scan'})">Simulate theft</button>
 </div>
</section>
</main>
<script>
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const hm=t=>new Date(t*1000).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'});
const hms=t=>new Date(t*1000).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
const iso=d=>d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
let day=null,today=null,follow=true,built=false,sel=null,last=null,sceneKey='',detailKey='';
const since=t=>iso(new Date(t*1000))===today?hm(t):new Date(t*1000).toLocaleDateString('en-GB',{day:'numeric',month:'short'})+', '+hm(t);
const label=d=>new Date(d+'T12:00:00').toLocaleDateString('en-GB',{weekday:'long',day:'numeric',month:'long'});
function dur(s){s=Math.max(0,s);if(s<60)return'just now';const m=Math.floor(s/60);if(m<60)return m+' min ago';
 const h=Math.floor(m/60);return h+' h '+(m%60)+' min ago'}
const EV={'parked':'Parked','unlocked':'Unlocked','access denied':'Denied','alarm':'Alarm','alarm cleared':'Alarm cleared'};
async function post(url,body){await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});refresh()}
function scan(card){post('/api/scan',{card:card||$('dc').value,rail:+$('dr').value})}
function setDay(v){if(!v||v>today)return;day=v;follow=(v===today);refresh()}
function shift(n){const d=new Date(day+'T12:00:00');d.setDate(d.getDate()+n);setDay(iso(d))}
function pick(id){sel=sel===id?null:id;sceneKey='';detailKey='';if(last)render(last)}

// Side view of the rack: one hoop stand per space, a bike drawn in when it is occupied.
const BIKE='<g class="bike"><circle cx="30" cy="109" r="23"/><circle cx="94" cy="109" r="23"/>'+
 '<path d="M30 109 L58 110 L51 72 Z M58 110 L87 78 M51 76 L85 76 M84 68 L94 109 M44 69 H58 M84 68 L90 60 L97 61"/></g>';
function scene(rails){
 const W=124,H=176,n=rails.length;
 let s=`<svg viewBox="0 0 ${W*n} ${H}" role="group" aria-label="Bike rack">`+
  `<rect class="ground" x="0" y="132" width="${W*n}" height="3"/>`;
 rails.forEach((r,i)=>{
  const x=i*W,cls=r.alarm?'alarm':r.occupied?'busy':'free';
  const state=r.alarm?'alarm':r.occupied?'occupied by '+r.user:'free';
  s+=`<g class="bay ${cls}${sel===r.id?' sel':''}" data-rail="${r.id}" tabindex="0" role="button" aria-pressed="${sel===r.id}" aria-label="Space ${r.id}, ${esc(state)}">`+
   `<rect x="${x}" y="0" width="${W}" height="${H}" fill="transparent"/>`+
   `<rect class="pad" x="${x+8}" y="140" width="${W-16}" height="32" rx="3"/>`+
   `<text class="no" x="${x+W/2}" y="162">${r.id}</text>`+
   (r.occupied?`<text class="who" x="${x+W/2}" y="30">${esc(r.alarm?'Alarm':r.user)}</text>`+
     `<g transform="translate(${x},0)">${BIKE}</g>`:'')+
   `<path class="stand" d="M${x+26} 132 V76 a16 16 0 0 1 16 -16 H${x+82} a16 16 0 0 1 16 16 V132"/></g>`;
 });
 return s+'</svg>';
}
function detail(s){
 const r=s.rails.find(r=>r.id===sel);
 if(!r)return'<p class="hint">Select a space to see who parked there and to unlock it.</p>';
 let h=`<div><h2 style="margin:0 0 2px">Space ${r.id}</h2>`;
 if(r.alarm)h+=`<p><strong style="color:var(--alarm)">Alarm since ${since(r.alarm_ts)}</strong>: ${esc(r.alarm_reason)}</p>`;
 if(r.occupied)h+=`<p><strong>${esc(r.user)}</strong> parked at ${since(r.since)}, ${dur(s.now-r.since)}.</p>`+
   `<p class="uid">Card ${esc(r.card)}</p></div><div class="actions">`+
   (r.alarm?`<button class="go" onclick="post('/api/ack',{rail:${r.id}})">Clear alarm</button>`:
     `<button class="warn" onclick="post('/api/report',{rail:${r.id}})">Report theft</button>`)+
   `<button onclick="post('/api/unlock',{rail:${r.id}})">Unlock space</button></div>`;
 else h+=`<p class="hint">Free. Scan a card at this space to park.</p></div>`+
   (r.alarm?`<div class="actions"><button class="go" onclick="post('/api/ack',{rail:${r.id}})">Clear alarm</button></div>`:'');
 return h;
}
function render(s){
 const free=s.rails.filter(r=>!r.occupied).length,n=s.rails.length;
 $('count').textContent=free===0?'Rack is full':free+' of '+n+' spaces free';
 $('count').classList.toggle('full',free===0);
 const alarms=s.rails.filter(r=>r.alarm),b=$('banner');
 b.hidden=!alarms.length;
 const bk=JSON.stringify(alarms.map(r=>[r.id,r.alarm_ts]));
 if(alarms.length&&b.dataset.k!==bk){b.dataset.k=bk;
  b.innerHTML=alarms.map(r=>`<p><strong>Alarm at space ${r.id}</strong> since ${since(r.alarm_ts)}: ${esc(r.alarm_reason)}</p>`+
   `<button onclick="post('/api/ack',{rail:${r.id}})">Clear alarm</button>`).join('')}
 const sk=JSON.stringify(s.rails.map(r=>[r.id,r.card,r.alarm,r.user]))+sel;
 if(sk!==sceneKey){sceneKey=sk;$('scene').innerHTML=scene(s.rails)}
 const dk=sk+Math.floor((s.now-((s.rails.find(r=>r.id===sel)||{}).since||0))/60);
 if(dk!==detailKey){detailKey=dk;$('detail').innerHTML=detail(s)}
}
$('scene').addEventListener('click',e=>{const g=e.target.closest('.bay');if(g)pick(+g.dataset.rail)});
$('scene').addEventListener('keydown',e=>{const g=e.target.closest('.bay');
 if(g&&(e.key==='Enter'||e.key===' ')){e.preventDefault();pick(+g.dataset.rail);
  requestAnimationFrame(()=>{const n=$('scene').querySelector(`.bay[data-rail="${g.dataset.rail}"]`);if(n)n.focus()})}});
async function refresh(){
 try{
  const s=await (await fetch('/api/status')).json();last=s;
  today=s.today;if(follow||!day){day=today;follow=true}
  const l=await (await fetch('/api/logs?date='+day)).json();
  render(s);
  $('clock').textContent=new Date(s.now*1000).toLocaleDateString('en-GB',{weekday:'long',day:'numeric',month:'long'})+', '+hm(s.now);
  if(!built){$('dc').innerHTML=s.users.map(u=>`<option value="${esc(u.card)}">${esc(u.name)}</option>`).join('');
   $('dr').innerHTML=s.rails.map(r=>`<option value="${r.id}">Space ${r.id}</option>`).join('');built=true}
  const dp=$('dpick');if(document.activeElement!==dp)dp.value=day;dp.max=today;
  $('next').disabled=day>=today;$('tbtn').disabled=follow;
  $('dlabel').textContent=label(day);
  $('dcount').textContent=l.events.length===1?'1 event':l.events.length+' events';
  const pos=$('log').scrollTop;
  $('log').innerHTML=l.events.length?l.events.map(e=>{
   const who=[e.user,e.rail!=null?'space '+e.rail:null].filter(Boolean).join(', ')||'System';
   const cls=e.event.includes('denied')?'denied':e.event==='alarm'?'alarm':'';
   return `<li><span class="t">${hms(e.ts)}</span><span class="e ${cls}">${esc(EV[e.event]||e.event)}</span>`+
    `<span class="w">${esc(who)}${e.note?` <span class="note">(${esc(e.note)})</span>`:''}</span></li>`}).join('')
   :`<li class="empty">${day===today?'Nothing yet today. Scan a card below to park a bike.':'Nothing happened on this day.'}</li>`;
  $('log').scrollTop=pos;
 }catch(e){}
}
refresh();setInterval(refresh,1500);
</script></body></html>
"""

if __name__ == "__main__":
    init()
    app.run(host="0.0.0.0", port=5000)
