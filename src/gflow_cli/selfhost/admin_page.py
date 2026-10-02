"""Static private settings page. Never interpolate provider credentials."""

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="csrf-token" content="__CSRF__"><title>Flow · CapSolver settings</title>
<style nonce="__NONCE__">
:root{font-family:system-ui,-apple-system,sans-serif;color:#20302b;background:#f4f6f3}
*{box-sizing:border-box}body{margin:0;padding:48px 20px}main{max-width:560px;margin:auto}
.brand{font-weight:650;color:#456556;letter-spacing:.06em;margin-bottom:28px}
section{background:white;
border:1px solid #dce4dd;
border-radius:18px;
padding:32px;
box-shadow:0 12px 35px #223b2610}
h1{font-size:28px;margin:0 0 12px;letter-spacing:-.7px}p{line-height:1.55;color:#59665e}
.status{font-size:14px;background:#eff4ee;border-radius:8px;padding:12px;margin:24px 0}
label{display:block;font-weight:600;font-size:14px;margin-bottom:9px}
input{font:inherit;width:100%;padding:13px;border:1px solid #a7b7ab;border-radius:8px}
input:focus{outline:3px solid #91b29b55;border-color:#426c4e}
.buttons{display:flex;gap:9px;flex-wrap:wrap;margin-top:16px}
button{font:inherit;
font-size:14px;
font-weight:600;
border:1px solid #bdcbbf;
border-radius:8px;
padding:11px 15px;
cursor:pointer;
background:white;
color:#2c4935}
button.primary{background:#30583e;border-color:#30583e;color:white}button:disabled{opacity:.5;cursor:wait}
button:focus-visible{outline:3px solid #91b29b}
.note{font-size:13px;border-top:1px solid #e4e9e3;padding-top:18px;margin-top:26px}
#message{font-size:14px;min-height:24px;line-height:1.5;margin-top:20px}
@media(max-width:440px){body{padding:24px 14px}section{padding:24px}}
</style></head><body><main><div class="brand">FLOW / PRIVATE SETTINGS</div><section>
<h1>Connect CapSolver</h1><p>Save your API key securely on your Flow server.</p>
<div class="status" id="status">Checking saved configuration…</div>
<form id="form"><label for="key">CapSolver API key</label>
<input id="key" name="key" type="password"
 autocomplete="off" spellcheck="false"
 maxlength="500"
 placeholder="Paste your CapSolver key" required>
<div class="buttons"><button class="primary" type="submit">Save key</button>
<button id="check" type="button">Check connection</button>
<button id="remove" type="button">Remove key</button>
</div>
</form>
<div id="message" role="status" aria-live="polite"></div>
<p class="note">The connection check reads your balance and does not
create a CAPTCHA task. Saving a key does not yet enable
CAPTCHA solving for image or video generation.</p>
</section></main><script nonce="__NONCE__">
const csrf = document.querySelector('meta[name="csrf-token"]').content;
const status = document.querySelector('#status');
const message = document.querySelector('#message');
const key = document.querySelector('#key');
async function refresh() {
  const r = await fetch('/api/status', {cache: 'no-store'});
  if (!r.ok) throw Error('Could not read settings.');
  const d = await r.json();
  status.textContent = d.configured ? 'API key saved · value hidden' : 'No API key saved';
}
async function act(path, body) {
  document.querySelectorAll('button').forEach(b => b.disabled = true);
  message.textContent = 'Working…';
  try {
    const r = await fetch(path, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
      body: JSON.stringify(body)
    });
    const d = await r.json();
    if (!r.ok) throw Error(typeof d.detail === 'string' ? d.detail : 'Request failed.');
    key.value = '';
    await refresh();
    if (path === '/api/check') {
      const usd = new Intl.NumberFormat('en-US', {style: 'currency', currency: 'USD'});
      message.textContent = 'Connection verified · Balance ' + usd.format(d.balance);
    } else {
      message.textContent = path === '/api/remove' ? 'Key removed.' : 'Key saved securely.';
    }
  } catch (e) {
    message.textContent = e.message;
  } finally {
    document.querySelectorAll('button').forEach(b => b.disabled = false);
  }
}
document.querySelector('#form').addEventListener('submit', e => {
  e.preventDefault();
  act('/api/save', {key: key.value.trim()});
});
document.querySelector('#check').addEventListener('click', () => act('/api/check', {}));
document.querySelector('#remove').addEventListener('click', () => act('/api/remove', {}));
refresh().catch(e => message.textContent = e.message);
</script></body></html>"""
