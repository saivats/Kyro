"use strict";
const byId = id => document.getElementById(id);
const labels = ["Low", "Medium", "High", "Critical"];
const stages = {review:"Pending review", waiting:"Waiting", assigned:"Assigned", in_treatment:"In treatment", completed:"Completed"};
let current = null, selectedCase = null, selectedDoctor = null, requestKey = null, signature = null;
let refreshNumber = 0;

function el(tag, text, className) {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (className) item.className = className;
  return item;
}
function button(text, handler) {
  const item = el("button", text, "secondary");
  item.type = "button";
  item.onclick = async () => {
    item.disabled = true;
    try { await handler(); } catch (err) { tell(err.message); }
    finally { item.disabled = false; }
  };
  return item;
}
function tell(text) { byId("message").textContent = text; }
async function api(path, payload) {
  const options = payload === undefined ? {} : {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)};
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Request failed");
  return data;
}
function bar(title, value, max, caption, cls) {
  const row = el("div", undefined, "bar"), meter = el("progress");
  meter.max = max || 1; meter.value = Math.abs(value);
  meter.setAttribute("aria-label", title); if (cls) meter.className = cls;
  row.append(el("span", title), meter, el("strong", caption));
  return row;
}
function line(title, value) {
  const row = el("div", undefined, "row");
  row.append(el("span", title), el("strong", value));
  return row;
}
function showView() {
  const views = [...document.querySelectorAll("[data-view]")];
  const wanted = views.find(a => a.hash === location.hash)?.dataset.view || "overview";
  for (const link of views) {
    byId(link.dataset.view).hidden = link.dataset.view !== wanted;
    if (link.dataset.view === wanted) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  if (wanted === "model") loadReport().catch(e => tell(e.message));
}
window.addEventListener("hashchange", showView);
function minutes(value) { return value == null ? "No recorded interval" : value.toFixed(1) + " min"; }
function waited(stamp) {
  return stamp ? Math.max(0, Math.floor((Date.now() - Date.parse(stamp.replace(" ", "T")+"Z"))/60000))+" min since review" : "Earlier record";
}
function renderOverview(s) {
  const total = Object.values(s.counts).reduce((a,b) => a+b, 0);
  byId("stats").replaceChildren(...[["Total cases",total], ...Object.entries(stages).map(([k,v]) => [v,s.counts[k]||0])].map(([name,value]) => {
    const box=el("div",undefined,"stat"); box.append(el("strong",value),el("small",name)); return box;
  }));
  const reviewed = Object.values(s.severity).reduce((a,b)=>a+b,0);
  byId("mix").replaceChildren(...labels.map((name,i)=>bar(name,s.severity[i]||0,reviewed,String(s.severity[i]||0))));
  byId("timings").replaceChildren(line("Doctors accepting cases",s.doctors.filter(d=>d.available && d.load<d.capacity).length+" / "+s.doctors.length),
    line("Mean review to assignment",minutes(s.durations.wait_minutes)),line("Mean treatment duration",minutes(s.durations.treatment_minutes)));
  const waiting = s.cases.filter(c=>c.state==="waiting").map(c=>line(c.name,labels[c.reviewed]+" · "+c.specialty+" · "+waited(c.reviewed_at)));
  byId("waiting").replaceChildren(...(waiting.length?waiting:[el("p","No reviewed cases are waiting for capacity.")]));
}
async function transition(c, action) {
  await api("/api/demo/cases/"+c.id+"/action",{action});
  await refresh(); tell(action==="start"?"Treatment started.":"Treatment completed. Available capacity has been reassigned where possible.");
}
function actionButton(c) {
  return c.state==="assigned" ? button("Start treatment",()=>transition(c,"start")) :
    c.state==="in_treatment" ? button("Complete treatment",()=>transition(c,"complete")) : null;
}
function renderQueue() {
  if (!current) return;
  const filter=byId("filter").value, query=byId("search").value.toLowerCase().trim();
  const rows=current.cases.filter(c=>(filter==="active"?c.state!=="completed":c.state===filter)
    && (c.name+" "+c.specialty).toLowerCase().includes(query)).map(c=>{
    const row=el("tr"), title=el("td"), severity=el("td"), state=el("td"), actions=el("td");
    title.append(el("strong",c.name),el("small",c.specialty+" · "+c.created));
    severity.append(el("span","AI "+labels[c.predicted],"sev s"+c.predicted),el("small",c.reviewed==null?"Pending human review":"Confirmed "+labels[c.reviewed]));
    state.append(el("strong",stages[c.state]),el("small",c.doctor || (c.state==="waiting"?waited(c.reviewed_at):"Unassigned")));
    actions.append(button(c.state==="review"?"Inspect & review":"Inspect",()=>inspect(c.id)));
    const next=actionButton(c); if(next) actions.append(next);
    row.append(title,severity,state,actions); return row;
  });
  if(!rows.length){const r=el("tr"),cell=el("td","No cases match this view.");cell.colSpan=4;r.append(cell);rows.push(r);}
  byId("rows").replaceChildren(...rows);
}
function renderDoctors(s) {
  byId("doctors").replaceChildren(...s.doctors.map(d=>{
    const box=el("article"), meter=bar("Workload",d.load,d.capacity,d.load+" / "+d.capacity);
    box.append(el("h2",d.name),el("p",d.specialty+" · "+(d.available?"Accepting cases":"Closed to new cases")),meter);
    for(const c of s.cases.filter(c=>c.doctor_id===d.id && ["assigned","in_treatment"].includes(c.state))){
      const r=line(c.name,labels[c.reviewed]);r.append(actionButton(c));box.append(r);
    }
    box.append(button("Edit doctor",()=>editDoctor(d)));return box;
  }));
}
async function refresh() {
  const sequence=++refreshNumber;
  const data=await api("/api/demo/state");
  if(sequence !== refreshNumber) return;
  current=data; renderOverview(data); renderQueue(); renderDoctors(data);
  byId("events").replaceChildren(...(data.events.length?data.events.map(e=>line(e.action.replaceAll("_"," ")+" · "+e.subject,e.created+" UTC")):[el("p","Activity appears after the first intake or roster change.")]));
}
async function checkReady() {
  try {await api("/health/ready");byId("health").textContent="● System ready";}
  catch {byId("health").textContent="● System unavailable";}
}
async function inspect(id) {
  const c=current.cases.find(x=>x.id===id), detail=await api("/api/demo/cases/"+id);
  selectedCase=id;const target=byId("inspection"), result=detail.result, input=detail.intake;
  target.replaceChildren();byId("case-title").textContent=c.name+" · Triage inspector";
  target.append(el("h3","AI prediction · "+labels[c.predicted]),el("p","Uncalibrated model score "+(c.confidence*100).toFixed(1)+"%."));
  if(result){
    target.append(...labels.map((l,i)=>bar(l,result.probabilities[i],1,(100*result.probabilities[i]).toFixed(1)+"%")));
    target.append(el("h3","Top model contributions"),el("p","TreeSHAP values shift the raw margin for "+labels[c.predicted]+". Positive values push toward this class. Negative values push away."));
    const top=result.feature_importance.slice(0,5),max=Math.abs(top[0].shap_value);
    target.append(...top.map(f=>bar(f.feature.replaceAll("_"," "),f.shap_value,max,(f.shap_value>=0?"+":"")+f.shap_value.toFixed(3),f.shap_value<0?"away":"")));
  } else {target.append(el("p","This earlier case has no stored explanation."));}
  target.append(el("h3","Review information"),el("p","Symptoms and oxygen saturation are excluded from the model."));
  if(input){
    target.append(line("Symptoms",input.symptoms || "None entered"),line("Age / gender",input.age+" / "+input.gender),
      line("Prior triage / EMS",[input.immediate_triage,input.arrival_by_ems].map(x=>x?"Yes":"No").join(" / ")),
      line("Chronic conditions",input.history.chronic_conditions.join(", ")||"None selected"));
    const titles={heart_rate:"Heart rate (bpm)",systolic_bp:"Systolic BP (mmHg)",diastolic_bp:"Diastolic BP (mmHg)",respiratory_rate:"Respiratory rate (/min)",temperature:"Normalized temperature (°F)",pain_scale:"Pain score",oxygen_saturation:"Oxygen saturation (%)"};
    for(const [key,v] of Object.entries(input.vitals))target.append(line(titles[key],String(Number(v.toFixed(2)))));
  } else target.append(line("Oxygen saturation",c.oxygen+"%"));
  target.append(line("Routing specialty",c.specialty));
  if(c.reviewed!==null)target.append(line("Human-confirmed severity",labels[c.reviewed]));
  if(c.doctor)target.append(el("p","Assigned to "+c.doctor+" by matching specialty, open capacity, lowest utilization, then doctor ID."));
  const form=byId("review-form");form.hidden=c.state!=="review";form.reset();form.elements.specialty.value=c.specialty;
  byId("review-status").textContent="";
  byId("inspector").showModal();
}
byId("review-form").onsubmit=async e=>{
  e.preventDefault();const f=e.currentTarget,b=f.querySelector("button");b.disabled=true;
  try{await api("/api/demo/cases/"+selectedCase+"/action",{action:"review",severity:Number(f.elements.severity.value),specialty:f.elements.specialty.value});
    byId("inspector").close();location.hash="queue";await refresh();tell("Human review saved.");}
  catch(err){byId("review-status").textContent=err.message;}finally{b.disabled=false;}
};
const presets={
  routine:["General visit","general",32,"female",76,118,76,16,36.8,1,99,0,0,"Fictional routine visit"],
  cardiac:["Cardiology transfer","cardiology",62,"male",112,110,70,23,37.5,6,94,0,1,"Fictional chest discomfort"],
  resp:["Respiratory review","respiratory",68,"female",132,84,54,30,38.8,8,88,1,1,"Fictional breathing difficulty"]
};
byId("preset").onchange=e=>{
  const f=byId("case-form"), preset=presets[e.target.value];if(!preset)return;
  const keys=["name","specialty","age","gender","heart_rate","systolic_bp","diastolic_bp","respiratory_rate","temperature","pain_scale","oxygen_saturation","immediate_triage","arrival_by_ems","symptoms"];
  keys.forEach((k,i)=>{f.elements[k].value=preset[i];});f.elements.temperature_unit.value="C";f.elements.confirm.checked=false;
  for(const c of f.querySelectorAll('[name="conditions"]'))c.checked=e.target.value==="resp"&&c.value==="asthma";
};
byId("case-form").onsubmit=async e=>{
  e.preventDefault();const form=e.currentTarget, f=new FormData(form), b=form.querySelector("button[type=submit]");
  const vitals={};
  for(const k of ["heart_rate","systolic_bp","diastolic_bp","respiratory_rate","temperature","pain_scale","oxygen_saturation"])vitals[k]=Number(f.get(k));
  const data={name:f.get("name"),age:Number(f.get("age")),gender:f.get("gender"),specialty:f.get("specialty"),symptoms:f.get("symptoms"),temperature_unit:f.get("temperature_unit"),vitals,chronic_conditions:f.getAll("conditions"),immediate_triage:Number(f.get("immediate_triage")),arrival_by_ems:Number(f.get("arrival_by_ems")),synthetic_only:f.has("confirm")};
  const serialized=JSON.stringify(data);
  if(signature!==serialized){signature=serialized;requestKey=crypto.randomUUID();}
  b.disabled=true;
  try{const r=await api("/api/demo/intake",{...data,request_id:requestKey});
    signature=null;form.reset();byId("filter").value="active";byId("search").value="";location.hash="queue";
    await refresh();await inspect(r.id);tell("Case saved for human review.");}
  catch(err){tell(err.message);}finally{b.disabled=false;}
};
function editDoctor(d){
  selectedDoctor=d?.id || null;
  const f=byId("doctor-form");f.reset();f.elements.name.value=d?.name || "";f.elements.specialty.value=d?.specialty || "general";
  f.elements.capacity.value=d?.capacity || 1;f.elements.available.checked=d?Boolean(d.available):true;
  byId("doctor-error").textContent="";byId("doctor-dialog").showModal();
}
byId("doctor-form").onsubmit=async e=>{
  e.preventDefault();const f=e.currentTarget,b=f.querySelector("button");b.disabled=true;
  try{await api("/api/demo/doctors"+(selectedDoctor?"/"+selectedDoctor:""),{name:f.elements.name.value,specialty:f.elements.specialty.value,capacity:Number(f.elements.capacity.value),available:f.elements.available.checked});
    byId("doctor-dialog").close();await refresh();tell("Doctor roster updated.");}
  catch(err){byId("doctor-error").textContent=err.message;}finally{b.disabled=false;}
};
async function loadReport(){
  const box=byId("model-report");if(box.childElementCount)return;
  const m=await api("/api/demo/model"), r=m.report;
  box.append(el("h2","XGBoost "+m.version+" · "+m.features.length+" inputs"),el("p","Historical evaluation on a mixed NHAMCS 2022 and synthetic test set. Rule-derived labels, pre-split imputation and prior-triage input limit interpretation. Sex encoding also differs across legacy preprocessing paths."),
    line("Accuracy",(100*r.accuracy).toFixed(2)+"%"),line("Macro F1",(100*r.macro_f1).toFixed(2)+"%"),line("High-class recall",(100*r.recall_per_class.High).toFixed(2)+"%"),
    el("h3","Historical confusion matrix"),el("p","Rows are reference labels. Columns are predicted classes."));
  const table=el("table"),head=el("tr");["Reference",...labels].forEach(x=>head.append(el("th",x)));table.append(head);
  r.confusion_matrix.forEach((row,i)=>{const tr=el("tr");tr.append(el("th",labels[i]),...row.map(v=>el("td",v)));table.append(tr);});
  const wrap=el("div",undefined,"scroll");wrap.append(table);box.append(wrap);
}
for(const b of document.querySelectorAll("[data-close]"))b.onclick=()=>b.closest("dialog").close();
byId("add-doctor").onclick=()=>editDoctor(null);
byId("search").oninput=renderQueue;byId("filter").onchange=renderQueue;
showView();refresh().catch(e=>tell(e.message));checkReady();
setInterval(()=>{if(!document.hidden && !document.querySelector("dialog[open]")){refresh().catch(e=>tell(e.message));checkReady();}},5000);
