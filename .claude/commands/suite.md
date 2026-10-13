---
description: Run every test module
---

From the repo root:

```sh
sh test.sh
```

It clears `__pycache__`, runs each module in its own process (unittest per module; `host/tests/test_proto_unit.py`
is a script), prints one line per module with its exit code, and exits non-zero if any module fails. It does not
build firmware or touch the board.
