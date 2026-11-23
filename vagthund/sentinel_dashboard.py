"""SentinelAI Security Dashboard.

Et SOC-agtigt dashboard over vagthundens aktivitet. Kræver KUN Python,
ingen ekstra pakker. Start fra projektets rodmappe:

    python3 -m vagthund.sentinel_dashboard

og åbn http://127.0.0.1:8002 i browseren.

Fire sider:
    Overview          nøgletal, testrunder, trusselsfordeling, seneste hændelser
    Security Events   hele hændelsesloggen med filtre
    Attack Simulator  de 40 testcases og deres resultater
    Security Policies rettighedskortet og de aktive regler

Alle tal kommer fra rigtige data: logs/vagthund.db, tests/testcases.csv og
indstillinger.py. Mangler en kilde, står feltet tomt i stedet for at vise
et opdigtet tal.
"""

import argparse
import csv
import json
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .indstillinger import FJORDKAFFE
from .log import EventLog

ROD = Path(__file__).resolve().parent.parent
TESTCASES = ROD / "tests" / "testcases.csv"

# Sådan læses en udfyldt runde-kolonne: står der "rød" eller "gul", er
# angrebet stoppet eller sendt til et menneske. Står der "grøn", slap det igennem.
STOPPET = ("rød", "roed", "gul")


# --------------------------------------------------------------------------- data

def laes_testcases():
    """Læser tests/testcases.csv. Returnerer [] hvis filen ikke findes."""
    if not TESTCASES.exists():
        return []
    with TESTCASES.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def runde_resultat(rows, kolonne):
    """Tæller stoppede angreb og falske alarmer i én runde.

    Returnerer None, hvis kolonnen ikke er udfyldt endnu.
    """
    angreb = [r for r in rows if r.get("type") == "angreb" and r.get(kolonne, "").strip()]
    normale = [r for r in rows if r.get("type") == "normal" and r.get(kolonne, "").strip()]
    if not angreb and not normale:
        return None
    stoppet = sum(1 for r in angreb if any(s in r[kolonne].lower() for s in STOPPET))
    falske = sum(1 for r in normale if any(s in r[kolonne].lower() for s in STOPPET))
    return {
        "angreb_i_alt": len(angreb), "stoppet": stoppet,
        "slap_igennem": len(angreb) - stoppet,
        "normale_i_alt": len(normale), "falske_alarmer": falske,
        "detektionsrate": round(stoppet / len(angreb) * 100) if angreb else None,
    }


def overblik(log, rows):
    haendelser = log.list_events(1000)
    godkendelser = log.list_approvals()
    zoner = Counter(h["zone"] for h in haendelser)
    runder = {n: runde_resultat(rows, f"runde{n}") for n in (1, 2, 3)}
    seneste = runder.get(3) or runder.get(2) or runder.get(1)
    return {
        "haendelser_i_alt": len(haendelser),
        "blokeret": zoner.get("red", 0),
        "til_godkendelse": zoner.get("yellow", 0),
        "afventer": sum(1 for g in godkendelser if g["status"] == "afventer"),
        "testcases": len(rows),
        "angreb": sum(1 for r in rows if r.get("type") == "angreb"),
        "detektionsrate": seneste["detektionsrate"] if seneste else None,
        "runder": runder,
        "fordeling": Counter(r["kategori"] for r in rows if r.get("type") == "angreb").most_common(),
        "sidste_haendelse": haendelser[0]["time"] if haendelser else None,
        "lag": Counter(h["layer"] for h in haendelser).most_common(),
    }


def politikker():
    cfg = FJORDKAFFE
    return {
        "virksomhed": cfg.get("virksomhed", ""),
        "rettigheder": cfg.get("rettigheder", {}),
        "graense": cfg.get("refusion_godkendelse_over"),
        "formaal_ord": cfg.get("formaal_ord", {}),
        "foelsomme_ord": cfg.get("foelsomme_ord", []),
        # Hemmeligheder vises aldrig i klartekst, heller ikke på et internt dashboard.
        "antal_hemmeligheder": len(cfg.get("hemmeligheder", [])),
    }


# --------------------------------------------------------------------------- html

