import os
import json
from flask import Flask, request, jsonify, render_template_string
from google.genai import types
from gemini import llm_client, MODEL, extract_text
from tools import CONFIRM_REQUIRED, HISTORY_FILE, execute_function, make_gemini_config

gemini_config = make_gemini_config()

# Per-session chat histories (simple in-memory store)
sessions = {}

app = Flask(__name__)


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/api/history")
def history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            return jsonify(json.load(f))
    return jsonify([])


@app.route("/api/chat/clear", methods=["POST"])
def clear_chat():
    session_id = request.json.get("session_id", "default")
    sessions.pop(session_id, None)
    return jsonify({"status": "ok"})


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json
    msg = data.get("message", "").strip()
    session_id = data.get("session_id", "default")
    confirmed = data.get("confirmed")

    if not msg and confirmed is None:
        return jsonify({"error": "No message"}), 400

    if session_id not in sessions:
        sessions[session_id] = {
            "contents": [
                types.Content(role="user", parts=[types.Part(text="You are my trading assistant.")]),
                types.Content(role="model", parts=[types.Part(text="I'm your DhanHQ trading assistant. How can I help?")]),
            ],
            "pending_confirmation": None,
        }

    session = sessions[session_id]
    contents = session["contents"]

    # Handle confirmation response
    if confirmed is not None and session["pending_confirmation"]:
        pc = session["pending_confirmation"]
        session["pending_confirmation"] = None

        if confirmed:
            result = execute_function(pc["func_name"], pc["args"])
        else:
            result = {"status": "cancelled", "message": "User declined"}

        contents.append(pc["gemini_content"])
        contents.append(types.Content(role="user", parts=[
            types.Part.from_function_response(name=pc["func_name"], response=result)
        ]))

        response = llm_client.models.generate_content(model=MODEL, contents=contents, config=gemini_config)
        return _process_response(response, contents, session)

    # Normal message
    contents.append(types.Content(role="user", parts=[types.Part(text=msg)]))

    try:
        response = llm_client.models.generate_content(model=MODEL, contents=contents, config=gemini_config)
        return _process_response(response, contents, session)
    except Exception as e:
        contents.pop()
        return jsonify({"error": str(e)}), 500


