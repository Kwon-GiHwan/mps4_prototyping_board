"""Bridge to the ChatGPT tab that the user designated as the temporary manager (2026-09-14).

Mechanism: AppleScript -> Google Chrome "execute javascript" on the front window's active tab
(the user enabled JavaScript from Apple Events). The tab must stay the active tab of the
front Chrome window while a question is pending.

  python3 manager_bridge.py ask "<question>"        # sends, waits for the full answer, prints it
  python3 manager_bridge.py last                    # prints the last assistant message
  python3 manager_bridge.py status                  # tab url/title, generating?, message count

Wait rule: after sending, poll every 2 s until (a) the assistant message count has grown,
(b) no stop button is visible, and (c) the last assistant text has been unchanged for 3
consecutive polls. Timeout 600 s -> raises. Every exchange is appended to
docs/paper/raw_data_report/amendments/manager_log.md (question, answer, timestamps).
"""
import json, subprocess, sys, time
from pathlib import Path

LOG = Path(__file__).with_name("manager_log.md")
TAB = 'tell application "Google Chrome" to tell active tab of front window to execute javascript '
STOP_SEL = 'button[data-testid="stop-button"]'
SEND_SEL = 'button[data-testid="send-button"]'
MSG_SEL = '[data-message-author-role="assistant"]'


def js(code):
    r = subprocess.run(["osascript", "-e", TAB + json.dumps(code)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return r.stdout.rstrip("\n")


def status():
    return json.loads(js("JSON.stringify({url:location.href,title:document.title,"
                         "generating:!!document.querySelector(%s),n:document.querySelectorAll(%s).length})"
                         % (json.dumps(STOP_SEL), json.dumps(MSG_SEL))))


def last_text():
    return js("(function(){var m=document.querySelectorAll(%s);return m.length?m[m.length-1].innerText:'';})()" % json.dumps(MSG_SEL))


def send(text):
    code = ("(function(){var ta=document.querySelector('#prompt-textarea');if(!ta)return 'NO_TEXTAREA';"
            "ta.focus();document.execCommand('selectAll',false,null);document.execCommand('insertText',false,%s);"
            "return 'TYPED:'+ta.innerText.length;})()" % json.dumps(text))
    r = js(code)
    if not r.startswith("TYPED"):
        raise RuntimeError(r)
    time.sleep(0.8)
    r = js("(function(){var b=document.querySelector(%s);if(!b||b.disabled)return 'NO_SEND';b.click();return 'SENT';})()" % json.dumps(SEND_SEL))
    if r != "SENT":
        raise RuntimeError(r)


def ask(text, timeout=600):
    before = status()["n"]
    t0 = time.time(); send(text)
    stable, prev = 0, None
    while time.time() - t0 < timeout:
        time.sleep(2)
        s = status()
        if s["n"] > before and not s["generating"]:
            cur = last_text()
            stable = stable + 1 if cur == prev and cur else 0
            prev = cur
            if stable >= 3:
                LOG.parent.mkdir(exist_ok=True)
                with open(LOG, "a") as f:
                    f.write("\n## %s\n\n**Q (Claude):**\n\n%s\n\n**A (manager, %.0fs):**\n\n%s\n" % (
                        time.strftime("%Y-%m-%d %H:%M:%S"), text, time.time() - t0, cur))
                return cur
    raise TimeoutError("manager did not finish within %ds" % timeout)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "ask":
        print(ask(sys.argv[2]))
    elif cmd == "last":
        print(last_text())
    else:
        print(json.dumps(status(), ensure_ascii=False))
