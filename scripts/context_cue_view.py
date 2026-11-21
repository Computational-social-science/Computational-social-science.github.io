"""Render the role-evidence comparison from the reviewed public observations."""

import csv
import json
from io import StringIO


def render_context_cue(data):
    rows = list(csv.DictReader(StringIO(data.decode("utf-8"), newline=""), strict=True))
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    for character, escaped in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026")):
        payload = payload.replace(character, escaped)
    return PAGE.replace("__OBSERVATIONS__", payload)


PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Who did the work? · The Matthew Effect</title>
<link rel="stylesheet" href="../style.css"><link rel="stylesheet" href="../reader.css">
<style>
main.case-study{max-width:70rem;padding-block:clamp(1.5rem,5vw,4rem)}
nav{display:flex;flex-wrap:wrap;justify-content:space-between;gap:.45rem 2rem;font-size:.9rem}
header{margin:2.8rem 0 1.2rem} h1{font:600 clamp(2.15rem,5vw,4.4rem)/1.05 var(--serif);margin:0}
header p{max-width:58ch;margin-top:.7rem;font:1.13rem/1.45 var(--serif)}
.controls{display:flex;flex-wrap:wrap;gap:1rem 2rem;padding:1rem 0 1.3rem;border-bottom:1px solid var(--rule)}
label,summary{font:.9rem/1.5 var(--sans);color:var(--accent)} label{display:grid;gap:.35rem;font-weight:600;max-width:100%}
select{max-width:100%;font:inherit;color:var(--ink);background:var(--paper);border:1px solid var(--rule);padding:.45rem .65rem;border-radius:.25rem}
section h2{margin:1.6rem 0 .5rem;font:600 1.45rem/1.2 var(--serif)}
.question{font:italic 1.05rem/1.45 var(--serif);margin-bottom:.65rem}
#sources{margin:.5rem 0;display:grid;gap:.5rem;font:1.06rem/1.5 var(--serif);max-width:82ch}
#sources p{padding-left:.8rem;border-left:2px solid var(--rule)}
.reference{font:.93rem/1.55 var(--sans);color:var(--accent);margin:.75rem 0}
.answers{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1.25rem;margin:.85rem 0}
.answers article{min-width:0;padding-top:.65rem;border-top:2px solid var(--accent);overflow-wrap:anywhere}
.answers h3{font:600 1.08rem/1.35 var(--sans);margin:0 0 .6rem}
blockquote{font:1.1rem/1.5 var(--serif);margin:.4rem 0 .8rem;white-space:pre-wrap}
.verdict{color:var(--accent);font:.92rem/1.45 var(--sans)}
details{margin-top:.65rem} summary{cursor:pointer} dl{font:.85rem/1.45 var(--sans);margin:.35rem 0} dt{font-weight:600} dd{margin:0 0 .3rem}
@media(max-width:48rem){.answers{grid-template-columns:1fr}.controls{display:grid;grid-template-columns:minmax(0,1fr)}.controls label,.controls select{min-width:0;width:100%}body .shell{width:calc(100% - 2.5rem)}}
@page{size:A4 portrait;margin:18mm}
@media print{nav,.controls,details{display:none}main.case-study{width:auto;padding:0}.answers{display:block}.answers article{break-inside:avoid;margin:.8rem 0}}
</style></head>
<body><main class="shell case-study">
<nav><a href="../manuscript.html#when-can-context-identify-the-researcher">Return to the manuscript</a><a href="context-cue-scores.csv" download>Download all 72 assignments (CSV)</a></nav>
<header><h1>Who did the work?</h1><p>Read the same evidence under three assignments of scientific standing. Compare whom each summary credits and how it handles uncertainty.</p></header>
<div class="controls"><label>Case and record order<select id="context-block"></select></label>
<label>Available evidence<select id="context-evidence">
<option value="DIRECT">Actor named directly</option><option selected value="INDIRECT">Actor inferable across records</option>
<option value="INDETERMINATE">Actor cannot be identified</option></select></label></div>
<section><h2>What the records say</h2><p id="question" class="question"></p><div id="sources"></div>
<p id="reference" class="reference" role="status"></p></section>
<section><h2>What the model wrote</h2><div id="context-results" class="answers"></div></section>
<noscript>Download the CSV above for the questions, records, answers and scores.</noscript></main>
<script type="application/json" id="context-data">__OBSERVATIONS__</script>
<script>
const rows=JSON.parse(document.querySelector('#context-data').textContent);
const cases=document.querySelector('#context-block'), evidence=document.querySelector('#context-evidence');
const arms={NEUTRAL:'Standing unspecified',A_MARKED:'A given high standing',B_MARKED:'B given high standing'};
const verdicts={SOLE_CORRECT:'Credits the documented actor',SOLE_FOIL:'Credits the other researcher',
  JOINT:'Credits both researchers jointly',SOLE_UNSUPPORTED:'Selects one researcher without decisive evidence',
  EXPLICIT_UNCERTAINTY:'Explicitly leaves the actor unresolved',UNASSIGNED:'Makes no assignment or explicit statement of uncertainty',
  TECHNICAL_FAILURE:'No auditable answer'};
function put(parent,tag,value){const item=document.createElement(tag);item.textContent=value;parent.append(item);return item}
for(const id of [...new Set(rows.map(r=>r.block))].sort()){
  const direct=rows.find(r=>r.block===id&&r.evidence==='DIRECT');
  const record=direct.prompt.split('\n\n')[2].split(':')[0].toLowerCase();
  const family=direct.vignette==='interviews'?'Interviews':'Reading';
  cases.add(new Option(family+' · '+record+' first · '+id,id));
}
function render(){
  const group=rows.filter(r=>r.block===cases.value&&r.evidence===evidence.value);
  const [question,roster,...pieces]=group[0].prompt.split('\n\n');
  document.querySelector('#question').textContent=question;
  const sources=document.querySelector('#sources');sources.replaceChildren();
  for(const piece of pieces)put(sources,'p',piece);
  const ref=group[0].gold_actor;
  document.querySelector('#reference').textContent=ref==='UNDETERMINED'
    ?'Independent model reading: either researcher could have performed the action.'
    :'Independent model reading: Researcher '+ref+' performed the action.';
  const results=document.querySelector('#context-results');results.replaceChildren();
  for(const arm of Object.keys(arms)){
    const r=group.find(item=>item.cue===arm),card=document.createElement('article');results.append(card);
    put(card,'h3',arms[arm]);
    if(r.answer)put(card,'blockquote',r.answer);
    put(card,'p',verdicts[r.response_category]).className='verdict';
    if(r.delivery==='DELIVERED'){
      const d=document.createElement('details');card.append(d);put(d,'summary','Inspect coding');
      const list=document.createElement('dl');d.append(list);
      for(const [k,v] of [['Action',r.action_status],['Attribution',r.attribution],['Actor endorsed',r.endorsed_actors||'None'],
          ['Uncertainty stated',r.explicit_uncertainty==='1'?'Yes':'No']]){
        put(list,'dt',k);put(list,'dd',v.replaceAll('_',' ').toLowerCase());
      }
    }
  }
}
function showSelection(){
  render();
  history.replaceState(null,'','#'+cases.value+'-'+evidence.value);
}
function readSelection(){
  const [block,level]=location.hash.slice(1).split('-');
  if([...cases.options].some(o=>o.value===block) && [...evidence.options].some(o=>o.value===level)){
    cases.value=block;evidence.value=level;
  }
  render();
}
cases.addEventListener('change',showSelection);evidence.addEventListener('change',showSelection);
window.addEventListener('hashchange',readSelection);readSelection();
</script></body></html>'''