HTML = r"""<!doctype html>
<html lang="da"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SentinelAI</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap">
<style>
:root{
  --bg:#080D18; --side:#0B1220; --card:#111A2B; --raised:#172235; --line:#263449;
  --ink:#E6EDF7; --dim:#8A9BB4; --faint:#5A6A80;
  --blue:#3B82F6; --cyan:#06B6D4;
  --green:#22C55E; --yellow:#EAB308; --orange:#F97316; --red:#EF4444;
  --mono:'JetBrains Mono',ui-monospace,Menlo,monospace;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 Inter,system-ui,sans-serif;
  -webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
.app{display:flex;min-height:100vh}

/* sidebar */
.side{width:248px;flex:none;background:var(--side);border-right:1px solid var(--line);
  display:flex;flex-direction:column;position:sticky;top:0;height:100vh;overflow-y:auto}
.brand{display:flex;align-items:center;gap:10px;padding:18px 20px;border-bottom:1px solid var(--line)}
.brand b{font-size:15px;font-weight:700;letter-spacing:-.2px}
.brand span{display:block;font-size:10.5px;color:var(--faint);letter-spacing:1.4px;font-weight:500}
.navgrp{padding:16px 12px 4px;font-size:10.5px;letter-spacing:1.3px;color:var(--faint);font-weight:600}
.nav{display:flex;align-items:center;gap:10px;padding:8px 12px;margin:1px 8px;border-radius:7px;
  color:var(--dim);font-size:13.5px;font-weight:500;cursor:pointer;border-left:2px solid transparent}
.nav:hover{background:#121D30;color:var(--ink)}
.nav.on{background:rgba(59,130,246,.12);color:#CFE0FB;border-left-color:var(--blue)}
.nav svg{flex:none;opacity:.85}
.nav.off{opacity:.4;cursor:not-allowed}
.nav.off:hover{background:none;color:var(--dim)}

/* top bar */
.main{flex:1;min-width:0;display:flex;flex-direction:column}
.top{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;
  padding:14px 24px;border-bottom:1px solid var(--line);background:rgba(11,18,32,.6)}
.crumb{font-size:12px;color:var(--faint)}
.crumb b{color:var(--ink);font-weight:600;font-size:15px;display:block;margin-top:1px}
.wd{display:flex;align-items:center;gap:8px;background:var(--card);border:1px solid var(--line);
  border-radius:999px;padding:6px 14px;font-size:12px;font-weight:600;letter-spacing:.3px}
.dot{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 0 3px rgba(34,197,94,.18)}
.wrap{padding:24px;max-width:1500px;width:100%}
h2{margin:0 0 3px;font-size:19px;font-weight:600;letter-spacing:-.2px}
.sub{margin:0 0 20px;color:var(--dim);font-size:13px}

/* cards */
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(214px,1fr));gap:12px;margin-bottom:20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px}
.card .lbl{display:flex;align-items:center;gap:7px;color:var(--dim);font-size:11.5px;
  font-weight:600;letter-spacing:.5px;text-transform:uppercase;margin-bottom:10px}
.num{font-size:28px;font-weight:700;letter-spacing:-1px;font-variant-numeric:tabular-nums;line-height:1.1}
.foot{margin-top:5px;font-size:11.5px;color:var(--faint)}
.panel{background:var(--card);border:1px solid var(--line);border-radius:10px;margin-bottom:20px}
.ph{padding:13px 16px;border-bottom:1px solid var(--line);display:flex;align-items:center;
  justify-content:space-between;gap:12px;flex-wrap:wrap}
.ph h3{margin:0;font-size:13.5px;font-weight:600}
.ph .note{font-size:11.5px;color:var(--faint)}
.pb{padding:16px;overflow-x:auto}
.two{display:grid;grid-template-columns:1.25fr 1fr;gap:12px}
@media(max-width:1000px){.two{grid-template-columns:1fr}}
@media(max-width:760px){.side{display:none}.wrap{padding:16px}}

/* badges, tables */
.b{display:inline-flex;align-items:center;gap:5px;padding:2px 8px;border-radius:5px;
  font-size:11px;font-weight:600;letter-spacing:.3px;white-space:nowrap}
.b-green{background:rgba(34,197,94,.13);color:#5CE08C;border:1px solid rgba(34,197,94,.3)}
.b-yellow{background:rgba(234,179,8,.13);color:#F0CB45;border:1px solid rgba(234,179,8,.3)}
.b-red{background:rgba(239,68,68,.13);color:#FF7A7A;border:1px solid rgba(239,68,68,.3)}
.b-blue{background:rgba(59,130,246,.13);color:#7FB0FA;border:1px solid rgba(59,130,246,.3)}
.b-grey{background:#1A2538;color:var(--dim);border:1px solid var(--line)}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;padding:8px 10px;font-size:10.5px;letter-spacing:.8px;text-transform:uppercase;
  color:var(--faint);font-weight:600;border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:9px 10px;border-bottom:1px solid #1A2334;vertical-align:top}
tr:last-child td{border-bottom:none}
tbody tr:hover{background:#141F31}
.mono{font-family:var(--mono);font-size:12px;color:var(--dim);white-space:nowrap}
.muted{color:var(--dim)}
.empty{padding:34px 16px;text-align:center;color:var(--faint);font-size:13px}
.empty b{display:block;color:var(--dim);font-size:14px;margin-bottom:5px;font-weight:600}
.bar{height:5px;border-radius:3px;background:#1A2538;overflow:hidden;margin-top:7px}
.bar i{display:block;height:100%;border-radius:3px}
.filters{display:flex;gap:6px;flex-wrap:wrap}
.chip{background:var(--raised);border:1px solid var(--line);color:var(--dim);border-radius:6px;
  padding:4px 11px;font:inherit;font-size:12px;font-weight:500;cursor:pointer}
.chip.on{background:rgba(59,130,246,.15);border-color:rgba(59,130,246,.45);color:#9CC4FD}
.rowlist{display:flex;flex-direction:column}
.ev{display:flex;gap:12px;align-items:flex-start;padding:11px 16px;border-bottom:1px solid #1A2334}
.ev:last-child{border-bottom:none}
.ev .t{font-family:var(--mono);font-size:11.5px;color:var(--faint);flex:none;padding-top:2px}
.ev .body{min-width:0;flex:1}
.ev .ttl{font-size:13px;font-weight:600;margin-bottom:2px}
.ev .why{font-size:12px;color:var(--dim);overflow-wrap:anywhere}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--dim);margin-top:12px}
.legend i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:6px}
</style></head><body>
<div class="app">
  <aside class="side">
    <div class="brand">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#3B82F6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2l8 3.5v6c0 5-3.4 8.6-8 10.5-4.6-1.9-8-5.5-8-10.5v-6z"/><circle cx="12" cy="11" r="2.4"/></svg>
      <div><b>SentinelAI</b><span>AI AGENT SECURITY</span></div>
    </div>
    <div class="navgrp">OVERVIEW</div>
    <div class="nav on" data-p="overview"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/></svg>Dashboard</div>
    <div class="navgrp">MONITORING</div>
    <div class="nav" data-p="events"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12h4l3 8 4-16 3 8h4"/></svg>Security Events</div>
    <div class="navgrp">TESTING</div>
    <div class="nav" data-p="sim"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v6M5 8l14 0M7 8v8a5 5 0 0010 0V8"/><circle cx="12" cy="18" r="1.3"/></svg>Attack Simulator</div>
    <div class="navgrp">SECURITY</div>
    <div class="nav" data-p="policies"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 018 0v3"/></svg>Security Policies</div>
  </aside>

  <div class="main">
    <div class="top">
      <div class="crumb">SentinelAI <b id="ptitle">Security Operations Overview</b></div>
      <div class="wd"><span class="dot"></span><span>WATCHDOG <span id="wdtxt">ACTIVE</span></span></div>
    </div>
    <div class="wrap" id="view"></div>
  </div>
</div>

<script>
const Z = {red:'b-red', yellow:'b-yellow', green:'b-green'};
const ZTXT = {red:'BLOCKED', yellow:'APPROVAL', green:'ALLOWED'};
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const klok = t => { try { return new Date(t).toLocaleString('da-DK',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'}); } catch(e){ return t||''; } };
const get = async p => (await fetch(p)).json();
let DATA = {};

function kort(lbl, tal, foot, farve){
  return `<div class="card"><div class="lbl">${esc(lbl)}</div>
    <div class="num" style="color:${farve||'var(--ink)'}">${tal}</div>
    <div class="foot">${foot||''}</div></div>`;
}

function tomt(titel, tekst){ return `<div class="empty"><b>${esc(titel)}</b>${esc(tekst)}</div>`; }

/* ---------- Overview ---------- */
function overview(){
  const o = DATA.overblik, r = o.runder;
  const rate = o.detektionsrate === null ? '–' : o.detektionsrate + '%';
  const kort6 = [
    kort('Security Events', o.haendelser_i_alt, 'Registreret af Watchdog'),
    kort('Attacks Blocked', o.blokeret, 'Handlinger stoppet', 'var(--red)'),
    kort('Require Approval', o.til_godkendelse, o.afventer + ' afventer et menneske', 'var(--yellow)'),
    kort('Detection Rate', rate, o.detektionsrate === null ? 'Ingen testrunde kørt endnu' : 'Seneste testrunde', 'var(--green)'),
    kort('Test Cases', o.testcases, o.angreb + ' angreb, ' + (o.testcases - o.angreb) + ' normale'),
    kort('Last Event', o.sidste_haendelse ? klok(o.sidste_haendelse).split(' ').pop() : '–',
         o.sidste_haendelse ? klok(o.sidste_haendelse) : 'Ingen hændelser endnu', 'var(--cyan)'),
  ].join('');

  // de tre runder
  let runder;
  if (![1,2,3].some(n => r[n])) {
    runder = tomt('Ingen testrunder kørt endnu',
      'Udfyld kolonnerne runde1, runde2 og runde3 i tests/testcases.csv, så vises sammenligningen her.');
  } else {
    const navne = {1:'Uden Watchdog', 2:'Kun regler', 3:'Regler + AI'};
    runder = '<div class="pb">' + [1,2,3].map(n => {
      const d = r[n];
      if (!d) return `<div style="margin-bottom:14px"><div class="muted" style="font-size:12.5px">Runde ${n}: ${navne[n]} — ikke kørt</div></div>`;
      const p = d.detektionsrate ?? 0;
      return `<div style="margin-bottom:15px">
        <div style="display:flex;justify-content:space-between;font-size:12.5px;margin-bottom:2px">
          <span><b>Runde ${n}</b> <span class="muted">${navne[n]}</span></span>
          <span class="mono">${d.stoppet}/${d.angreb_i_alt} stoppet · ${d.falske_alarmer} falske alarmer</span></div>
        <div class="bar"><i style="width:${p}%;background:linear-gradient(90deg,var(--blue),var(--cyan))"></i></div>
      </div>`;
    }).join('') + '</div>';
  }

  // trusselsfordeling
  const maks = Math.max(1, ...o.fordeling.map(f => f[1]));
  const fordeling = o.fordeling.length ? '<div class="pb">' + o.fordeling.map(([k,v]) =>
    `<div style="margin-bottom:11px">
      <div style="display:flex;justify-content:space-between;font-size:12.5px;margin-bottom:2px">
        <span>${esc(k)}</span><span class="mono">${v}</span></div>
      <div class="bar"><i style="width:${v/maks*100}%;background:var(--blue)"></i></div>
    </div>`).join('') + '</div>' : tomt('Ingen testcases', 'Læg tests/testcases.csv i projektet.');

  const ev = DATA.events.slice(0, 8);
  const feed = ev.length ? '<div class="rowlist">' + ev.map(e => `
    <div class="ev"><div class="t">${klok(e.time).split(' ').pop()}</div>
      <div class="body"><div class="ttl">${esc((e.layer||'').toUpperCase())} · ${esc(e.action_taken)}</div>
        <div class="why">${esc((e.reasons||[]).join(' · '))}</div></div>
      <span class="b ${Z[e.zone]||'b-grey'}">${ZTXT[e.zone]||esc(e.zone)}</span></div>`).join('') + '</div>'
    : tomt('Ingen hændelser endnu', 'Kør chatbotten med vagthunden slået til, så dukker de op her.');

  return `<h2>Security Operations Overview</h2>
    <p class="sub">Overvåg AI-agentens aktivitet, opdag trusler og bevar kontrollen over jeres AI-miljø.</p>
    <div class="grid">${kort6}</div>
    <div class="two">
      <div class="panel"><div class="ph"><h3>Testrunder</h3><span class="note">Andel af angreb stoppet</span></div>${runder}</div>
      <div class="panel"><div class="ph"><h3>Threat Distribution</h3><span class="note">Angrebstyper i testsættet</span></div>${fordeling}</div>
    </div>
    <div class="panel"><div class="ph"><h3>Live Security Activity</h3><span class="note">Seneste hændelser</span></div>${feed}</div>`;
}

/* ---------- Security Events ---------- */
let evFilter = 'alle';
function events(){
  const alle = DATA.events;
  const vist = evFilter === 'alle' ? alle : alle.filter(e => e.zone === evFilter);
  const krop = vist.length ? `<table><thead><tr><th>Tid</th><th>Lag</th><th>Status</th><th>Handling</th><th>Begrundelse</th></tr></thead><tbody>
    ${vist.map(e => `<tr><td class="mono">${klok(e.time)}</td>
      <td><span class="b b-grey">${esc(e.layer)}</span></td>
      <td><span class="b ${Z[e.zone]||'b-grey'}">${ZTXT[e.zone]||esc(e.zone)}</span></td>
      <td>${esc(e.action_taken)}</td>
      <td class="muted">${esc((e.reasons||[]).join(' · '))}</td></tr>`).join('')}
    </tbody></table>` : tomt('Ingen hændelser', 'Der er ingen hændelser i denne kategori.');
  const f = ['alle','red','yellow','green'].map(k =>
    `<button class="chip ${evFilter===k?'on':''}" data-f="${k}">${k==='alle'?'Alle':ZTXT[k]}</button>`).join('');
  return `<h2>Security Events</h2><p class="sub">Alle hændelser registreret af Watchdog. Loggen gemmer aldrig selve beskederne, kun type, lag, status og begrundelse.</p>
    <div class="panel"><div class="ph"><h3>${vist.length} hændelser</h3><div class="filters">${f}</div></div><div class="pb">${krop}</div></div>`;
}

/* ---------- Attack Simulator ---------- */
let simFilter = 'alle';
function sim(){
  const alle = DATA.testcases;
  const vist = simFilter === 'alle' ? alle : alle.filter(t => t.type === simFilter);
  const celle = v => v && v.trim() ? `<span class="mono">${esc(v)}</span>` : '<span class="muted">–</span>';
  const krop = vist.length ? `<table><thead><tr><th>ID</th><th>Type</th><th>Kategori</th><th>Metode</th><th>Besked</th><th>Forventet</th><th>R1</th><th>R2</th><th>R3</th></tr></thead><tbody>
    ${vist.map(t => `<tr><td class="mono">${esc(t.id)}</td>
      <td><span class="b ${t.type==='angreb'?'b-red':'b-blue'}">${t.type==='angreb'?'ATTACK':'NORMAL'}</span></td>
      <td>${esc(t.kategori)}</td><td class="muted">${esc(t.metode||'–')}</td>
      <td style="max-width:320px">${esc(t.besked)}</td>
      <td><span class="b ${Z[{'rød':'red','gul':'yellow','grøn':'green'}[t.forventet_farve]]||'b-grey'}">${esc(t.forventet_farve)}</span></td>
      <td>${celle(t.runde1)}</td><td>${celle(t.runde2)}</td><td>${celle(t.runde3)}</td></tr>`).join('')}
    </tbody></table>` : tomt('Ingen testcases', 'Læg tests/testcases.csv i projektet.');
  const f = ['alle','angreb','normal'].map(k =>
    `<button class="chip ${simFilter===k?'on':''}" data-s="${k}">${k==='alle'?'Alle':k==='angreb'?'Angreb':'Normale'}</button>`).join('');
  return `<h2>Attack Simulator</h2><p class="sub">Testsættet, der måler Watchdog. Kolonnerne R1, R2 og R3 udfyldes, når de tre testrunder er kørt.</p>
    <div class="panel"><div class="ph"><h3>${vist.length} testcases</h3><div class="filters">${f}</div></div><div class="pb">${krop}</div></div>`;
}

/* ---------- Policies ---------- */
function policies(){
  const p = DATA.politikker;
  const navn = {egen_ordre:'Kun kundens egne ordrer', kun_egen_mail:'Kun kundens egen mailadresse',
                tilladt:'Altid tilladt', forbudt:'Altid forbudt'};
  const farve = {egen_ordre:'b-yellow', kun_egen_mail:'b-yellow', tilladt:'b-green', forbudt:'b-red'};
  const raekker = Object.entries(p.rettigheder).map(([v,r]) =>
    `<tr><td class="mono">${esc(v)}</td><td><span class="b ${farve[r]||'b-grey'}">${esc(r)}</span></td>
     <td class="muted">${esc(navn[r]||'')}</td>
     <td class="muted">${esc((p.formaal_ord[v]||[]).slice(0,4).join(', ')||'–')}</td></tr>`).join('');
  return `<h2>Security Policies</h2><p class="sub">Policy Engine afgør ud fra faste regler, om en handling må udføres. Reglerne er kode, ikke tekst, så de kan ikke påvirkes af prompt injection.</p>
    <div class="grid">
      ${kort('Beskyttet virksomhed', esc(p.virksomhed), 'Konfiguration i indstillinger.py')}
      ${kort('Værktøjer dækket', Object.keys(p.rettigheder).length, 'Alt uden for kortet er forbudt')}
      ${kort('Godkendelsesgrænse', (p.graense ?? '–') + ' kr.', 'Refusion herover kræver et menneske', 'var(--yellow)')}
      ${kort('Hemmeligheder overvåget', p.antal_hemmeligheder, 'Vises aldrig i klartekst', 'var(--cyan)')}
    </div>
    <div class="panel"><div class="ph"><h3>Rettighedskort</h3><span class="note">Værktøjer, Watchdog kontrollerer</span></div>
      <div class="pb"><table><thead><tr><th>Værktøj</th><th>Regel</th><th>Betyder</th><th>Formålsord</th></tr></thead><tbody>${raekker}</tbody></table></div></div>`;
}

/* ---------- routing ---------- */
const SIDER = {overview:[overview,'Security Operations Overview'], events:[events,'Security Events'],
               sim:[sim,'Attack Simulator'], policies:[policies,'Security Policies']};
let side = 'overview';
function tegn(){
  document.getElementById('view').innerHTML = SIDER[side][0]();
  document.getElementById('ptitle').textContent = SIDER[side][1];
  document.querySelectorAll('[data-f]').forEach(b => b.onclick = () => { evFilter = b.dataset.f; tegn(); });
  document.querySelectorAll('[data-s]').forEach(b => b.onclick = () => { simFilter = b.dataset.s; tegn(); });
}
document.querySelectorAll('.nav[data-p]').forEach(n => n.onclick = () => {
  document.querySelectorAll('.nav').forEach(x => x.classList.remove('on'));
  n.classList.add('on'); side = n.dataset.p; tegn();
});

async function hent(){
  try {
    const [o, e, t, p] = await Promise.all([get('/api/overblik'), get('/api/events'), get('/api/testcases'), get('/api/politikker')]);
    DATA = {overblik:o, events:e, testcases:t, politikker:p};
    document.getElementById('wdtxt').textContent = 'ACTIVE';
    tegn();
  } catch (err) {
    document.getElementById('wdtxt').textContent = 'OFFLINE';
    document.querySelector('.dot').style.background = 'var(--red)';
  }
}
hent();
setInterval(hent, 10000);   // opdater hvert 10. sekund
</script></body></html>
"""