def _process_response(response, contents, session):
    """Process Gemini response, handling function calls and confirmations."""
    for _ in range(10):
        if not response.candidates or not response.candidates[0].content.parts:
            break

        function_calls = [p for p in response.candidates[0].content.parts if p.function_call]
        if not function_calls:
            break

        contents.append(response.candidates[0].content)
        function_response_parts = []

        for part in function_calls:
            fc = part.function_call
            func_name = fc.name
            args = dict(fc.args)

            if func_name in CONFIRM_REQUIRED:
                session["pending_confirmation"] = {
                    "func_name": func_name,
                    "args": args,
                    "gemini_content": response.candidates[0].content,
                }
                contents.pop()
                return jsonify({
                    "needs_confirmation": True,
                    "action": func_name,
                    "args": args,
                })

            result = execute_function(func_name, args)
            function_response_parts.append(
                types.Part.from_function_response(name=func_name, response=result)
            )

        if function_response_parts:
            contents.append(types.Content(role="user", parts=function_response_parts))
            response = llm_client.models.generate_content(model=MODEL, contents=contents, config=gemini_config)

    # Extract final text
    text = ""
    if response.candidates and response.candidates[0].content.parts:
        contents.append(response.candidates[0].content)
        text = extract_text(response)

    return jsonify({"response": text})


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DhanHQ Trading Assistant</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; background: #0f1117; color: #e1e4e8; height: 100vh; display: flex; flex-direction: column; }
.tabs { display: flex; background: #161b22; border-bottom: 1px solid #30363d; }
.tab { padding: 12px 24px; cursor: pointer; border-bottom: 2px solid transparent; color: #8b949e; font-size: 14px; }
.tab.active { color: #58a6ff; border-bottom-color: #58a6ff; }
.tab:hover { color: #c9d1d9; }
.panel { flex: 1; display: none; overflow: hidden; flex-direction: column; }
.panel.active { display: flex; }

/* Chat */
#chat-messages { flex: 1; overflow-y: auto; padding: 16px; }
.msg { max-width: 80%; margin: 8px 0; padding: 10px 14px; border-radius: 12px; line-height: 1.5; font-size: 14px; white-space: pre-wrap; word-wrap: break-word; }
.msg.user { background: #1f6feb; margin-left: auto; border-bottom-right-radius: 4px; }
.msg.bot { background: #21262d; border: 1px solid #30363d; border-bottom-left-radius: 4px; }
.msg.confirm { background: #1c2128; border: 1px solid #d29922; }
.confirm-btns { margin-top: 8px; }
.confirm-btns button { padding: 6px 16px; margin-right: 8px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; }
.btn-yes { background: #238636; color: #fff; }
.btn-no { background: #da3633; color: #fff; }
.btn-yes:hover { background: #2ea043; }
.btn-no:hover { background: #e5534b; }
#chat-input-area { padding: 12px 16px; border-top: 1px solid #30363d; display: flex; gap: 8px; }
#chat-input { flex: 1; padding: 10px 14px; border-radius: 8px; border: 1px solid #30363d; background: #0d1117; color: #e1e4e8; font-size: 14px; outline: none; }
#chat-input:focus { border-color: #58a6ff; }
#send-btn { padding: 10px 20px; background: #238636; color: #fff; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; }
#send-btn:hover { background: #2ea043; }
#send-btn:disabled { background: #21262d; cursor: not-allowed; }
#clear-btn { padding: 10px 14px; background: #21262d; color: #8b949e; border: 1px solid #30363d; border-radius: 8px; cursor: pointer; font-size: 14px; }
#clear-btn:hover { color: #f85149; border-color: #f85149; }
.typing { color: #8b949e; font-style: italic; padding: 8px 14px; }

/* History */
#history-panel { padding: 16px; overflow-y: auto; }
.history-card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; margin-bottom: 12px; }
.history-date { color: #58a6ff; font-weight: 600; font-size: 15px; margin-bottom: 6px; }
.history-reasoning { color: #8b949e; font-size: 13px; margin-bottom: 10px; font-style: italic; }
.history-budget { color: #d29922; font-size: 13px; margin-bottom: 10px; }
.history-orders { width: 100%; border-collapse: collapse; font-size: 13px; }
.history-orders th { text-align: left; padding: 6px 10px; color: #8b949e; border-bottom: 1px solid #30363d; }
.history-orders td { padding: 6px 10px; border-bottom: 1px solid #21262d; }
.status-ok { color: #3fb950; }
.status-fail { color: #f85149; }
.history-summary { margin-top: 8px; font-size: 13px; color: #8b949e; }
.empty { text-align: center; color: #484f58; padding: 40px; font-size: 15px; }
</style>
</head>
<body>
<div class="tabs">
  <div class="tab active" onclick="switchTab('chat')">Chat</div>
  <div class="tab" onclick="switchTab('history')">SIP History</div>
</div>

<div id="chat-panel" class="panel active">
  <div id="chat-messages">
    <div class="msg bot">I'm your DhanHQ trading assistant. I can help you place orders, check portfolio, search stocks, and get real-time market insights. What would you like to do?</div>
  </div>
  <div id="chat-input-area">
    <input id="chat-input" placeholder="Ask anything about markets or trading..." autocomplete="off">
    <button id="send-btn" onclick="sendMessage()">Send</button>
    <button id="clear-btn" onclick="clearChat()" title="Clear conversation">Clear</button>
  </div>
</div>

<div id="history-panel" class="panel"></div>

<script>
const sessionId = crypto.randomUUID();
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');

chatInput.addEventListener('keydown', e => { if (e.key === 'Enter' && !sendBtn.disabled) sendMessage(); });

async function clearChat() {
  await fetch('/api/chat/clear', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({session_id: sessionId}),
  });
  chatMessages.innerHTML = '<div class="msg bot">Chat cleared. How can I help?</div>';
}

function switchTab(tab) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelector(`.tab:nth-child(${tab === 'chat' ? 1 : 2})`).classList.add('active');
  document.getElementById(tab + '-panel').classList.add('active');
  if (tab === 'history') loadHistory();
}

function addMessage(text, cls) {
  const d = document.createElement('div');
  d.className = 'msg ' + cls;
  d.textContent = text;
  chatMessages.appendChild(d);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return d;
}

function showConfirmation(action, args) {
  const d = document.createElement('div');
  d.className = 'msg confirm';
  let desc = '';
  if (action === 'place_market_order')
    desc = `${args.transaction_type} ${args.quantity} x ${args.stock_name} at MARKET (${args.product_type || 'CNC'})`;
  else if (action === 'place_limit_order')
    desc = `${args.transaction_type} ${args.quantity} x ${args.stock_name} at ₹${args.price} (${args.product_type || 'CNC'})`;
  else if (action === 'cancel_order')
    desc = `Cancel order ${args.order_id}`;
  d.innerHTML = `<strong>Confirm action:</strong> ${desc}<div class="confirm-btns"><button class="btn-yes" onclick="confirm(true, this)">Yes, execute</button><button class="btn-no" onclick="confirm(false, this)">Cancel</button></div>`;
  chatMessages.appendChild(d);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function confirm(yes, btn) {
  btn.parentElement.querySelectorAll('button').forEach(b => b.disabled = true);
  const typing = addMessage('Processing...', 'typing');
  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({session_id: sessionId, confirmed: yes, message: ''}),
    });
    const data = await res.json();
    typing.remove();
    if (data.needs_confirmation) showConfirmation(data.action, data.args);
    else if (data.response) addMessage(data.response, 'bot');
    else if (data.error) addMessage('Error: ' + data.error, 'bot');
  } catch(e) { typing.remove(); addMessage('Error: ' + e.message, 'bot'); }
}

async function sendMessage() {
  const msg = chatInput.value.trim();
  if (!msg) return;
  chatInput.value = '';
  addMessage(msg, 'user');
  sendBtn.disabled = true;
  const typing = addMessage('Thinking...', 'typing');

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({session_id: sessionId, message: msg}),
    });
    const data = await res.json();
    typing.remove();
    if (data.needs_confirmation) showConfirmation(data.action, data.args);
    else if (data.response) addMessage(data.response, 'bot');
    else if (data.error) addMessage('Error: ' + data.error, 'bot');
  } catch(e) { typing.remove(); addMessage('Error: ' + e.message, 'bot'); }
  sendBtn.disabled = false;
  chatInput.focus();
}

async function loadHistory() {
  const panel = document.getElementById('history-panel');
  try {
    const res = await fetch('/api/history');
    const history = await res.json();
    if (!history.length) { panel.innerHTML = '<div class="empty">No SIP trades yet. History will appear here after your first automated SIP run.</div>'; return; }

    panel.innerHTML = history.slice().reverse().map(h => `
      <div class="history-card">
        <div class="history-date">${h.date}</div>
        <div class="history-budget">Budget: ₹${h.budget.toLocaleString()}</div>
        <div class="history-reasoning">${h.reasoning}</div>
        <table class="history-orders">
          <tr><th>ETF</th><th>Qty</th><th>LTP</th><th>Cost</th><th>Status</th></tr>
          ${h.orders.map(o => `<tr>
            <td>${o.stock_name}</td>
            <td>${o.quantity}</td>
            <td>₹${(o.ltp||0).toFixed(2)}</td>
            <td>₹${(o.quantity * (o.ltp||0)).toFixed(0)}</td>
            <td class="${o.status === 'OK' ? 'status-ok' : 'status-fail'}">${o.status}</td>
          </tr>`).join('')}
        </table>
        <div class="history-summary">${h.results.succeeded}/${h.results.total} orders succeeded</div>
      </div>
    `).join('');
  } catch(e) { panel.innerHTML = '<div class="empty">Failed to load history: ' + e.message + '</div>'; }
}
</script>
</body>
</html>"""

if __name__ == "__main__":
    app.run(debug=True, port=5001)
