"use strict";

const $ = (id) => document.getElementById(id);
const agentDefinitions = [
  ["MasterAgent", "Master", "Coordenação e resposta", "◈"],
  ["DeveloperAgent", "Developer", "Código e desenvolvimento", "⌘"],
  ["ResearchAgent", "Research", "Pesquisa e contexto", "◇"],
  ["SystemAgent", "System", "Workspace e diagnóstico", "⌁"],
  ["Reviewer", "Reviewer", "Revisão e síntese", "✓"],
];
let voice = null;
let openMic = null;
const state = { session: null, mode: "normal", sessions: [], runs: new Map(), sending: false, loadVersion: 0 };
const terminal = new Set(["completed", "failed", "cancelled"]);
const labels = { queued: "Aguardando execução", pending: "Aguardando execução", running: "Equipe trabalhando", completed: "Execução concluída", failed: "Execução interrompida por erro", cancelled: "Execução cancelada" };

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = String(text);
  return element;
}

async function api(path, options = {}) {
  if (!globalThis.CairoClient) throw new Error("Atualização instalada. Encerre o Cairo com Ctrl+C e abra novamente para carregar a nova versão.");
  return CairoClient.fetchJSON(path, options);
}

function showError(message = "") {
  $("error-banner").textContent = message;
  $("error-banner").hidden = !message;
}

function setMode(mode) {
  state.mode = mode === "swarm" ? "swarm" : "normal";
  document.querySelectorAll(".mode").forEach((button) => {
    const active = button.dataset.mode === state.mode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  $("mode-help").textContent = state.mode === "swarm" ? "Master → subagentes → Reviewer" : "Master → ferramentas";
}

function currentRun() { return state.runs.get(state.session?.id); }
function busy() { const run = currentRun(); return Boolean(voice?.active || openMic?.voice.active) || state.sending || Boolean(run && !terminal.has(run.status)); }
function updateControls() {
  const active = busy();
  $("send").disabled = active;
  $("new-chat").disabled = state.sending;
  document.querySelectorAll(".session-button").forEach((button) => { button.disabled = state.sending; });
  $("message").disabled = active;
  $("microphone").disabled = Boolean(openMic?.enabled) || !voice?.Recognition || (active && !voice?.active);
  $("open-mic").disabled = !voice?.Recognition || (!openMic?.enabled && active);
  $("voice-auto-send").disabled = Boolean(openMic?.enabled);
  $("cancel").hidden = !currentRun() || terminal.has(currentRun().status);
  document.querySelectorAll(".mode").forEach((button) => { button.disabled = active; });
}

function renderSessions() {
  $("sessions").replaceChildren();
  if (!state.sessions.length) $("sessions").append(node("p", "session-empty", "Seu próximo projeto começa com uma conversa."));
  for (const session of state.sessions) {
    const button = node("button", `session-button${session.id === state.session?.id ? " active" : ""}`, session.title || "Nova conversa");
    button.title = session.title || "Nova conversa";
    if (session.id === state.session?.id) button.setAttribute("aria-current", "page");
    button.addEventListener("click", () => openSession(session.id));
    $("sessions").append(button);
  }
}

function addMessage(role, content, pending = false) {
  if (!content) return;
  const article = node("article", `message ${role}${pending ? " pending" : ""}`);
  const header = node("div", "message-header");
  header.append(node("span", "message-avatar", role === "user" ? "V" : "C"), node("span", "", role === "user" ? "Você" : "Cairo"));
  if (!pending) {
    const copy = node("button", "", "Copiar");
    copy.type = "button";
    copy.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(content); copy.textContent = "Copiado"; }
      catch (_) { showError("Não foi possível copiar. Selecione o texto e use Ctrl+C."); }
    });
    header.append(copy);
    if (role === "user") {
      const reuse = node("button", "", "Reutilizar");
      reuse.type = "button";
      reuse.addEventListener("click", () => prepareDraft(content));
      header.append(reuse);
    }
  }
  if (role === "assistant" && !pending && window.speechSynthesis) {
    const speak = node("button", "", "Ouvir");
    speak.type = "button";
    speak.addEventListener("click", () => speakText(content));
    header.append(speak);
  }
  article.append(header, node("div", "message-content", content));
  $("messages").append(article);
}

