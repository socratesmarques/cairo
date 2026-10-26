"use strict";

// Polling never starts, pauses or dismisses clocks; actions require a form or button.
const daily = {sid:null, title:"", data:{tasks:[],notes:[],timers:[]}, taskId:null, noteId:null, tab:"tasks", commands:[], loading:false, timerSample:Date.now()};
const dailyDialog = $("daily-dialog");
const dailyFold = value => String(value).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("pt-BR");

function dailyFeedback(message, error=false) {
  $("daily-feedback").textContent = message;
  $("daily-feedback").dataset.error = String(error);
}
function selectDailyTab(tab) {
  dailyFeedback("");
  daily.tab = tab;
  document.querySelectorAll("[data-daily-tab]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.dailyTab === tab)));
  document.querySelectorAll("[data-daily-panel]").forEach(panel => panel.hidden = panel.dataset.dailyPanel !== tab);
}
async function openDaily(tab="tasks") {
  try {
    if (state.sending) throw new Error("Aguarde o envio da mensagem antes de abrir a central.");
    openMic?.stop();
    if (!state.session) {
      const session = await api("/api/sessions", {method:"POST",body:"{}"});
      await openSession(session.id);
      await refreshSessions();
    }
    if (!state.session) throw new Error("Escolha uma conversa para abrir a central.");
    const changed = daily.sid !== state.session.id;
    daily.sid = state.session.id;
    daily.title = state.session.title || "Nova conversa";
    if (changed) { resetDailyForm("task"); resetDailyForm("note"); }
    $("daily-context").textContent = `Conversa: ${daily.title}`;
    dailyFeedback("Carregando seus itens…");
    selectDailyTab(tab);
    if (!dailyDialog.open) dailyDialog.showModal();
    await refreshDaily();
    if (!daily.commands.length) daily.commands = await api("/api/commands");
    renderCommands();
    dailyFeedback("");
  } catch (error) { if (dailyDialog.open) dailyFeedback(error.message,true); else showError(error.message); }
}
async function refreshDaily() {
  const sid = daily.sid;
  const data = await api("/api/productivity?" + new URLSearchParams({session_id:sid}));
  if (sid !== daily.sid) return;
  daily.data = data;
  daily.timerSample = Date.now();
  renderDaily();
}
async function dailyCall(tool, args) {
  const response = await api("/api/productivity", {method:"POST",body:JSON.stringify({session_id:daily.sid,tool,arguments:args})});
  return response.result;
}
async function dailyMutation(tool, args) {
  const sid = daily.sid;
  const result = await dailyCall(tool,args);
  if (sid !== daily.sid) return result;
  await refreshDaily();
  dailyFeedback(result.message.replace(/\s*ID:\s*[0-9a-f]{32}/g,""));
  return result;
}
function resetDailyForm(kind) {
  daily[kind + "Id"] = null;
  $(kind + "-form").reset();
  if (kind === "task") $("task-form-heading").textContent = "Uma coisa de cada vez";
}
function actionButton(label, action) {
  const button = node("button", "", label); button.type="button";
  button.addEventListener("click", async () => {
    button.disabled = true;
    try { await action(); } catch(error) { dailyFeedback(error.message,true); }
    finally { button.disabled = false; }
  });
  return button;
}
function renderTasks() {
  const list = $("task-list"); list.replaceChildren();
  const query = dailyFold($("task-search").value);
  const filter = $("task-filter").value;
  const priorities = {high:"Alta", normal:"Normal", low:"Baixa"};
  const items = daily.data.tasks.filter(item => (filter === "all" || item.status === filter) && dailyFold(item.text).includes(query));
  for (const item of items) {
    const row = node("article","daily-item");
    row.append(node("h4","",item.text));
    row.append(node("p", "daily-item-meta" + (item.overdue ? " overdue" : ""), `${priorities[item.priority]} · ${item.due ? item.due.split("-").reverse().join("/") : "Sem prazo"}${item.overdue ? " · Atrasada" : ""}`));
    const actions = node("div","daily-item-actions");
    actions.append(actionButton("Editar", () => { daily.taskId=item.id; $("task-text").value=item.text; $("task-priority").value=item.priority; $("task-due").value=item.due; $("task-form-heading").textContent="Editar tarefa"; $("task-text").focus(); }));
    actions.append(actionButton(item.status === "open" ? "Concluir" : "Reabrir", () => dailyMutation("task_update",{id:item.id,status:item.status === "open" ? "done" : "open"})));
    if (item.status !== "archived") actions.append(actionButton("Arquivar", () => dailyMutation("task_update",{id:item.id,status:"archived"})));
    row.append(actions);list.append(row);
  }
  if (!items.length) list.append(node("p","daily-empty","Nenhuma tarefa neste filtro. Adicione a próxima ao lado."));
}
function renderNotes() {
  const list = $("note-list"); list.replaceChildren();
  const query = dailyFold($("note-search").value);
  const items = daily.data.notes.filter(item => item.status === $("note-filter").value && dailyFold(item.title+" "+item.text).includes(query));
  for (const item of items) {
    const row = node("article","daily-item"); row.append(node("h4","",item.title),node("p","daily-note-preview",item.text));
    const actions=node("div","daily-item-actions");
    actions.append(actionButton("Editar",()=>{ daily.noteId=item.id; $("note-title").value=item.title; $("note-text").value=item.text; $("note-title").focus(); }),actionButton("Copiar",()=>navigator.clipboard.writeText(item.text).then(()=>dailyFeedback("Nota copiada."))), actionButton(item.status === "active" ? "Arquivar" : "Restaurar",()=>dailyMutation("note_update",{id:item.id,status:item.status === "active" ? "archived" : "active"})));
    row.append(actions);list.append(row);
  }
  if (!items.length) list.append(node("p","daily-empty","Nenhuma nota encontrada. Guarde uma ideia ao lado."));
}
function renderFocus() {
  const list=$("focus-list");list.replaceChildren();
  const labels={running:"Em andamento",paused:"Pausado",finished:"Concluído",cancelled:"Cancelado",acknowledged:"Confirmado"};
  const items=daily.data.timers.filter(item=>!["cancelled","acknowledged"].includes(item.status));
  for (const item of items) {
    const row=node("article","daily-item");row.append(node("h4","",item.text),node("p","daily-item-meta",labels[item.status]));
    const clock=node("div","focus-clock");clock.dataset.timerId=item.id;row.append(clock);
    const actions=node("div","daily-item-actions");
    const add=(label,action)=>actions.append(actionButton(label,()=>dailyMutation("focus_action",{id:item.id,action})));
    if(item.status==="running") add("Pausar","pause");
    if(item.status==="paused") add("Retomar","resume");
    if(["running","paused"].includes(item.status)) add("Cancelar","cancel");
    if(item.status==="finished") add("Confirmar conclusão","acknowledge");
    row.append(actions);list.append(row);
  }
  if(!items.length) list.append(node("p","daily-empty","Seu próximo período de foco começa aqui."));
  tickDaily();
}
function renderDailyAgenda() {
  const list=$("daily-reminder-list");list.replaceChildren();
  for(const item of daily.data.reminders || []){
    const overdue=new Date(item.due).getTime()<=Date.now();
    const row=node("article","daily-item");row.append(node("h4","",item.text),node("p","daily-item-meta"+(overdue?" overdue":""),new Date(item.due).toLocaleString("pt-BR")+(overdue?" · Aguardando você":"")));
    const actions=node("div","daily-item-actions");
    const update=async(path,extra={})=>{await api(path,{method:"POST",body:JSON.stringify({id:item.id,session_id:daily.sid,...extra})});await refreshDaily();await refreshReminders();dailyFeedback("Agenda atualizada.");};
    actions.append(actionButton("Adiar 15 min",()=>update("/api/reminders/snooze",{minutes:15})),actionButton("Adiar 1 hora",()=>update("/api/reminders/snooze",{minutes:60})),actionButton("Concluir",()=>update("/api/reminders/dismiss")));
    row.append(actions);list.append(row);
  }
  if(!daily.data.reminders?.length) list.append(node("p","daily-empty","Nenhum lembrete pendente nesta conversa."));
}
function tickDaily() {
  if(!dailyDialog.open) return;
  document.querySelectorAll("[data-timer-id]").forEach(element=>{
    const timer=daily.data.timers.find(item=>item.id===element.dataset.timerId);
    const seconds=Math.max(0, Math.ceil(timer.remaining_seconds-(timer.status==="running" ? (Date.now()-daily.timerSample)/1000 : 0)));
    element.textContent=`${String(Math.floor(seconds/60)).padStart(2,"0")}:${String(seconds%60).padStart(2,"0")}`;
  });
}
function renderDaily() {
  const tasks=daily.data.tasks;
  const counts=[[tasks.filter(item=>item.status==="open").length,"Tarefas abertas"],[tasks.filter(item=>item.overdue).length,"Com prazo atrasado"],[tasks.filter(item=>item.status==="done").length,"Concluídas"]];
  $("daily-summary").replaceChildren(...counts.map(([count,label])=>{const card=node("div");card.append(node("strong","",count),node("span","",label));return card;}));
  renderTasks(); renderNotes(); renderFocus(); renderDailyAgenda();
}
function renderCommands() {
  const query=dailyFold($("command-search").value);
  const items=daily.commands.filter(item=>dailyFold(item.category+" "+item.command).includes(query));
  $("command-list").replaceChildren(...items.map(item=>{
    const button=actionButton("",()=>{dailyDialog.close();prepareDraft(item.command);});
    button.append(node("small","",item.category),node("span","",item.command));return button;
  }));
  if(!items.length) $("command-list").append(node("p","daily-empty","Nenhum exemplo encontrado."));
}
function dailyForm(id, work) {
  $(id).addEventListener("submit",async event=>{
    event.preventDefault();const button=event.submitter; if(button) button.disabled=true;
    try {await work();} catch(error){dailyFeedback(error.message,true);} finally{if(button)button.disabled=false;}
  });
}
dailyForm("task-form",async()=>{
  const sid=daily.sid;
  const args={text:$("task-text").value,priority:$("task-priority").value,due:$("task-due").value};
  if(daily.taskId) args.id=daily.taskId;
  await dailyMutation(daily.taskId ? "task_update" : "task_create",args);if(sid===daily.sid)resetDailyForm("task");
});
dailyForm("note-form",async()=>{
  const sid=daily.sid;
  const args={title:$("note-title").value,text:$("note-text").value};if(daily.noteId) args.id=daily.noteId;
  await dailyMutation(daily.noteId ? "note_update" : "note_create",args);if(sid===daily.sid)resetDailyForm("note");
});
dailyForm("focus-form",()=>dailyMutation("focus_start",{seconds:Number($("focus-minutes").value)*60,text:$("focus-text").value}));
dailyForm("daily-reminder-form",async()=>{await api("/api/reminders",{method:"POST",body:JSON.stringify({session_id:daily.sid,text:$("daily-reminder-text").value,due:new Date($("daily-reminder-due").value).toISOString()})});$("daily-reminder-form").reset();await refreshDaily();await refreshReminders();dailyFeedback("Lembrete agendado.");});
dailyForm("calculate-form",async()=>{$("calculate-output").textContent="";const result=await dailyCall("calculate",{expression:$("calculate-expression").value});$("calculate-output").textContent=result.message;dailyFeedback("");});
dailyForm("convert-form",async()=>{$("convert-output").textContent="";const result=await dailyCall("unit_convert",{value:$("convert-value").value,source:$("convert-source").value,target:$("convert-target").value});$("convert-output").textContent=result.message;dailyFeedback("");});
dailyForm("text-form",async()=>{$("text-output").textContent="";const result=await dailyCall("text_transform",{text:$("utility-text").value,action:$("text-action").value});$("text-output").textContent=result.message;dailyFeedback("");});
$("copy-text-output").addEventListener("click",async()=>{try{await navigator.clipboard.writeText($("text-output").textContent);dailyFeedback("Resultado copiado.");}catch(_){dailyFeedback("Não foi possível copiar; selecione o resultado e use Ctrl+C.",true);}});
$("task-reset").addEventListener("click",()=>resetDailyForm("task"));
$("note-reset").addEventListener("click",()=>resetDailyForm("note"));
for(const id of ["task-search","task-filter"]) $(id).addEventListener("input",renderTasks);
for(const id of ["note-search","note-filter"]) $(id).addEventListener("input",renderNotes);
$("command-search").addEventListener("input",renderCommands);
document.querySelectorAll("[data-daily-tab]").forEach(button=>button.addEventListener("click",()=>selectDailyTab(button.dataset.dailyTab)));
document.querySelectorAll("[data-focus-minutes]").forEach(button=>button.addEventListener("click",()=>{$("focus-minutes").value=button.dataset.focusMinutes;}));
$("open-daily").addEventListener("click",()=>openDaily());
$("open-guide").addEventListener("click",()=>openDaily("guide"));
$("daily-close").addEventListener("click",()=>dailyDialog.close());
$("refresh-daily").addEventListener("click",async()=>{try{await refreshDaily();dailyFeedback("Central atualizada.");}catch(error){dailyFeedback(error.message,true);}});
$("export-daily").addEventListener("click",async()=>{
  try{
    await refreshDaily();
    const lines=[`# Central do dia — ${daily.title}`,"", "## Tarefas",...daily.data.tasks.map(item=>`- [${item.status==="done" ? "x" : " "}] ${item.text} (${item.priority}; ${item.due||"sem prazo"}; ${item.status})`),"","## Notas",...daily.data.notes.flatMap(item=>[`### ${item.title} (${item.status})`,"",item.text,""])];
    const blob=new Blob([lines.join("\n")],{type:"text/markdown;charset=utf-8"});const url=URL.createObjectURL(blob);
    const link=node("a");link.href=url;link.download=`cairo-central-${daily.sid}.md`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);dailyFeedback("Exportação preparada em Markdown.");
  }catch(error){dailyFeedback(error.message,true);}
});
let focusPollBusy=false;
async function pollFocusAlerts(){
  if(focusPollBusy)return;focusPollBusy=true;
  try{
    const alerts=await api("/api/focus-alerts");
    $("focus-alert").replaceChildren();$("focus-alert").hidden=!alerts.length;
    if(alerts.length){$("focus-alert").append(node("span","",`${alerts.length} período(s) de foco concluído(s).`),actionButton(`Ver: ${alerts[0].text}`,async()=>{dailyDialog.close();await openSession(alerts[0].session_id);await openDaily("focus");}));}
    if(dailyDialog.open && daily.sid){
      const sid=daily.sid;const response=await api("/api/productivity",{method:"POST",body:JSON.stringify({session_id:sid,tool:"focus_list",arguments:{}})});
      if(sid===daily.sid){
        const signature=items=>JSON.stringify(items.map(item=>[item.id,item.status,item.text]));
        const changed=signature(daily.data.timers)!==signature(response.result.items);
        daily.data.timers=response.result.items;daily.timerSample=Date.now();
        if(changed)renderFocus();else tickDaily();
      }
    }
  }catch(_){if(dailyDialog.open && daily.tab==="focus")dailyFeedback("Não foi possível atualizar o foco. O horário salvo será recuperado ao reconectar.",true);}
  finally{focusPollBusy=false;}
}
setInterval(tickDaily,1000);
setInterval(pollFocusAlerts,10000);
pollFocusAlerts();