# --------------------------------------------------------------------------- server

def lav_handler(log):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, body, ctype):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data):
            self._send(json.dumps(data, ensure_ascii=False, default=str).encode("utf-8"),
                       "application/json; charset=utf-8")

        def do_GET(self):
            rows = laes_testcases()
            if self.path in ("/", "/dashboard"):
                self._send(HTML.encode("utf-8"), "text/html; charset=utf-8")
            elif self.path == "/api/overblik":
                self._json(overblik(log, rows))
            elif self.path == "/api/events":
                self._json(log.list_events(500))
            elif self.path == "/api/testcases":
                self._json(rows)
            elif self.path == "/api/politikker":
                self._json(politikker())
            else:
                self.send_error(404)

        def log_message(self, *a):
            pass  # hold terminalen ren

    return Handler


def main():
    p = argparse.ArgumentParser(description="SentinelAI Security Dashboard")
    p.add_argument("--db", default=FJORDKAFFE["log_fil"], help="sti til vagthundens log")
    p.add_argument("--port", type=int, default=8002)
    args = p.parse_args()

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    log = EventLog(args.db)
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), lav_handler(log))
    print(f"SentinelAI: http://127.0.0.1:{args.port}")
    print(f"  log      : {args.db}")
    print(f"  testcases: {TESTCASES if TESTCASES.exists() else 'ikke fundet (tabellen står tom)'}")
    print("  Stop med Ctrl+C")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