function renderMessages() {
  const messages = (state.session?.messages || []).filter((message) => ["user", "assistant"].includes(message.role));
  $("welcome").hidden = messages.length > 0;
  $("messages").replaceChildren();
  for (const message of messages) addMessage(message.role, message.content);
  const run = currentRun();
  if (run && !terminal.has(run.status)) addMessage("assistant", "Estou trabalhando no seu pedido. Acompanhe as etapas no painel da equipe.", true);
  $("conversation").scrollTop = $("conversation").scrollHeight;
}

function normalizedAgent(name) {
  const value = String(name || "").toLowerCase().replace(/[^a-z]/g, "");
  return agentDefinitions.find(([id]) => value === id.toLowerCase() || value === id.replace("Agent", "").toLowerCase() || (id === "Reviewer" && value === "revieweragent"))?.[0];
}

function renderActivity(run) {
  const events = run?.events || [];
  const statuses = new Map();
  for (const event of events) {
    const agent = normalizedAgent(event.agent);
    if (!agent) continue;
    const kind = String(event.kind || "").toLowerCase();
    let status = "running";
    if (["completed", "finished", "done"].includes(kind)) status = "completed";
    if (/fail|error/.test(kind)) status = "failed";
    if (kind === "cancelled") status = "idle";
    statuses.set(agent, status);
  }
  if (run && terminal.has(run.status)) {
    for (const [agent, status] of statuses) {
      if (status === "running") statuses.set(agent, run.status === "failed" ? "failed" : run.status === "cancelled" ? "idle" : "completed");
    }
  }
  $("agents").replaceChildren();
  for (const [id, name, description, icon] of agentDefinitions) {
    const row = node("div", "agent-row");
    const copy = node("div", "agent-description");
    const status = statuses.get(id) || "idle";
    copy.append(node("div", "agent-name", name), node("div", "agent-role", description));
    const indicator = node("span", `agent-state ${status}`);
    indicator.setAttribute("aria-label", { idle: "Aguardando", running: "Em execução", completed: "Concluído", failed: "Falhou" }[status]);
    indicator.title = indicator.getAttribute("aria-label");
    row.append(node("span", "agent-icon", icon), copy, indicator);
    $("agents").append(row);
  }
  $("run-status").textContent = run ? labels[run.status] || run.status : "Pronto para começar";
  $("run-dot").className = `run-dot ${run?.status || ""}`;
  $("event-count").textContent = `${events.length} evento${events.length === 1 ? "" : "s"}`;
  const oldScroll = $("events").scrollTop;
  const atBottom = $("events").scrollHeight - oldScroll - $("events").clientHeight < 40;
  $("events").replaceChildren();
  if (!events.length) $("events").append(node("li", "event-empty", "As etapas aparecem aqui quando você envia uma mensagem."));
  for (const event of events) {
    const item = node("li", "event");
    const meta = node("div", "event-meta");
    const time = event.created_at ? new Date(event.created_at) : null;
    meta.append(node("span", "", event.agent || "Cairo"), node("span", "event-time", time && !Number.isNaN(time.valueOf()) ? time.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : ""));
    item.append(meta, node("div", "event-text", event.message || event.kind || "Etapa registrada"));
    $("events").append(item);
  }
  $("events").scrollTop = atBottom ? $("events").scrollHeight : oldScroll;
  updateControls();
}

async function refreshSessions() {
  const sessions = await api("/api/sessions");
  state.sessions = Array.isArray(sessions) ? sessions : sessions.sessions || [];
  renderSessions();
}

async function openSession(id) {
  openMic?.stop();
  voice?.cancel();
  window.speechSynthesis?.cancel();
  const version = ++state.loadVersion;
  showError();
  try {
    const session = await api(`/api/sessions/${encodeURIComponent(id)}`);
    if (version !== state.loadVersion) return;
    state.session = session;
    $("chat-title").textContent = session.title || "Nova conversa";
    try { localStorage.setItem("cairo-session", session.id); } catch (_) { /* Storage may be disabled by browser policy. */ }
    renderSessions();
    const runs = session.runs || [];
    const active = runs.find((run) => !terminal.has(run.status));
    const latest = active || runs[0];
    if (latest && !state.runs.has(id)) {
      const run = await api(`/api/runs/${encodeURIComponent(latest.id)}`);
      state.runs.set(id, run);
      if (!terminal.has(run.status)) pollRun(id, run.id);
    }
    if (version !== state.loadVersion) return;
    const run = currentRun();
    if (run?.mode) setMode(run.mode);
    renderMessages();
    renderActivity(run);
    if (!busy()) $("message").focus();
  } catch (error) { if (version === state.loadVersion) showError(error.message); }
}

