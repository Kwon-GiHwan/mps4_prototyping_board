"""Native MPS4 deployment with verified recovery after each stock MLEK run."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
import threading
import time

from host.campaigns.errors import CellFailure


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or '..' in path.parts or str(path) == '.':
        raise CellFailure('UNSUPPORTED_CONFIGURATION', 'board_config',
                          'artifact and card destinations must be relative paths')
    return str(path)


def _within(root: Path, relative: str) -> Path:
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()):
        raise CellFailure('UNSUPPORTED_CONFIGURATION', 'board_config',
                          'destination escapes its root')
    return path


def _command(*argv: str, allowed=(0,)) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CellFailure('ENVIRONMENT_UNAVAILABLE', 'board_environment', str(exc)) from exc
    if result.returncode not in allowed:
        raise CellFailure('ENVIRONMENT_UNAVAILABLE', 'board_environment',
                          f'{argv[0]} failed: {result.stderr.strip()}')
    return result


class _Capture:
    def __init__(self, port: str):
        try:
            import serial
            self.port = serial.Serial(port, 115200, timeout=0.2, exclusive=True)
        except (ImportError, OSError) as exc:
            raise CellFailure('ENVIRONMENT_UNAVAILABLE', 'board_capture', str(exc)) from exc
        try:
            self.port.reset_input_buffer()
        except Exception as exc:
            self.port.close()
            raise CellFailure('ENVIRONMENT_UNAVAILABLE', 'board_capture', str(exc)) from exc
        self.chunks = []
        self.error = None
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()
        if not self.ready.wait(5) or not self.thread.is_alive():
            self.close()
            raise CellFailure('ENVIRONMENT_UNAVAILABLE', 'board_capture', 'reader did not start')

    def _read(self):
        try:
            # Complete a read before announcing readiness: boot cannot overtake
            # reader setup even when the application finishes during reset.
            while not self.stop.is_set():
                chunk = self.port.read(65536)
                self.ready.set()
                if chunk:
                    self.chunks.append(chunk)
        except Exception as exc:
            self.error = exc
            self.ready.set()

    @property
    def running(self):
        return self.ready.is_set() and self.thread.is_alive() and self.error is None

    def text(self):
        return self.data().decode('utf-8', errors='replace')

    def data(self):
        return b''.join(self.chunks)

    def wait(self, timeout: float):
        from host.campaigns.measurement import EXECUTION_ERRORS, MEMORY_ERRORS

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.running:
                raise CellFailure('ENVIRONMENT_UNAVAILABLE', 'board_capture',
                                  f'UART reader stopped: {self.error}')
            text = self.text()
            if 'Inference completed.' in text:
                time.sleep(0.5)
                return
            if any(marker in text.lower() for marker in MEMORY_ERRORS + EXECUTION_ERRORS):
                return
            time.sleep(0.1)
        raise CellFailure('TIMEOUT', 'board_inference', 'inference deadline exceeded')

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)
        self.port.close()


class _BoardIO:
    def __init__(self, settings: dict):
        self.settings = settings
        self.mounted = False

    def mcc(self, command: str, wait=1.0):
        try:
            import serial
            with serial.Serial(self.settings['mcc_port'], 115200, timeout=0.5,
                               write_timeout=2, exclusive=True) as port:
                port.write(command.encode('ascii') + b'\r')
                port.flush()
                time.sleep(wait)
                return port.read(262144).decode('ascii', errors='replace')
        except (ImportError, OSError) as exc:
            raise CellFailure('ENVIRONMENT_UNAVAILABLE', 'board_console', str(exc)) from exc

    def present(self):
        return Path(self.settings['block_device']).exists()

    def _helper(self):
        """'sudo' (default, unchanged) or 'udisks' for a root-free mount path.

        The udisks path exists because this host grants the operator serial and
        USB access but no passwordless sudo; udisks2 performs the mount under a
        polkit rule instead. Existing configs keep the sudo path byte for byte.
        """
        helper = self.settings.get('mount_helper', 'sudo')
        if helper not in ('sudo', 'udisks'):
            raise CellFailure('ENVIRONMENT_UNAVAILABLE', 'board_identity',
                              'mount_helper must be sudo or udisks')
        return helper

    def _holders(self):
        paths = [self.settings[key] for key in ('mcc_port', 'uart_port')]
        paths += [self.settings[key] for key in ('block_device', 'partition')
                  if Path(self.settings[key]).exists()]
        if self._helper() == 'udisks':
            # Without root, lsof cannot see holders owned by other users. The
            # check is therefore weaker here and is recorded as such: it proves
            # this operator holds nothing, not that nobody does.
            result = _command('lsof', '-t', '--', *paths, allowed=(0, 1))
        else:
            result = _command('sudo', '-n', 'lsof', '-t', '--', *paths, allowed=(0, 1))
        # sudo/lsof operational errors can also exit 1, so stderr is not ignored.
        if result.stderr.strip() or result.stdout.strip():
            raise CellFailure('ENVIRONMENT_UNAVAILABLE', 'board_preflight',
                              'cannot establish exclusive UART/block access')

    def preflight(self):
        if self.present():
            raise CellFailure('ENVIRONMENT_UNAVAILABLE', 'board_preflight',
                              'board block device must be absent before USB_ON')
        ports = [Path(self.settings[key]) for key in ('mcc_port', 'uart_port')]
        try:
            valid = all(stat.S_ISCHR(port.stat().st_mode) for port in ports)
            distinct = ports[0].resolve() != ports[1].resolve()
        except OSError as exc:
            raise CellFailure('ENVIRONMENT_UNAVAILABLE', 'board_preflight', str(exc)) from exc
        if not valid or not distinct:
            raise CellFailure('ENVIRONMENT_UNAVAILABLE', 'board_preflight',
                              'MCC and application UART must be distinct character devices')
        self._holders()

    def usb(self, enabled: bool):
        if not enabled and self.mounted:
            raise CellFailure('BOARD_RECOVERY_ERROR', 'board_unmount',
                              'refusing USB_OFF while mounted', target_unusable=True)
        self.mcc('USB_ON' if enabled else 'USB_OFF', wait=3)
        deadline = time.monotonic() + 15
        while self.present() != enabled and time.monotonic() < deadline:
            time.sleep(0.2)
        if self.present() != enabled:
            raise CellFailure('ENVIRONMENT_UNAVAILABLE', 'board_usb', 'USB state did not settle')

    @contextmanager
    def mount(self, readonly: bool):
        settings = self.settings
        identity = _command('lsblk', '-J', '-o', 'PATH,FSTYPE,LABEL,PKNAME',
                            settings['partition'])
        nodes = json.loads(identity.stdout)['blockdevices']
        if len(nodes) != 1:
            raise CellFailure('ENVIRONMENT_UNAVAILABLE', 'board_identity', 'ambiguous partition')
        node = nodes[0]
        parent = str(node.get('pkname', ''))
        if not parent.startswith('/'):
            parent = '/dev/' + parent
        if (node.get('fstype') != 'vfat' or node.get('label') != settings['filesystem_label']
                or Path(parent).resolve() != Path(settings['block_device']).resolve()):
            raise CellFailure('ENVIRONMENT_UNAVAILABLE', 'board_identity', 'card identity mismatch')
        transport = _command('lsblk', '-dn', '-o', 'TRAN', settings['block_device'])
        if transport.stdout.strip() != 'usb':
            raise CellFailure('ENVIRONMENT_UNAVAILABLE', 'board_identity', 'card is not USB')
        mounted = _command('findmnt', '-rn', '-S', settings['partition'], allowed=(0, 1))
        if mounted.stdout.strip():
            raise CellFailure('ENVIRONMENT_UNAVAILABLE', 'board_mount', 'partition already mounted')
        if self._helper() == 'udisks':
            with self._mount_udisks(readonly) as root:
                yield root
            return
        root = Path(tempfile.mkdtemp(prefix='mlek-card-'))
        try:
            options = f'uid={os.getuid()},gid={os.getgid()},umask=022'
            if readonly:
                options += ',ro'
            _command('sudo', '-n', 'mount', '-t', 'vfat', '-o', options,
                     settings['partition'], str(root))
            self.mounted = True
            try:
                yield root
            finally:
                _command('sync')
                _command('sudo', '-n', 'umount', str(root))
                state = _command('findmnt', '-rn', '-S', settings['partition'], allowed=(0, 1))
                if state.stdout.strip():
                    raise CellFailure('BOARD_RECOVERY_ERROR', 'board_unmount',
                                      'card remains mounted', target_unusable=True)
                self.mounted = False
        finally:
            # Never recursively delete a mountpoint: an unmount failure must
            # preserve both the card and its mount for operator recovery.
            if not self.mounted:
                root.rmdir()

    @contextmanager
    def _mount_udisks(self, readonly: bool):
        """udisks2 chooses the mount point, so it is read back rather than set.

        The identity gates in mount() have already run; this only performs the
        privileged step. Unmount failure leaves the card mounted on purpose, so
        that usb() refuses USB_OFF and the operator can recover.
        """
        partition = self.settings['partition']
        argv = ['udisksctl', 'mount', '-b', partition, '--no-user-interaction']
        if readonly:
            argv += ['--options', 'ro']
        _command(*argv)
        located = _command('findmnt', '-rn', '-o', 'TARGET', '-S', partition)
        root = Path(located.stdout.strip().splitlines()[0]) if located.stdout.strip() else None
        if root is None or not root.is_dir():
            raise CellFailure('ENVIRONMENT_UNAVAILABLE', 'board_mount',
                              'udisks reported no mount point')
        self.mounted = True
        try:
            yield root
        finally:
            _command('sync')
            _command('udisksctl', 'unmount', '-b', partition, '--no-user-interaction')
            state = _command('findmnt', '-rn', '-S', partition, allowed=(0, 1))
            if state.stdout.strip():
                raise CellFailure('BOARD_RECOVERY_ERROR', 'board_unmount',
                                  'card remains mounted', target_unusable=True)
            self.mounted = False

    def capture(self):
        return _Capture(self.settings['uart_port'])

    def reboot(self, capture=None):
        if capture is not None and not capture.running:
            raise CellFailure('ENVIRONMENT_UNAVAILABLE', 'board_capture', 'capture not ready')
        text = self.mcc('REBOOT', wait=3)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if 'Clearing SCC CPUWAIT' in text and 'Cmd>' in text:
                break
            text += self.mcc('', wait=2)
        if ('DDR memory test at 0x70000000: PASSED' not in text
                or 'Clearing SCC CPUWAIT' not in text or 'Cmd>' not in text):
            raise CellFailure('ENVIRONMENT_UNAVAILABLE', 'board_boot', 'boot health gate failed')

    def postflight(self):
        self.reboot()
        self.usb(False)
        self._holders()
        return {'boot_health': True, 'device_absent': True, 'exclusive_access': True}


def run_board(cell: dict, config: dict, artifacts: dict, run_dir: Path) -> dict:
    """Run one fresh-boot inference; leave the original card contents restored."""
    settings = cell['target'].get('board', {})
    if settings.get('adapter') != 'mps4':
        raise CellFailure('UNSUPPORTED_CONFIGURATION', 'board_config', 'unsupported board adapter')
    target = cell['target']
    if (target.get('kind'), target.get('platform'), target.get('subsystem'),
            target.get('npu'), cell.get('options', {}).get('mac')) != (
            'board', 'mps4', 'sse-320', 'ethos-u85', 1024):
        raise CellFailure('UNSUPPORTED_CONFIGURATION', 'board_config',
                          'native adapter supports MPS4 SSE-320 U85 1024 only')
    required = ('mcc_port', 'uart_port', 'block_device', 'partition', 'filesystem_label')
    if any(not isinstance(settings.get(key), str) or not settings[key] for key in required):
        raise CellFailure('UNSUPPORTED_CONFIGURATION', 'board_config', 'missing board settings')
    destinations = settings.get('destinations')
    if not isinstance(destinations, dict) or not destinations:
        raise CellFailure('UNSUPPORTED_CONFIGURATION', 'board_config', 'explicit destinations required')
    required_destinations = {
        'sectors/inference_runner/' + name: 'SOFTWARE/' + name
        for name in ('boot.bin', 'bram.bin', 'ddr.bin')
    }
    required_destinations['sectors/images.txt'] = 'MB/HBI0376B/FI101/images.txt'
    if destinations != required_destinations:
        raise CellFailure('UNSUPPORTED_CONFIGURATION', 'board_config',
                          'complete inference_runner image set and FI101 destinations required')
    sources = {}
    expected = artifacts.get('deployable_hashes')
    if not isinstance(expected, dict) or not expected:
        raise CellFailure('IDENTITY_MISMATCH', 'board_identity', 'build deployable hashes missing')
    hashes = {}
    for source, destination in destinations.items():
        if not isinstance(source, str) or not isinstance(destination, str):
            raise CellFailure('UNSUPPORTED_CONFIGURATION', 'board_config', 'invalid destination mapping')
        relative_source, relative_destination = _relative(source), _relative(destination)
        sources[relative_destination] = _within(Path(artifacts['bin_dir']), relative_source)
        digest = expected.get(relative_source)
        if (not isinstance(digest, str) or len(digest) != 64
                or any(character not in '0123456789abcdef' for character in digest)):
            raise CellFailure('IDENTITY_MISMATCH', 'board_identity', 'declared artifact hash missing or invalid')
        hashes[relative_destination] = digest
    if len(sources) != len(destinations) or any(not path.is_file() for path in sources.values()):
        raise CellFailure('UNSUPPORTED_CONFIGURATION', 'board_config', 'missing artifact or duplicate destination')
    if any(_hash(source) != hashes[name] for name, source in sources.items()):
        raise CellFailure('IDENTITY_MISMATCH', 'board_identity', 'source differs from build artifact')
    image_text = sources['MB/HBI0376B/FI101/images.txt'].read_text()
    image_text = '\n'.join(line.split(';', 1)[0].strip() for line in image_text.splitlines())
    files = re.findall(r'^IMAGE(\d+)FILE:\s*(\S+)\s*$', image_text, re.M)
    updates = re.findall(r'^IMAGE(\d+)UPDATE:\s*(\S+)\s*$', image_text, re.M)
    referenced = [value.replace('\\', '/').lstrip('/') for _, value in files]
    if (re.findall(r'^TOTALIMAGES:\s*(\d+)\s*$', image_text, re.M) != ['3']
            or sorted(index for index, _ in files) != ['0', '1', '2']
            or sorted(updates) != [('0', 'RAM'), ('1', 'RAM'), ('2', 'RAM')]
            or len(referenced) != 3 or set(referenced) != set(required_destinations.values()) - {
                'MB/HBI0376B/FI101/images.txt'}):
        raise CellFailure('UNSUPPORTED_CONFIGURATION', 'board_config',
                          'images.txt must load only the three declared inference_runner RAM images')
    timeout = config['measurement']['timeout_seconds']
    if (not isinstance(timeout, (int, float)) or isinstance(timeout, bool)
            or not 0 < timeout < float('inf')):
        raise CellFailure('UNSUPPORTED_CONFIGURATION', 'board_config', 'invalid inference timeout')
    run_dir.mkdir(parents=True, exist_ok=True)
    backup = run_dir / 'board-backup'
    backup.mkdir(exist_ok=False)
    io = _BoardIO(settings)
    io.preflight()
    originals = {}
    modified = False
    capture = None
    result = {}
    error = None
    try:
        io.usb(True)
        with io.mount(True) as card:
            for index, relative in enumerate(sources):
                target = _within(card, relative)
                if not target.parent.is_dir():
                    raise CellFailure('UNSUPPORTED_CONFIGURATION', 'board_deploy',
                                      'destination parent directory must already exist')
                saved = backup / str(index)
                if target.exists():
                    if not target.is_file():
                        raise CellFailure('UNSUPPORTED_CONFIGURATION', 'board_deploy', 'destination is not a file')
                    shutil.copyfile(target, saved)
                    if _hash(target) != _hash(saved):
                        raise CellFailure('ENVIRONMENT_UNAVAILABLE', 'board_backup', 'backup hash mismatch')
                    originals[relative] = {'backup': str(saved), 'sha256': _hash(saved)}
                else:
                    originals[relative] = {'backup': None, 'sha256': None}
        (backup / 'manifest.json').write_text(json.dumps(originals, indent=2) + '\n')
        with io.mount(False) as card:
            modified = True
            for relative, source in sources.items():
                if _hash(source) != hashes[relative]:
                    raise CellFailure('IDENTITY_MISMATCH', 'board_deploy', 'artifact changed before deployment')
                shutil.copyfile(source, _within(card, relative))
        with io.mount(True) as card:
            if any(_hash(_within(card, name)) != digest for name, digest in hashes.items()):
                raise CellFailure('IDENTITY_MISMATCH', 'board_deploy', 'deployment readback mismatch')
        io.usb(False)
        capture = io.capture()
        if not capture.running:
            raise CellFailure('ENVIRONMENT_UNAVAILABLE', 'board_capture', 'capture not ready')
        io.reboot(capture)
        capture.wait(timeout)
    except Exception as exc:
        error = exc
    finally:
        if capture is not None:
            try:
                capture.close()
            except Exception as exc:
                error = error or exc
            try:
                raw_path = run_dir / 'uart.bin'
                raw_path.write_bytes(capture.data())
                result['uart_binary_path'] = str(raw_path)
                result['uart_binary_sha256'] = _hash(raw_path)
                result['uart'] = capture.text()
                uart_path = run_dir / 'uart.txt'
                uart_path.write_text(result['uart'])
                result['uart_path'] = str(uart_path)
                result['uart_sha256'] = _hash(uart_path)
            except Exception as exc:
                error = error or exc
        try:
            if modified:
                if not io.present():
                    io.usb(True)
                with io.mount(False) as card:
                    for relative, original in originals.items():
                        target = _within(card, relative)
                        if original['backup'] is None:
                            target.unlink(missing_ok=True)
                        else:
                            saved = Path(original['backup'])
                            if _hash(saved) != original['sha256']:
                                raise RuntimeError('backup changed before restore')
                            shutil.copyfile(saved, target)
                with io.mount(True) as card:
                    for relative, original in originals.items():
                        target = _within(card, relative)
                        digest = _hash(target) if target.exists() else None
                        if digest != original['sha256']:
                            raise RuntimeError('restore readback mismatch')
            result['restore'] = {'verified': True, 'needed': modified}
            io.usb(False)
            result['postflight'] = io.postflight()
        except Exception as exc:
            error = CellFailure('BOARD_RECOVERY_ERROR', 'board_recovery', str(exc), target_unusable=True)
            result['recovery_error'] = str(exc)
        (run_dir / 'board-state.json').write_text(json.dumps(result, indent=2) + '\n')
    if error is not None:
        if isinstance(error, CellFailure):
            raise error
        raise CellFailure('ENVIRONMENT_UNAVAILABLE', 'board_execution', str(error)) from error
    return result
