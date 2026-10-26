"use strict";

async function loadMoreSessions(button) {
  if (state.sending) return;
  const version = state.searchVersion;
  const offset = state.sessionsOffset;
  button.disabled = true;
  try {
    const items = await api("/api/sessions?" + new URLSearchParams({
      q: $("session-search").value, archived: state.archived ? "1" : "0", offset,
    }));
    if (version !== state.searchVersion) return;
    const known = new Set(state.sessions.map(item => item.id));
    state.sessions.push(...items.filter(item => !known.has(item.id)));
    state.sessionsOffset += items.length;
    state.hasMoreSessions = items.length === 200;
    renderSessions();
  } catch (error) { showError(error.message); button.disabled = false; }
}

function mergeSessionHistory(session) {
  if (state.session?.id === session.id && session.messages.length && session.message_count >= state.session.message_count) {
    const first = session.messages[0].id;
    session.messages = [
      ...state.session.messages.filter(message => Number.isInteger(message.id) && message.id < first),
      ...session.messages,
    ];
  }
  state.session = session;
}

async function loadOlderMessages(button) {
  const sessionId = state.session?.id;
  const version = state.loadVersion;
  const first = state.session?.messages.find(message => Number.isInteger(message.id));
  if (!sessionId || !first) return;
  button.disabled = true;
  try {
    const result = await api(`/api/sessions/${encodeURIComponent(sessionId)}/messages?before=${first.id}`);
    if (state.session?.id !== sessionId || version !== state.loadVersion) return;
    const pane = $("conversation");
    const oldHeight = pane.scrollHeight, oldTop = pane.scrollTop;
    const known = new Set(state.session.messages.map(message => message.id));
    state.session.messages.unshift(...result.messages.filter(message => !known.has(message.id)));
    renderMessages();
    pane.scrollTop = oldTop + pane.scrollHeight - oldHeight;
    if (!result.has_more) {
      const remaining = $("messages").querySelector(".load-history");
      remaining?.remove();
    }
  } catch (error) { showError(error.message); button.disabled = false; }
}

$("import-conversation").addEventListener("change", async (event) => {
  const input = event.target, file = input.files?.[0];
  if (!file) return;
  input.disabled = true;
  $("import-status").textContent = "Conferindo conversa…";
  try {
    if (state.sending) throw new Error("Aguarde o envio atual antes de importar.");
    if (file.size > 8 * 1024 * 1024) throw new Error("Selecione um arquivo JSON de até 8 MB.");
    let document;
    try { document = JSON.parse(await file.text()); }
    catch (_) { throw new Error("O arquivo não contém um JSON válido."); }
    const session = await api("/api/sessions/import", {method:"POST", body:JSON.stringify(document), timeoutMs:60000});
    $("session-search").value = "";
    setSessionFilter(false);
    await openSession(session.id);
    $("import-status").textContent = `Importação concluída: ${session.imported_messages} mensagens e ${session.imported_notes} notas. As conversas existentes foram preservadas.`;
  } catch (error) { $("import-status").textContent = error.message; }
  finally { input.disabled = false; input.value = ""; }
});

// The browser can suspend this tab while another tab starts or completes a run.
document.addEventListener("visibilitychange", async () => {
  if (document.hidden || state.sending || !state.session) return;
  const id = state.session.id, version = state.loadVersion;
  try {
    const session = await api(`/api/sessions/${encodeURIComponent(id)}`);
    if (id !== state.session?.id || version !== state.loadVersion) return;
    mergeSessionHistory(session);
    $("chat-title").textContent = session.title;
    const latest = session.runs.find(run => !terminal.has(run.status)) || session.runs[0];
    if (latest) {
      const run = await api(`/api/runs/${encodeURIComponent(latest.id)}`);
      state.runs.set(id, run);
      if (!terminal.has(run.status)) pollRun(id, run.id);
    } else state.runs.delete(id);
    if (id !== state.session?.id || version !== state.loadVersion) return;
    renderMessages(); renderActivity(currentRun());
    const run = currentRun();
    if (run?.status === "failed" && run.error) showError(run.error);
  } catch (error) { if (id === state.session?.id) showError(error.message); }
});