function newChat() {
  openMic?.stop();
  voice?.cancel();
  window.speechSynthesis?.cancel();
  ++state.loadVersion;
  state.session = null;
  $("chat-title").textContent = "Nova conversa";
  $("message").value = "";
  try { localStorage.removeItem("cairo-session"); } catch (_) { /* Optional preference persistence. */ }
  showError(); renderSessions(); renderMessages(); renderActivity(); $("message").focus();
}

const polling = new Set();
async function pollRun(sessionId, runId) {
  if (polling.has(runId)) return;
  polling.add(runId);
  let errors = 0;
  try {
    while (true) {
      let run;
      try { run = await api(`/api/runs/${encodeURIComponent(runId)}`); errors = 0; }
      catch (error) {
        errors += 1;
        if (state.session?.id === sessionId) showError(`Conexão interrompida: ${error.message} Nova tentativa automática…`);
        await new Promise((resolve) => setTimeout(resolve, Math.min(5000, 700 * errors)));
        continue;
      }
      state.runs.set(sessionId, run);
      if (state.session?.id === sessionId) { showError(); renderActivity(run); }
      if (terminal.has(run.status)) {
        if (state.session?.id === sessionId) {
          const version = state.loadVersion;
          try {
            const session = await api(`/api/sessions/${encodeURIComponent(sessionId)}`);
            if (state.session?.id === sessionId && version === state.loadVersion) {
              state.session = session;
              $("chat-title").textContent = session.title || "Conversa";
              renderMessages();
            }
          } catch (error) {
            if (state.session?.id === sessionId && version === state.loadVersion) {
              if (run.result) state.session.messages.push({ role: "assistant", content: run.result });
              renderMessages(); showError(`Resposta concluída, mas o histórico não foi atualizado: ${error.message}`);
            }
          }
          if (state.session?.id === sessionId && run.status === "completed" && run.result && $("speak-replies").checked) speakText(run.result);
          if (state.session?.id === sessionId && run.error && run.status === "failed") { openMic?.stop(); showError(run.error); }
          if (state.session?.id === sessionId && run.status === "cancelled") { openMic?.stop(); showError(); }
        }
        await refreshSessions().catch(() => {});
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 700));
    }
  } finally { polling.delete(runId); updateControls(); }
}

async function sendMessage(event) {
  event.preventDefault();
  const message = $("message").value.trim();
  if (!message || busy()) return;
  state.sending = true;
  updateControls(); showError();
  let sessionId;
  try {
    if (!state.session) {
      const session = await api("/api/sessions", { method: "POST", body: "{}" });
      state.session = { ...session, messages: [], runs: [] };
    }
    sessionId = state.session.id;
    const run = await api("/api/runs", { method: "POST", body: JSON.stringify({ session_id: sessionId, message, mode: state.mode }) });
    state.runs.set(sessionId, { ...run, mode: state.mode, events: [] });
    if (state.session?.id === sessionId) {
      state.session.messages.push({ role: "user", content: message });
      $("message").value = "";
      try { localStorage.setItem("cairo-session", sessionId); } catch (_) { /* Optional preference persistence. */ }
      renderMessages(); renderActivity(currentRun());
    }
    pollRun(sessionId, run.id);
    await refreshSessions();
  } catch (error) { openMic?.stop(); showError(error.message); }
  finally { state.sending = false; updateControls(); }
}

$("chat-form").addEventListener("submit", sendMessage);
$("new-chat").addEventListener("click", newChat);
document.querySelectorAll(".mode").forEach((button) => button.addEventListener("click", () => setMode(button.dataset.mode)));
document.querySelectorAll(".prompt-card").forEach((button) => button.addEventListener("click", () => { if (!busy()) { $("message").value = button.dataset.prompt; if (button.dataset.mode) setMode(button.dataset.mode); $("message").focus(); } }));
$("message").addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); $("chat-form").requestSubmit(); } });
document.addEventListener("keydown", (event) => { if (event.key.toLowerCase() === "n" && !event.ctrlKey && !event.metaKey && !event.altKey && !["INPUT", "TEXTAREA"].includes(document.activeElement.tagName)) newChat(); });
$("cancel").addEventListener("click", async () => {
  const run = currentRun();
  if (!run || terminal.has(run.status)) return;
  $("cancel").disabled = true;
  try { await api(`/api/runs/${encodeURIComponent(run.id)}/cancel`, { method: "POST", body: "{}" }); }
  catch (error) { showError(error.message); }
  finally { $("cancel").disabled = false; }
});

