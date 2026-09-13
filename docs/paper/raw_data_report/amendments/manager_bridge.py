"""Bridge to the ChatGPT tab that the user designated as the temporary manager (2026-09-14).

Mechanism: AppleScript -> Google Chrome "execute javascript" on the tab whose URL contains the
manager conversation id (any window, need not be frontmost; the user enabled JavaScript from
Apple Events). The model is ChatGPT Pro: answers can take 10 minutes or more.

  python3 manager_bridge.py ask "<question>"        # sends, waits for the full answer, prints it
  python3 manager_bridge.py last                    # prints the last assistant message
  python3 manager_bridge.py status                  # tab url/title, generating?, message count

Wait rule: after sending, poll every 5 s until (a) the assistant message count has grown,
(b) no stop button is visible, and (c) the last assistant text has been unchanged for 3
consecutive polls. Timeout 2400 s -> raises. For long waits run detached:
  nohup python3 manager_bridge.py ask "<q>" > /tmp/manager_answer.txt 2>&1 & Every exchange is appended to
docs/paper/raw_data_report/amendments/manager_log.md (question, answer, timestamps).
"""
import json, subprocess, sys, time
from pathlib import Path

LOG = Path(__file__).with_name("manager_log.md")
CONV = "6a966f7b-e58c-83ee-8980-92b6f1d48417"  # the designated manager conversation
TAB = ('tell application "Google Chrome" to repeat with w in windows\nrepeat with t in tabs of w\n'
       'if URL of t contains "%s" then return (execute t javascript ' % CONV)
TAB_END = ')\nend repeat\nend repeat\nreturn "NO_MANAGER_TAB"\n'

STOP_SEL = 'button[data-testid="stop-button"]'
SEND_SEL = 'button[data-testid="send-button"]'
MSG_SEL = '[data-message-author-role="assistant"]'


def js(code):
    r = subprocess.run(["osascript", "-e", TAB + json.dumps(code) + TAB_END], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    out = r.stdout.rstrip("\n")
    if out == "NO_MANAGER_TAB":
        raise RuntimeError("manager conversation tab not open in Chrome")
    return out


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


def wait_answer(before, t0, timeout=2400, poll=5, before_text=None):
    """Wait until an answer newer than `before` has fully rendered; returns its text.
    ChatGPT virtualises long conversations, so the assistant-node count may not grow: a changed
    last-assistant text counts as a new answer too."""
    stable, prev = 0, None
    while time.time() - t0 < timeout:
        time.sleep(poll)
        s = status()
        new = s["n"] > before or (before_text is not None and last_text() != before_text)
        if new and not s["generating"]:
            cur = last_text()
            stable = stable + 1 if cur == prev and cur else 0
            prev = cur
            if stable >= 3:
                return cur
    raise TimeoutError("manager did not finish within %ds" % timeout)


def log_exchange(question, answer, seconds):
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write("\n## %s\n\n**Q (Claude):**\n\n%s\n\n**A (manager, %.0fs):**\n\n%s\n" % (
            time.strftime("%Y-%m-%d %H:%M:%S"), question, seconds, answer))


def ask(text, timeout=2400, poll=5):
    before = status()["n"]; before_text = last_text()
    t0 = time.time(); send(text)
    cur = wait_answer(before, t0, timeout, poll, before_text)
    log_exchange(text, cur, time.time() - t0)
    return cur


def wait_pending(question_label, timeout=2400, poll=5):
    """A question was already sent (e.g. before an interruption): wait for its answer and log it."""
    t0 = time.time(); before = status()["n"] - 1
    cur = wait_answer(before, t0, timeout, poll)
    log_exchange(question_label, cur, time.time() - t0)
    return cur


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "ask":
        print(ask(sys.argv[2]))
    elif cmd == "last":
        print(last_text())
    elif cmd == "wait":
        print(wait_pending(sys.argv[2] if len(sys.argv) > 2 else "(question sent earlier)"))
    else:
        print(json.dumps(status(), ensure_ascii=False))
