"""Board deployment failure recovery without devices or privileged commands."""

from contextlib import contextmanager
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from host.campaigns import board
from host.campaigns.errors import CellFailure


class FakeCapture:
    running = True

    def __init__(self, events, fail=False, close_fail=False):
        self.events = events
        self.fail = fail
        self.close_fail = close_fail

    def wait(self, timeout):
        self.events.append('wait')
        if self.fail:
            raise CellFailure('TIMEOUT', 'board_inference', 'test timeout')

    def close(self):
        self.events.append('close')
        self.running = False
        if self.close_fail:
            raise OSError('capture close failed')

    def text(self):
        return 'Inference completed.\n'

    def data(self):
        return self.text().encode()


class FakeBoard:
    def __init__(self, card, fail=False, restore_fail=False, close_fail=False):
        self.card = card
        self.events = []
        self.enabled = False
        self.fail = fail
        self.restore_fail = restore_fail
        self.close_fail = close_fail
        self.mounts = 0

    def preflight(self):
        self.events.append('preflight')

    def present(self):
        return self.enabled

    def usb(self, enabled):
        self.events.append('usb_on' if enabled else 'usb_off')
        self.enabled = enabled

    @contextmanager
    def mount(self, readonly):
        self.mounts += 1
        if self.restore_fail and self.mounts == 4:
            raise OSError('restore media unavailable')
        self.events.append('mount_ro' if readonly else 'mount_rw')
        yield self.card
        self.events.append('unmount')

    def capture(self):
        self.events.append('capture_ready')
        return FakeCapture(self.events, self.fail, self.close_fail)

    def reboot(self, capture):
        assert capture.running
        self.events.append('reboot')

    def postflight(self):
        self.events.extend(['postflight_reboot', 'postflight_usb_off'])
        self.enabled = False
        return {'device_absent': True}


class BoardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bin = self.root / 'bin/sectors/inference_runner'
        self.bin.mkdir(parents=True)
        (self.bin / 'boot.bin').write_bytes(b'new boot')
        (self.bin / 'bram.bin').write_bytes(b'new bram')
        (self.bin / 'ddr.bin').write_bytes(b'new ddr')
        images = 'TOTALIMAGES: 3\n' + ''.join(
            f'IMAGE{i}FILE: \\SOFTWARE\\{name}\nIMAGE{i}UPDATE: RAM\n'
            for i, name in enumerate(('boot.bin', 'bram.bin', 'ddr.bin')))
        (self.bin.parent / 'images.txt').write_text(images)
        self.card = self.root / 'card'
        self.card.mkdir()
        (self.card / 'SOFTWARE').mkdir()
        (self.card / 'MB/HBI0376B/FI101').mkdir(parents=True)
        (self.card / 'SOFTWARE/boot.bin').write_bytes(b'original boot')
        self.settings = {
            'adapter': 'mps4', 'mcc_port': '/dev/mcc', 'uart_port': '/dev/uart',
            'block_device': '/dev/sdb', 'partition': '/dev/sdb1',
            'filesystem_label': 'M1SDP',
            'destinations': {
                **{'sectors/inference_runner/' + name: 'SOFTWARE/' + name
                   for name in ('boot.bin', 'bram.bin', 'ddr.bin')},
                'sectors/images.txt': 'MB/HBI0376B/FI101/images.txt'},
        }
        self.cell = {'target': {'board': self.settings, 'kind': 'board', 'platform': 'mps4',
                                'subsystem': 'sse-320', 'npu': 'ethos-u85'},
                     'options': {'mac': 1024}}
        self.config = {'measurement': {'timeout_seconds': 30}}
        self.artifacts = {'bin_dir': str(self.root / 'bin'), 'deployable_hashes': {
            name: board._hash(self.root / 'bin' / name)
            for name in self.settings['destinations']}}

    def run_board(self, io):
        with patch.object(board, '_BoardIO', return_value=io):
            return board.run_board(self.cell, self.config, self.artifacts, self.root / 'run')

    def test_build_hash_is_required_before_any_board_io(self):
        for hashes in (None, {}, {'boot.bin': 'a' * 64, 'bram.bin': 'b' * 64}):
            with self.subTest(hashes=hashes):
                self.artifacts['deployable_hashes'] = hashes
                with patch.object(board, '_BoardIO') as io, self.assertRaises(CellFailure) as caught:
                    board.run_board(self.cell, self.config, self.artifacts, self.root / 'run')
                io.assert_not_called()
                self.assertEqual(caught.exception.status, 'IDENTITY_MISMATCH')

    def test_only_implemented_hardware_target_is_accepted(self):
        for key, wrong in (('platform', 'mps3'), ('subsystem', 'sse-300'), ('npu', 'ethos-u55')):
            original = self.cell['target'][key]
            self.cell['target'][key] = wrong
            with self.assertRaises(CellFailure) as caught:
                self.run_board(FakeBoard(self.card))
            self.assertEqual(caught.exception.status, 'UNSUPPORTED_CONFIGURATION')
            self.cell['target'][key] = original
        self.cell['options']['mac'] = 256
        with self.assertRaises(CellFailure):
            self.run_board(FakeBoard(self.card))

    def test_complete_inference_image_mapping_required(self):
        original = dict(self.settings['destinations'])
        for bad in (
            {key: value for key, value in original.items() if not key.endswith('ddr.bin')},
            {key.replace('inference_runner', 'hal-test'): value for key, value in original.items()},
            dict(original, **{'sectors/inference_runner/ddr.bin': 'SOFTWARE/boot.bin'}),
        ):
            self.settings['destinations'] = bad
            with self.assertRaises(CellFailure) as caught:
                self.run_board(FakeBoard(self.card))
            self.assertEqual(caught.exception.status, 'UNSUPPORTED_CONFIGURATION')

    def test_images_manifest_must_boot_declared_ram_images(self):
        path = self.bin.parent / 'images.txt'
        original = path.read_text()
        for text in (original.replace('bram.bin', 'wrong.bin'),
                     original.replace('RAM', 'FORCEQSPI'),
                     original.replace('IMAGE1FILE', 'IMAGE0FILE')):
            path.write_text(text)
            self.artifacts['deployable_hashes']['sectors/images.txt'] = board._hash(path)
            with self.assertRaises(CellFailure) as caught:
                self.run_board(FakeBoard(self.card))
            self.assertEqual(caught.exception.status, 'UNSUPPORTED_CONFIGURATION')

    def test_source_change_after_backup_is_rejected_and_restored(self):
        io = FakeBoard(self.card)
        mount = io.mount

        @contextmanager
        def mutate_before_write(readonly):
            if not readonly and io.mounts == 1:
                (self.bin / 'boot.bin').write_bytes(b'changed after build')
            with mount(readonly) as card:
                yield card

        io.mount = mutate_before_write
        with self.assertRaises(CellFailure) as caught:
            self.run_board(io)
        self.assertEqual(caught.exception.status, 'IDENTITY_MISMATCH')
        self.assert_restored()

    def assert_restored(self):
        self.assertEqual((self.card / 'SOFTWARE/boot.bin').read_bytes(), b'original boot')
        self.assertFalse((self.card / 'SOFTWARE/bram.bin').exists())

    def test_success_restores_existing_and_removes_originally_absent_file(self):
        io = FakeBoard(self.card)
        result = self.run_board(io)
        self.assert_restored()
        self.assertTrue(result['restore']['verified'])
        self.assertEqual(Path(result['uart_path']).read_text(), 'Inference completed.\n')
        self.assertEqual(Path(result['uart_binary_path']).read_bytes(), b'Inference completed.\n')
        self.assertLess(io.events.index('capture_ready'), io.events.index('reboot'))
        self.assertLess(io.events.index('postflight_reboot'), io.events.index('postflight_usb_off'))
        self.assertEqual(io.mounts, 5)

    def test_timeout_restores_before_propagating(self):
        io = FakeBoard(self.card, fail=True)
        with self.assertRaises(CellFailure) as caught:
            self.run_board(io)
        self.assertEqual(caught.exception.status, 'TIMEOUT')
        self.assert_restored()
        self.assertIn('postflight_usb_off', io.events)

    def test_capture_close_failure_does_not_skip_restore(self):
        io = FakeBoard(self.card, close_fail=True)
        with self.assertRaises(CellFailure):
            self.run_board(io)
        self.assert_restored()
        self.assertIn('postflight_usb_off', io.events)

    def test_restore_failure_quarantines_target(self):
        with self.assertRaises(CellFailure) as caught:
            self.run_board(FakeBoard(self.card, restore_fail=True))
        self.assertEqual(caught.exception.status, 'BOARD_RECOVERY_ERROR')
        self.assertTrue(caught.exception.target_unusable)
        self.assertTrue((self.root / 'run/board-backup/manifest.json').is_file())

    def test_partial_deployment_is_restored(self):
        original_copy = board.shutil.copyfile

        def copy(source, destination):
            if Path(source) == self.bin / 'bram.bin':
                Path(destination).write_bytes(b'partial')
                raise OSError('write interrupted')
            return original_copy(source, destination)

        with patch.object(board.shutil, 'copyfile', side_effect=copy):
            with self.assertRaises(CellFailure):
                self.run_board(FakeBoard(self.card))
        self.assert_restored()

    def test_paths_and_unknown_adapter_rejected_before_io(self):
        for destinations in ({'boot.bin': '../outside'}, {'../outside': 'boot.bin'},
                             {'boot.bin': '/absolute'}, {'boot.bin': '.'},
                             {'boot.bin': 'same', 'bram.bin': 'same'}):
            with self.subTest(destinations=destinations):
                self.settings['destinations'] = destinations
                with patch.object(board, '_BoardIO') as io, self.assertRaises(CellFailure):
                    self.run_board(io)
                io.assert_not_called()
        self.settings['adapter'] = 'unknown'
        with self.assertRaises(CellFailure) as caught:
            self.run_board(FakeBoard(self.card))
        self.assertEqual(caught.exception.status, 'UNSUPPORTED_CONFIGURATION')

    def test_symlink_source_escape_rejected(self):
        outside = self.root / 'secret'
        outside.write_text('not an artifact')
        (self.bin / 'boot.bin').unlink()
        (self.bin / 'boot.bin').symlink_to(outside)
        with self.assertRaises(CellFailure):
            self.run_board(FakeBoard(self.card))
        self.assert_restored()

    def test_preflight_present_device_rejected(self):
        io = board._BoardIO(self.settings)
        with patch.object(io, 'present', return_value=True), self.assertRaises(CellFailure):
            io.preflight()

    def test_dead_capture_is_rejected_before_reboot_io(self):
        io = board._BoardIO(self.settings)
        capture = FakeCapture([])
        capture.running = False
        with patch.object(io, 'mcc') as mcc, self.assertRaises(CellFailure):
            io.reboot(capture)
        mcc.assert_not_called()

    def test_shared_memory_diagnostic_returns_for_classification_without_timeout(self):
        capture = object.__new__(board._Capture)
        with patch.object(board._Capture, 'running', True), \
                patch.object(capture, 'text', return_value='tensor arena is too small'):
            capture.wait(0.01)

    def test_uart_aliases_cannot_select_the_same_port(self):
        io = board._BoardIO(dict(self.settings, mcc_port='/dev/null', uart_port='/dev/null'))
        with patch.object(io, 'present', return_value=False), \
                patch.object(io, '_holders') as holders, self.assertRaises(CellFailure):
            io.preflight()
        holders.assert_not_called()

    def test_wrong_card_identity_cannot_mount(self):
        io = board._BoardIO(self.settings)
        response = subprocess.CompletedProcess([], 0,
            '{"blockdevices":[{"fstype":"vfat","label":"PERSONAL","pkname":"sdb"}]}', '')
        with patch.object(board, '_command', return_value=response) as command:
            with self.assertRaises(CellFailure):
                with io.mount(False):
                    self.fail('wrong card mounted')
        self.assertEqual(command.call_count, 1)

    def test_sudo_permission_failure_is_environment_unavailable(self):
        response = subprocess.CompletedProcess([], 1, '', 'sudo: a password is required')
        with patch.object(board.subprocess, 'run', return_value=response) as run:
            with self.assertRaises(CellFailure) as caught:
                board._command('sudo', '-n', 'mount', '/dev/example', '/tmp/example')
        self.assertEqual(caught.exception.status, 'ENVIRONMENT_UNAVAILABLE')
        self.assertEqual(run.call_args.args[0][:2], ('sudo', '-n'))
        self.assertNotIn('shell', run.call_args.kwargs)

    def test_unmount_failure_never_deletes_card_contents(self):
        io = board._BoardIO(self.settings)
        mountpoint = self.root / 'mountpoint'
        mountpoint.mkdir()

        def command(*argv, **kwargs):
            if argv[0] == 'lsblk':
                output = ('{"blockdevices":[{"fstype":"vfat","label":"M1SDP",'
                          '"pkname":"sdb"}]}') if '-J' in argv else 'usb\n'
            elif 'umount' in argv:
                raise CellFailure('ENVIRONMENT_UNAVAILABLE', 'board_environment', 'umount failed')
            else:
                output = ''
            return subprocess.CompletedProcess(argv, 0, output, '')

        with patch.object(board, '_command', side_effect=command), \
                patch.object(board.tempfile, 'mkdtemp', return_value=str(mountpoint)):
            with self.assertRaises(CellFailure):
                with io.mount(False) as mounted:
                    (mounted / 'precious.bin').write_bytes(b'preserve')
        self.assertEqual((mountpoint / 'precious.bin').read_bytes(), b'preserve')
        self.assertTrue(io.mounted)
        with self.assertRaises(CellFailure):
            io.usb(False)


if __name__ == '__main__':
    unittest.main()