async function initialize() {
  renderActivity();
  try {
    const config = await api("/api/config");
    document.querySelector(".version").textContent = "V" + (config.version || "anterior");
    $("demo-banner").hidden = config.provider !== "demo";
    $("model-label").textContent = `${config.provider} / ${config.model}`;
    $("permission-label").textContent = config.full_file_access && config.allow_file_operations ? "Arquivos fora da workspace habilitados" : config.allow_write ? "Escrita permitida no workspace" : "Workspace em modo de leitura";
    $("permission-label").title = config.workspace || "";
    $("permission-label").textContent += config.allow_desktop ? " · Aplicativos habilitados" : " · Aplicativos desativados";
    $("permission-label").textContent += ` · ${config.max_steps || "?"} etapas`;
    await api("/api/health");
    $("connection").textContent = "Cairo conectado";
    $("connection-dot").classList.add("connected");
    await refreshSessions();
    let remembered;
    try { remembered = localStorage.getItem("cairo-session"); } catch (_) { /* Optional preference persistence. */ }
    if (remembered && state.sessions.some((session) => session.id === remembered)) await openSession(remembered);
  } catch (error) { $("connection").textContent = "Sem conexão"; showError(`Não foi possível conectar ao Cairo. ${error.message}`); }
}
voice = new CairoVoice({
  Recognition: window.SpeechRecognition || window.webkitSpeechRecognition,
  onState: (status) => {
    $("microphone").setAttribute("aria-pressed", String(Boolean(voice?.active)));
    $("microphone").classList.toggle("listening", Boolean(voice?.active));
    $("microphone").textContent = voice?.active ? "Terminar ditado" : "Microfone";
    $("voice-status").textContent = { idle: "Microfone desligado", starting: "Aguardando microfone…", listening: "Ouvindo em português…", stopping: "Concluindo transcrição…" }[status];
    updateControls();
  },
  onText: (text) => { $("message").value = text; },
  onDone: () => { if ($("voice-auto-send").checked) $("chat-form").requestSubmit(); else $("message").focus(); },
  onError: (message) => { $("voice-status").textContent = message; },
});
if (!voice.Recognition) $("voice-help").textContent = "Ditado indisponível neste navegador. Abra Cairo no Google Chrome para falar pelo microfone.";
$("microphone").addEventListener("click", () => { if (voice.active) voice.stop(); else if (!busy()) { window.speechSynthesis?.cancel(); voice.start($("message").value); } });
document.addEventListener("visibilitychange", () => { if (document.hidden && voice.active) voice.cancel(); });
openMic = new CairoOpenMic({
  Recognition: voice.Recognition,
  blocked: () => state.sending || Boolean(currentRun() && (!terminal.has(currentRun().status) || polling.has(currentRun().id))) || Boolean(window.speechSynthesis?.speaking || window.speechSynthesis?.pending),
  onText: (text) => { $("message").value = text; },
  onCommand: () => { $("chat-form").requestSubmit(); },
  onState: (status) => {
    const enabled = Boolean(openMic?.enabled);
    $("voice-status").textContent = enabled ? "Ditado avulso desativado durante escuta contínua" : "Microfone desligado";
    $("open-mic").textContent = enabled ? "Parar escuta" : "Escuta contínua";
    $("open-mic").setAttribute("aria-pressed", String(enabled));
    $("open-mic").classList.toggle("listening", enabled);
    $("open-mic-status").textContent = {off:"Escuta contínua desligada", waiting:"Escuta ativa · aguardando concluir comando ou voz…", starting:"Escuta ativa · iniciando microfone…", listening:"Escuta ativa · Ouvindo próximo comando", stopping:"Escuta ativa · concluindo frase…"}[status];
    updateControls();
  },
  onError: (message) => { showError(message); }
});
$("open-mic").addEventListener("click", () => {
  if (openMic.enabled) { openMic.stop(); return; }
  if (busy()) return;
  if ($("message").value.trim()) { showError("Envie ou limpe o texto antes de iniciar a escuta contínua."); return; }
  showError(); window.speechSynthesis?.cancel(); openMic.start();
});
window.addEventListener("pagehide", () => { openMic.stop(); voice.cancel(); });
initialize();

