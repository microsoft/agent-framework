// Copyright (c) Microsoft. All rights reserved.

/// <summary>
/// Static HTML pages served by the sample application.
/// </summary>
internal static class Pages
{
    // ═══════════════════════════════════════════════════════════════════════
    // Homepage
    // ═══════════════════════════════════════════════════════════════════════

    internal const string Home = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Foundry Responses Hosting — Demos</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, sans-serif; background: #f5f5f5; display: flex; justify-content: center; padding: 2rem; }
    main { width: 100%; max-width: 700px; }
    h1 { font-size: 1.5rem; margin-bottom: .5rem; color: #1a1a1a; }
    .subtitle { color: #555; margin-bottom: 2rem; line-height: 1.5; }
    .cards { display: flex; flex-direction: column; gap: 1rem; }
    .card { background: #fff; border: 1px solid #ddd; border-radius: 10px; padding: 1.5rem; text-decoration: none; color: inherit; transition: box-shadow .15s, transform .15s; }
    .card:hover { box-shadow: 0 4px 16px rgba(0,0,0,.1); transform: translateY(-2px); }
    .card h2 { font-size: 1.15rem; color: #0066cc; margin-bottom: .4rem; }
    .card p { color: #555; line-height: 1.5; font-size: .9rem; }
    .card .tags { margin-top: .6rem; display: flex; gap: .4rem; flex-wrap: wrap; }
    .card .tag { background: #e8f0fe; color: #1a73e8; padding: .15rem .5rem; border-radius: 12px; font-size: .75rem; }
    footer { margin-top: 2rem; font-size: .8rem; color: #999; text-align: center; }
  </style>
</head>
<body>
  <main>
    <h1>🚀 Foundry Responses Hosting</h1>
    <p class="subtitle">
      Agent-framework agents hosted via the Azure AI Responses Server SDK.<br/>
      Each demo registers a different agent and serves it through <code>POST /responses</code>.
    </p>
    <div class="cards">
      <a class="card" href="/tool-demo">
        <h2>🔧 Tool Demo</h2>
        <p>An agent with local function tools (time, weather) and remote MCP tools from
           Microsoft Learn for documentation search.</p>
        <div class="tags">
          <span class="tag">Local Tools</span>
          <span class="tag">MCP</span>
          <span class="tag">Microsoft Learn</span>
          <span class="tag">Streaming</span>
        </div>
      </a>
      <a class="card" href="/workflow-demo">
        <h2>🔀 Workflow Demo</h2>
        <p>A triage workflow that routes questions to specialist agents — a Code Expert
           or a Creative Writer — using agent handoffs.</p>
        <div class="tags">
          <span class="tag">Workflow</span>
          <span class="tag">Handoffs</span>
          <span class="tag">Multi-Agent</span>
          <span class="tag">Triage</span>
        </div>
      </a>

    </div>
    <footer>
      All demos share the same <code>/responses</code> endpoint.
      The <code>model</code> field in the request selects which agent handles it.
    </footer>
  </main>
</body>
</html>
""";

    // ═══════════════════════════════════════════════════════════════════════
    // Tool Demo
    // ═══════════════════════════════════════════════════════════════════════

    internal const string ToolDemo = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Tool Demo — Foundry Responses Hosting</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, sans-serif; background: #f5f5f5; display: flex; justify-content: center; padding: 2rem; }
    main { width: 100%; max-width: 800px; }
    h1 { font-size: 1.2rem; margin-bottom: .3rem; color: #333; }
    .subtitle { font-size: .85rem; color: #666; margin-bottom: .8rem; }
    a.back { font-size: .85rem; color: #0066cc; text-decoration: none; display: inline-block; margin-bottom: 1rem; }
    #chat { background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 1rem; height: 56vh; overflow-y: auto; margin-bottom: 1rem; }
    .msg { margin-bottom: .75rem; line-height: 1.6; }
    .msg.user { color: #0066cc; }
    .msg.assistant { color: #333; }
    .msg .role { font-weight: 600; margin-right: .25rem; }
    .tool-call { background: #f0f4ff; border-left: 3px solid #4a90d9; padding: .4rem .6rem; margin: .4rem 0; border-radius: 4px; font-size: .85rem; color: #555; font-family: 'Cascadia Code', 'Fira Code', monospace; }
    .tool-call .tool-icon { margin-right: .3rem; }
    form { display: flex; gap: .5rem; }
    input { flex: 1; padding: .6rem .8rem; border: 1px solid #ccc; border-radius: 6px; font-size: 1rem; }
    button { padding: .6rem 1.2rem; background: #0066cc; color: #fff; border: none; border-radius: 6px; font-size: 1rem; cursor: pointer; }
    button:disabled { opacity: .5; cursor: not-allowed; }
    #status { font-size: .85rem; color: #888; margin-top: .5rem; }
    .suggestions { display: flex; flex-wrap: wrap; gap: .4rem; margin-bottom: 1rem; }
    .suggestions button { padding: .3rem .7rem; font-size: .8rem; background: #e8f0fe; color: #1a73e8; border: 1px solid #c5d8f8; border-radius: 16px; cursor: pointer; }
    .suggestions button:hover { background: #d2e3fc; }
  </style>
</head>
<body>
  <main>
    <a class="back" href="/">← Back to demos</a>
    <h1>🔧 Tool Demo</h1>
    <p class="subtitle">Agent with local tools (time, weather) + Microsoft Learn MCP (docs search)</p>
    <div class="suggestions">
      <button onclick="sendText('What time is it in Tokyo?')">🕐 Time in Tokyo</button>
      <button onclick="sendText('What is the weather in Seattle?')">🌤️ Weather in Seattle</button>
      <button onclick="sendText('How do I create an Azure Function using the CLI?')">📚 Azure Functions docs</button>
      <button onclick="sendText('What is Microsoft Agent Framework?')">📚 Agent Framework</button>
    </div>
    <div id="chat"></div>
    <form id="form">
      <input id="input" placeholder="Try: 'What time is it?' or 'Search docs for Azure AI Foundry'" autocomplete="off" autofocus />
      <button type="submit">Send</button>
    </form>
    <div id="status"></div>
  </main>
  <script src="/js/sse-validator.js"></script>
  <script>
    const AGENT = 'tool-agent';
    const chat = document.getElementById('chat');
    const form = document.getElementById('form');
    const input = document.getElementById('input');
    const status = document.getElementById('status');

    function escapeHtml(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

    function addMsg(role, html) {
      const d = document.createElement('div');
      d.className = 'msg ' + role; d.innerHTML = html;
      chat.appendChild(d); chat.scrollTop = chat.scrollHeight; return d;
    }

    function addToolCall(name) {
      const d = document.createElement('div');
      d.className = 'tool-call';
      d.innerHTML = '<span class="tool-icon">🔧</span> Calling <b>' + escapeHtml(name) + '</b>…';
      chat.appendChild(d); chat.scrollTop = chat.scrollHeight; return d;
    }

    function sendText(t) { input.value = t; form.dispatchEvent(new Event('submit')); }

    form.addEventListener('submit', async e => {
      e.preventDefault();
      const text = input.value.trim(); if (!text) return;
      input.value = '';
      addMsg('user', '<span class="role">You:</span>' + escapeHtml(text));

      const btn = form.querySelector('button[type="submit"]');
      btn.disabled = true; status.textContent = 'Streaming…';

      let fullText = '', assistantDiv = null;
      const toolCalls = {};
      const validator = new SseValidator();

      try {
        const resp = await fetch('/responses', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model: AGENT, stream: true, input: text })
        });
        if (!resp.ok) { status.textContent = 'Error ' + resp.status; btn.disabled = false; return; }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buf = '', curEvt = null;
        while (true) {
          const { done, value } = await reader.read(); if (done) break;
          buf += decoder.decode(value, { stream: true });
          const lines = buf.split('\n'); buf = lines.pop();
          for (const line of lines) {
            if (line.startsWith('event: ')) { curEvt = line.slice(7).trim(); continue; }
            if (!line.startsWith('data: ')) continue;
            const d = line.slice(6).trim(); if (d === '[DONE]') continue;
            try {
              const evt = JSON.parse(d);
              validator.capture(curEvt || evt.type || 'unknown', d);
              curEvt = null;
              if (evt.type === 'response.output_item.added' && evt.item?.type === 'function_call') {
                const id = evt.item.id;
                toolCalls[id] = { name: evt.item.name || '?', args: '', el: addToolCall(evt.item.name || '?') };
                status.textContent = 'Calling tool: ' + (evt.item.name || '…');
              }
              if (evt.type === 'response.function_call_arguments.delta' && evt.item_id && toolCalls[evt.item_id])
                toolCalls[evt.item_id].args += (evt.delta || '');
              if (evt.type === 'response.function_call_arguments.done' && evt.item_id && toolCalls[evt.item_id]) {
                const tc = toolCalls[evt.item_id];
                let args = tc.args; try { args = JSON.stringify(JSON.parse(args), null, 0); } catch {}
                tc.el.innerHTML = '<span class="tool-icon">✅</span> Called <b>' + escapeHtml(tc.name) + '</b>(' + escapeHtml(args) + ')';
              }
              if (evt.type === 'response.output_text.delta') {
                if (!assistantDiv) assistantDiv = addMsg('assistant', '<span class="role">Agent:</span>');
                fullText += evt.delta;
                assistantDiv.innerHTML = '<span class="role">Agent:</span>' + escapeHtml(fullText);
                chat.scrollTop = chat.scrollHeight;
                status.textContent = 'Streaming…';
              }
            } catch {}
          }
        }
        if (!fullText && !assistantDiv) addMsg('assistant', '<span class="role">Agent:</span><em>(empty)</em>');
        status.textContent = '';
      } catch (err) { status.textContent = 'Error: ' + err.message; }
      if (validator.events.length > 0) {
        try { const vr = await validator.validate(); chat.appendChild(validator.renderElement(vr)); chat.scrollTop = chat.scrollHeight; } catch {}
      }
      btn.disabled = false; input.focus();
    });
  </script>
</body>
</html>
""";

    // ═══════════════════════════════════════════════════════════════════════
    // Workflow Demo
    // ═══════════════════════════════════════════════════════════════════════

    internal const string WorkflowDemo = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Workflow Demo — Foundry Responses Hosting</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, sans-serif; background: #f5f5f5; display: flex; justify-content: center; padding: 2rem; }
    main { width: 100%; max-width: 800px; }
    h1 { font-size: 1.2rem; margin-bottom: .3rem; color: #333; }
    .subtitle { font-size: .85rem; color: #666; margin-bottom: .8rem; }
    a.back { font-size: .85rem; color: #0066cc; text-decoration: none; display: inline-block; margin-bottom: 1rem; }
    #chat { background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 1rem; height: 56vh; overflow-y: auto; margin-bottom: 1rem; }
    .msg { margin-bottom: .75rem; line-height: 1.6; }
    .msg.user { color: #0066cc; }
    .msg.assistant { color: #333; }
    .msg .role { font-weight: 600; margin-right: .25rem; }
    .workflow-evt { background: #f0f9f0; border-left: 3px solid #4caf50; padding: .4rem .6rem; margin: .4rem 0; border-radius: 4px; font-size: .85rem; color: #555; }
    .workflow-evt.failed { background: #fef0f0; border-left-color: #e53935; }
    .tool-call { background: #f0f4ff; border-left: 3px solid #4a90d9; padding: .4rem .6rem; margin: .4rem 0; border-radius: 4px; font-size: .85rem; color: #555; font-family: 'Cascadia Code', 'Fira Code', monospace; }
    form { display: flex; gap: .5rem; }
    input { flex: 1; padding: .6rem .8rem; border: 1px solid #ccc; border-radius: 6px; font-size: 1rem; }
    button { padding: .6rem 1.2rem; background: #0066cc; color: #fff; border: none; border-radius: 6px; font-size: 1rem; cursor: pointer; }
    button:disabled { opacity: .5; cursor: not-allowed; }
    #status { font-size: .85rem; color: #888; margin-top: .5rem; }
    .suggestions { display: flex; flex-wrap: wrap; gap: .4rem; margin-bottom: 1rem; }
    .suggestions button { padding: .3rem .7rem; font-size: .8rem; background: #e8f0fe; color: #1a73e8; border: 1px solid #c5d8f8; border-radius: 16px; cursor: pointer; }
    .suggestions button:hover { background: #d2e3fc; }
    .agent-diagram { background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; font-size: .85rem; text-align: center; color: #555; }
    .agent-diagram .flow { font-size: 1.1rem; letter-spacing: 2px; }
  </style>
</head>
<body>
  <main>
    <a class="back" href="/">← Back to demos</a>
    <h1>🔀 Workflow Demo — Agent Handoffs</h1>
    <p class="subtitle">A triage agent routes your question to a specialist (Code Expert or Creative Writer)</p>
    <div class="agent-diagram">
      <div class="flow">👤 User → 🔀 <b>Triage</b> → 💻 <b>Code Expert</b> / ✍️ <b>Creative Writer</b></div>
    </div>
    <div class="suggestions">
      <button onclick="sendText('Write a Python function to reverse a linked list')">💻 Reverse linked list</button>
      <button onclick="sendText('Write me a haiku about cloud computing')">✍️ Cloud haiku</button>
      <button onclick="sendText('Explain the difference between async and threads in C#')">💻 Async vs threads</button>
      <button onclick="sendText('Write a short story about an AI that learns to paint')">✍️ AI painter story</button>
    </div>
    <div id="chat"></div>
    <form id="form">
      <input id="input" placeholder="Ask a coding question or request creative writing…" autocomplete="off" autofocus />
      <button type="submit">Send</button>
    </form>
    <div id="status"></div>
  </main>
  <script src="/js/sse-validator.js"></script>
  <script>
    const AGENT = 'triage-workflow';
    const chat = document.getElementById('chat');
    const form = document.getElementById('form');
    const input = document.getElementById('input');
    const status = document.getElementById('status');

    function escapeHtml(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

    function addMsg(role, html) {
      const d = document.createElement('div');
      d.className = 'msg ' + role; d.innerHTML = html;
      chat.appendChild(d); chat.scrollTop = chat.scrollHeight; return d;
    }

    function addWorkflowEvent(icon, text, failed) {
      const d = document.createElement('div');
      d.className = 'workflow-evt' + (failed ? ' failed' : '');
      d.innerHTML = icon + ' ' + escapeHtml(text);
      chat.appendChild(d); chat.scrollTop = chat.scrollHeight;
    }

    function addToolCall(name) {
      const d = document.createElement('div');
      d.className = 'tool-call';
      d.innerHTML = '🔀 Handoff: <b>' + escapeHtml(name) + '</b>';
      chat.appendChild(d); chat.scrollTop = chat.scrollHeight; return d;
    }

    function sendText(t) { input.value = t; form.dispatchEvent(new Event('submit')); }

    form.addEventListener('submit', async e => {
      e.preventDefault();
      const text = input.value.trim(); if (!text) return;
      input.value = '';
      addMsg('user', '<span class="role">You:</span>' + escapeHtml(text));

      const btn = form.querySelector('button[type="submit"]');
      btn.disabled = true; status.textContent = 'Running workflow…';

      let fullText = '', assistantDiv = null;
      const toolCalls = {};
      const validator = new SseValidator();

      try {
        const resp = await fetch('/responses', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model: AGENT, stream: true, input: text })
        });
        if (!resp.ok) { status.textContent = 'Error ' + resp.status; btn.disabled = false; return; }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buf = '', curEvt = null;
        while (true) {
          const { done, value } = await reader.read(); if (done) break;
          buf += decoder.decode(value, { stream: true });
          const lines = buf.split('\n'); buf = lines.pop();
          for (const line of lines) {
            if (line.startsWith('event: ')) { curEvt = line.slice(7).trim(); continue; }
            if (!line.startsWith('data: ')) continue;
            const d = line.slice(6).trim(); if (d === '[DONE]') continue;
            try {
              const evt = JSON.parse(d);
              validator.capture(curEvt || evt.type || 'unknown', d);
              curEvt = null;

              // Workflow events (executor invoked/completed/failed)
              if (evt.type === 'response.output_item.added' && evt.item?.type === 'workflow_action') {
                const s = evt.item.status;
                const id = evt.item.action_id || evt.item.actionId || '?';
                if (s === 'in_progress' || s === 'InProgress')
                  addWorkflowEvent('▶️', 'Agent invoked: ' + id);
                else if (s === 'completed' || s === 'Completed')
                  addWorkflowEvent('✅', 'Agent completed: ' + id);
                else if (s === 'failed' || s === 'Failed')
                  addWorkflowEvent('❌', 'Agent failed: ' + id, true);
              }

              // Handoff function calls
              if (evt.type === 'response.output_item.added' && evt.item?.type === 'function_call') {
                const id = evt.item.id;
                toolCalls[id] = { name: evt.item.name || '?', args: '', el: addToolCall(evt.item.name || '?') };
                status.textContent = 'Handoff: ' + (evt.item.name || '…');
              }
              if (evt.type === 'response.function_call_arguments.delta' && evt.item_id && toolCalls[evt.item_id])
                toolCalls[evt.item_id].args += (evt.delta || '');
              if (evt.type === 'response.function_call_arguments.done' && evt.item_id && toolCalls[evt.item_id]) {
                const tc = toolCalls[evt.item_id];
                let args = tc.args; try { args = JSON.stringify(JSON.parse(args), null, 0); } catch {}
                tc.el.innerHTML = '🔀 Handoff: <b>' + escapeHtml(tc.name) + '</b>(' + escapeHtml(args) + ')';
              }

              // Text streaming from the specialist agent
              if (evt.type === 'response.output_text.delta') {
                if (!assistantDiv) assistantDiv = addMsg('assistant', '<span class="role">Agent:</span>');
                fullText += evt.delta;
                assistantDiv.innerHTML = '<span class="role">Agent:</span>' + escapeHtml(fullText);
                chat.scrollTop = chat.scrollHeight;
                status.textContent = 'Streaming…';
              }
            } catch {}
          }
        }
        if (!fullText && !assistantDiv) addMsg('assistant', '<span class="role">Agent:</span><em>(empty)</em>');
        status.textContent = '';
      } catch (err) { status.textContent = 'Error: ' + err.message; }
      if (validator.events.length > 0) {
        try { const vr = await validator.validate(); chat.appendChild(validator.renderElement(vr)); chat.scrollTop = chat.scrollHeight; } catch {}
      }
      btn.disabled = false; input.focus();
    });
  </script>
</body>
</html>
""";

    // ═══════════════════════════════════════════════════════════════════════
    // SSE Validator Script (shared by all demo pages)
    // ═══════════════════════════════════════════════════════════════════════

    internal const string ValidationScript = """
// SseValidator - inline SSE stream validation for Foundry Responses demos
// Captures events during streaming and validates against the API behaviour contract.
(function() {
  const style = document.createElement('style');
  style.textContent = `
    .sse-val { margin: .4rem 0 .6rem; padding: .3rem .5rem; font-size: .75rem; color: #aaa; border-top: 1px dashed #e8e8e8; }
    .val-ok { color: #7ab88a; }
    .val-err { color: #d47272; font-weight: 500; }
    .val-issues { margin: .2rem 0; }
    .val-issue { color: #c06060; font-size: .72rem; padding: .1rem 0; }
    .val-issue b { color: #b04040; }
    .val-at { color: #ccc; font-size: .68rem; }
    .val-log summary { cursor: pointer; color: #bbb; font-size: .72rem; }
    .val-log-items { max-height: 120px; overflow-y: auto; font-size: .7rem; background: #fafafa;
      padding: .3rem; border-radius: 3px; margin-top: .15rem;
      font-family: 'Cascadia Code', 'Fira Code', monospace; }
    .val-i { color: #ccc; display: inline-block; width: 1.8rem; text-align: right; margin-right: .3rem; }
    .val-t { color: #8ab4d0; }
  `;
  document.head.appendChild(style);
})();

class SseValidator {
  constructor() { this.events = []; }
  reset() { this.events = []; }
  capture(eventType, data) { this.events.push({ eventType, data }); }

  async validate() {
    const resp = await fetch('/api/validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ events: this.events })
    });
    return await resp.json();
  }

  renderElement(result) {
    const el = document.createElement('div');
    el.className = 'sse-val';
    const n = result.eventCount;
    const ok = result.isValid;
    const vs = result.violations || [];
    const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

    let h = ok
      ? `<span class="val-ok">${n} events — all rules passed ✅</span>`
      : `<span class="val-err">${n} events — ${vs.length} violation(s)</span>`;

    if (vs.length) {
      h += '<div class="val-issues">';
      vs.forEach(v => {
        h += `<div class="val-issue"><b>[${esc(v.ruleId)}]</b> ${esc(v.message)} <span class="val-at">#${v.eventIndex}</span></div>`;
      });
      h += '</div>';
    }

    h += `<details class="val-log"><summary>Event log (${this.events.length})</summary><div class="val-log-items">`;
    this.events.forEach((e, i) => {
      h += `<div><span class="val-i">${i}</span> <span class="val-t">${esc(e.eventType)}</span></div>`;
    });
    h += '</div></details>';

    el.innerHTML = h;
    return el;
  }
}
""";
}
