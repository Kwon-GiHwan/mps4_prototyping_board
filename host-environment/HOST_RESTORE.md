# Host environment — what the board-side scripts actually run on

Recorded 2026-08-08. **No script was modified to produce this.** The host tools
are frozen working-snapshot artifacts; this directory documents the environment
they run in so another machine can be set up without editing them.

## The interpreter split (easy to get wrong)

```
/usr/bin/python3   Python 3.12.3   ← the scripts run HERE (system, apt-managed)
mps4/venv/         Python 3.12.3   ← pyocd only. include-system-site-packages = false
```

`venv/` does **not** contain pyserial. Activating it and running a board script
fails with `ModuleNotFoundError`. That split is not obvious from any script and
was not written down anywhere until now.

## Dependency

`pyserial 3.5` from the **apt package `python3-serial`**, at
`/usr/lib/python3/dist-packages/serial/`. Not a pip install — `pip freeze` on
this interpreter lists nothing relevant because the package is distro-managed.
That is why no `requirements.txt` exists and why writing one would be
misleading: it would imply a pip provenance the install does not have.

On a new host:

```sh
apt install python3-serial
python3 -c "import serial; print(serial.__version__)"   # must print 3.5
```

## Serial bindings

See `serial-bindings.yaml`. The FTDI serial number `00FT46259002B` is hardcoded
in 29 places. Moving to another MPS4 means replacing it in all of them. This is
recorded rather than refactored: the scripts are frozen, and changing them would
break the working-snapshot hashes for no benefit to the current experiment.

## Not covered

- No lockfile. Versions of the other 55 packages in `venv/` (pyocd, pyusb,
  pylink_square, capstone, cmsis_pack_manager …) are unrecorded. They are not
  used by the board path, but pyocd work would need them.
- Host OS version and udev rules for the FTDI device are not captured.