function toggleTeam(open) {
  $("activity-panel").classList.toggle("is-open", open);
  $("team-toggle").setAttribute("aria-expanded", String(open));
  if (open) $("team-close").focus(); else $("team-toggle").focus();
}
$("team-toggle").addEventListener("click", () => toggleTeam(!$("activity-panel").classList.contains("is-open")));
$("team-close").addEventListener("click", () => toggleTeam(false));
document.addEventListener("keydown", (event) => { if (event.key === "Escape" && $("activity-panel").classList.contains("is-open")) toggleTeam(false); });

function speakText(text) {
  openMic?.pause();
  if (!window.speechSynthesis) { showError("Voz de saída indisponível neste navegador."); return; }
  voice?.cancel();
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text.slice(0, 12000));
  utterance.lang = "pt-BR";
  const portuguese = window.speechSynthesis.getVoices().find((v) => v.lang === "pt-BR");
  if (portuguese) utterance.voice = portuguese;
  utterance.onerror = (event) => { if (!["interrupted", "canceled"].includes(event.error)) showError("Não foi possível reproduzir a voz: " + event.error); };
  window.speechSynthesis.speak(utterance);
}
$("stop-speaking").addEventListener("click", () => window.speechSynthesis?.cancel());
window.addEventListener("pagehide", () => window.speechSynthesis?.cancel());
$("export-chat").addEventListener("click", async () => {
  if (!state.session) { showError("Abra uma conversa antes de exportar."); return; }
  try {
    const session = await api(`/api/sessions/${encodeURIComponent(state.session.id)}`);
    const text = JSON.stringify(session, null, 2);
    const url = URL.createObjectURL(new Blob([text], {type:"application/json;charset=utf-8"}));
    const link = document.createElement("a"); link.href = url; link.download = `cairo-${session.id}.json`;
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) { showError(error.message); }
});
let remindersLoading = false;
async function refreshReminders() {
  if (remindersLoading) return;
  remindersLoading = true;
  try {
    const items = await api("/api/reminders");
    $("reminders").replaceChildren();
    let dueCount = 0;
    for (const item of items) {
      const due = new Date(item.due) <= new Date();
      if (due) dueCount++;
      const row = node("div", `reminder-item${due ? " due" : ""}`);
      row.append(node("div", "", `${due ? "Agora: " : ""}${item.text}`), node("small", "", new Date(item.due).toLocaleString("pt-BR")));
      const dismiss = node("button", "", due ? "Concluir" : "Cancelar lembrete");
      dismiss.addEventListener("click", async () => {
        dismiss.disabled = true;
        try { await api("/api/reminders/dismiss", {method:"POST", body:JSON.stringify({id:item.id, session_id:item.session_id})}); await refreshReminders(); }
        catch(error) { showError(error.message); dismiss.disabled = false; }
      });
      row.append(dismiss); $("reminders").append(row);
    }
    $("reminder-status").textContent = dueCount ? `${dueCount} lembrete(s) aguardando você.` : `${items.length} lembrete(s) agendado(s).`;
    if (dueCount) document.querySelector(".daily-tools").open = true;
  } catch (_) { $("reminder-status").textContent = "Agenda sem conexão. Tentando novamente…"; }
  finally { remindersLoading = false; }
}
$("reminder-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.submitter; if (button) button.disabled = true;
  try {
    const text = $("reminder-text").value.trim();
    const due = new Date($("reminder-due").value).toISOString();
    let sessionId = state.session?.id;
    if (!sessionId) {
      const session = await api("/api/sessions", {method:"POST",body:"{}"});
      sessionId = session.id; await refreshSessions(); await openSession(sessionId);
    }
    await api("/api/reminders", {method:"POST",body:JSON.stringify({session_id:sessionId,text,due})});
    $("reminder-text").value = ""; showError(); await refreshReminders();
  } catch(error) { showError(error.message); }
  finally { if (button) button.disabled = false; }
});
refreshReminders();
setInterval(refreshReminders, 5000);

function prepareDraft(text) {
  if (busy()) { showError("Aguarde a execução terminar ou pressione Parar para preparar outro pedido."); return; }
  openMic?.stop(); voice?.cancel();
  $("message").value = text;
  $("message").focus();
  $("message").dispatchEvent(new Event("input", {bubbles:true}));
}

let savedShortcuts = [];
try { if (globalThis.CairoClient) savedShortcuts = CairoClient.shortcuts(JSON.parse(localStorage.getItem("cairo-shortcuts") || "[]")); }
catch (_) { /* An invalid preference must not prevent chatting. */ }
function renderShortcuts() {
  $("shortcuts").replaceChildren();
  if (!savedShortcuts.length) $("shortcuts").append(node("p", "", "Salve pedidos que você usa com frequência."));
  savedShortcuts.forEach((item, index) => {
    const row = node("div", "shortcut-row");
    const use = node("button", "", item.name);
    use.type = "button"; use.title = item.prompt;
    use.addEventListener("click", () => prepareDraft(item.prompt));
    const remove = node("button", "", "×");
    remove.type = "button"; remove.setAttribute("aria-label", "Remover atalho " + item.name);
    remove.addEventListener("click", () => {
      const next = savedShortcuts.filter((_, i) => i !== index);
      try { localStorage.setItem("cairo-shortcuts", JSON.stringify(next)); savedShortcuts = next; renderShortcuts(); }
      catch (_) { showError("O navegador não permitiu salvar a alteração dos atalhos."); }
    });
    row.append(use, remove); $("shortcuts").append(row);
  });
}
$("save-shortcut").addEventListener("click", () => {
  if (!globalThis.CairoClient) { showError("Reinicie Cairo para carregar a atualização."); return; }
  const prompt = $("message").value.trim();
  if (!prompt) { showError("Escreva um pedido antes de salvar o atalho."); return; }
  if (savedShortcuts.length >= 12) { showError("Você já tem 12 atalhos. Remova um para adicionar outro."); return; }
  const name = $("shortcut-name").value.trim() || prompt.slice(0, 40);
  const next = CairoClient.shortcuts([...savedShortcuts, {name, prompt}]);
  try { localStorage.setItem("cairo-shortcuts", JSON.stringify(next)); savedShortcuts = next; renderShortcuts(); $("shortcut-name").value = ""; showError(); }
  catch (_) { showError("O navegador não permitiu salvar atalhos neste perfil."); }
});
renderShortcuts();

async function refreshDiagnostics() {
  const panel = $("diagnostics");
  panel.hidden = false;
  panel.replaceChildren(node("p", "", "Verificando o Cairo…"));
  try {
    const result = await api("/api/diagnostics");
    panel.replaceChildren(node("h3", "", `Cairo ${result.version}`));
    panel.append(node("p", "", `Processo ${result.pid} · ${result.max_steps} etapas por agente`));
    $("update-banner").hidden = !result.restart_required;
    $("update-banner").textContent = result.restart_required ? "Atualização instalada: encerre o Cairo com Ctrl+C e abra novamente. A instância atual ainda usa arquivos anteriores." : "";
    for (const item of result.checks) {
      const row = node("div", "diagnostic-item " + item.status);
      row.append(node("strong", "", (item.status === "ok" ? "✓ " : "! ") + item.label), node("p", "", item.detail));
      panel.append(row);
    }
    if (result.historical_errors.length) {
      panel.append(node("h4", "", "Histórico de falhas"));
      for (const item of result.historical_errors) panel.append(node("p", "", `${item.label}: ${item.count}`));
    }
    panel.append(node("p", "diagnostic-note", result.history_note));
  } catch (error) { panel.replaceChildren(node("p", "", error.status === 404 ? "O servidor ainda usa a versão anterior. Encerre Cairo com Ctrl+C e abra novamente." : error.message)); }
}
$("check-cairo").addEventListener("click", refreshDiagnostics);
async function checkRuntimeUpdate() {
  try {
    const result = await api("/api/diagnostics");
    $("update-banner").hidden = !result.restart_required;
    $("update-banner").textContent = result.restart_required ? "Atualização instalada. Encerre o Cairo com Ctrl+C e abra novamente para carregar as mudanças." : "";
  } catch (error) {
    if (error.status === 404) { $("update-banner").hidden = false; $("update-banner").textContent = "O servidor usa uma versão anterior. Reinicie o Cairo para carregar a atualização."; }
  }
}
checkRuntimeUpdate();
setInterval(checkRuntimeUpdate, 60000);
$("check-model").addEventListener("click", async () => {
  const button = $("check-model");
  button.disabled = true; $("model-health").textContent = "Consultando o provedor…";
  try {
    const result = await api("/api/ai/health");
    $("model-health").textContent = `${result.provider || "IA"}: ${result.status}. Modelo: ${result.selected_model || "padrão do gateway"}. ` + (result.ready ? "Pronto para uso segundo o catálogo/configuração." : result.error?.message || result.note || "Confira a configuração do modelo.");
  } catch (error) { $("model-health").textContent = error.message; }
  finally { button.disabled = false; }
});
