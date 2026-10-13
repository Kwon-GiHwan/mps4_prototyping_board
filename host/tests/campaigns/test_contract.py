"""Exhaustive scheduling and evidence validation without SDKs or hardware."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from host.campaigns.config import file_sha, load_config, make_plan
from host.campaigns.errors import CellFailure
from host.campaigns.measurement import validate_measurement
from host.campaigns.runner import run_campaign, write_json


UART = ('Inference completed.\nTotal number of inferences: 1\n'
        'Profile for Inference:\nINFO - NPU TOTAL: 10 cycles\n'
        'INFO - NPU ACTIVE: 6 cycles\nINFO - NPU IDLE: 4 cycles\n')


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'model.tflite').write_bytes(b'model')
        self.source = {
            'schema_version': 1, 'build': {'mlek_root': str(self.root)},
            'models': [{'id': 'one', 'path': 'model.tflite'}],
            'targets': [{'id': 'fvp', 'kind': 'fvp', 'npu': 'ethos-u55',
                         'platform': 'mps3', 'subsystem': 'sse-300',
                         'supported_macs': [128], 'timing_adapter': 'ON',
                         'system_config': 'fixture', 'memory_mode': 'Shared_Sram',
                         'executable': 'fvp', 'board_prefix': 'mps3_board',
                         'mac_parameter': 'ethosu.num_macs'}],
            'variants': [{'id': 'performance', 'macs': [128]}],
            'measurement': {'repetitions': 2},
        }
        self.config_path = self.root / 'config.json'

    def config(self):
        self.config_path.write_text(json.dumps(self.source))
        return load_config(self.config_path)

    def build(self, cell, config, directory):
        directory.mkdir(parents=True)
        artifact = directory / 'firmware.axf'
        artifact.write_bytes(b'compiled fixture')
        h = file_sha(artifact)
        return {'axf': str(artifact), 'bin_dir': str(directory),
                'input_paths': {'model': cell['model']['path']},
                'vela_path': str(artifact),
                'hashes': {'model': cell['model']['sha256'], 'axf': h,
                           'vela_config': h, 'toolchain': h},
                'deployable_hashes': {'firmware.axf': h},
                'resolved': {'mlek_revision': 'a' * 40, 'versions': {}}, 'tools': {}}

    def valid_build(self, cell, config, directory):
        result = self.build(cell, config, directory)
        result['input_paths'].update(vela_config=result['axf'], toolchain=result['axf'])
        return result

    def backend(self, *args):
        return {'uart': UART, 'executable_identity': {'sha256': 'f' * 64}}

    def run_fake(self, config=None, output='run', backend=None, resume=False):
        with patch('host.campaigns.runner.builder.build', side_effect=self.valid_build), \
                patch('host.campaigns.runner.fvp.run_fvp', side_effect=backend or self.backend), \
                patch('host.campaigns.runner.board.run_board', side_effect=backend or self.backend):
            return run_campaign(config or self.config(), self.root / output, resume=resume)

    def test_full_product_keeps_unsupported_combinations(self):
        self.source['variants'][0]['macs'] = [32, 128, 2048]
        self.source['models'].append({'id': 'two', 'path': 'model.tflite'})
        plan = make_plan(self.config())
        self.assertEqual(len(plan['cells']), 6)
        self.assertEqual(len({cell['id'] for cell in plan['cells']}), 6)
        result = self.run_fake()
        self.assertEqual(result['summary'], {'UNSUPPORTED_CONFIGURATION': 4, 'SUCCESS': 2})

    def test_discovery_does_not_hardcode_seven_models(self):
        self.source.pop('models')
        models = self.root / 'resources_downloaded'
        models.mkdir()
        for index in range(9):
            (models / ('model%d.tflite' % index)).write_bytes(b'model')
        (models / 'model0_vela.tflite').write_bytes(b'compiled')
        self.source['discover_models'] = {}
        self.assertEqual(len(self.config()['models']), 9)

    def test_memory_failure_continues_and_preserves_attempt_status(self):
        self.source['variants'].append({'id': 'second', 'macs': [128]})
        outputs = iter([CellFailure('MEMORY_ERROR', 'measurement', 'arena too small'),
                        self.backend(), self.backend()])
        def backend(*args):
            value = next(outputs)
            if isinstance(value, Exception):
                raise value
            return value
        result = self.run_fake(backend=backend)
        self.assertEqual(result['summary'], {'MEMORY_ERROR': 1, 'SUCCESS': 1})
        self.assertEqual(result['cells'][0]['attempts'][0]['status'], 'MEMORY_ERROR')

    def test_internal_error_and_interrupt_terminalize_attempt(self):
        for error, status in [(RuntimeError('broken'), 'INTERNAL_ERROR'),
                              (KeyboardInterrupt(), 'INTERRUPTED')]:
            def backend(*args):
                raise error
            if isinstance(error, KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    self.run_fake(output=status, backend=backend)
            else:
                self.run_fake(output=status, backend=backend)
            result = json.loads((self.root / status / 'results.json').read_text())
            self.assertEqual(result['cells'][0]['attempts'][0]['status'], status)

    def test_board_aliases_are_quarantined_after_recovery_failure(self):
        target = self.source['targets'][0]
        target.update(kind='board', board={'mcc_port': '/dev/mcc-fixture'})
        alias = copy.deepcopy(target)
        alias['id'] = 'alias'
        self.source['targets'].append(alias)
        def backend(*args):
            raise CellFailure('BOARD_RECOVERY_ERROR', 'restore', 'failed', target_unusable=True)
        result = self.run_fake(backend=backend)
        self.assertEqual(result['summary'], {'BOARD_RECOVERY_ERROR': 1, 'TARGET_BLOCKED': 1})

    def test_resume_requires_original_evidence(self):
        config = self.config()
        result = self.run_fake(config)
        self.assertEqual(self.run_fake(config, resume=True)['summary'], {'SUCCESS': 1})
        raw = Path(result['cells'][0]['attempts'][0]['measurement_uart']['path'])
        raw.write_text(UART + 'changed')
        with self.assertRaisesRegex(ValueError, 'evidence differs'):
            self.run_fake(config, resume=True)

    def test_resume_terminalizes_stale_attempt(self):
        config = self.config()
        result = self.run_fake(config)
        result['cells'][0]['status'] = 'RUNNING'
        result['cells'][0]['attempts'][-1]['status'] = 'RUNNING'
        write_json(self.root / 'run/results.json', result)
        result = self.run_fake(config, resume=True)
        self.assertEqual(result['cells'][0]['attempts'][-1]['status'], 'INTERRUPTED')

    def test_option_bypass_is_visible_failure(self):
        self.source['variants'][0]['vela_options'] = ['--output-d', '/other']
        self.assertEqual(self.run_fake()['summary'], {'UNSUPPORTED_CONFIGURATION': 1})

    def test_exact_repeat_mismatch_retains_both_samples(self):
        self.source['measurement']['repeat_policy'] = 'exact'
        outputs = iter([self.backend(), {'uart': UART.replace('ACTIVE: 6', 'ACTIVE: 5')
                                        .replace('IDLE: 4', 'IDLE: 5'),
                                        'executable_identity': {'sha256': 'f' * 64}}])
        result = self.run_fake(backend=lambda *args: next(outputs))
        self.assertEqual(result['summary'], {'MEASUREMENT_MISMATCH': 1})
        self.assertEqual(len(result['cells'][0]['attempts']), 2)
        self.assertTrue(all(Path(a['measurement_uart']['path']).exists()
                            for a in result['cells'][0]['attempts']))

    def test_stable_serial_alias_is_preserved(self):
        device = self.root / 'tty-fixture'
        device.touch()
        alias = self.root / 'stable-device'
        alias.symlink_to(device)
        self.source['targets'][0].update(kind='board', board={'mcc_port': str(alias)})
        self.assertEqual(self.config()['targets'][0]['board']['mcc_port'], str(alias))

    def test_resume_rejects_changed_model(self):
        self.run_fake()
        (self.root / 'model.tflite').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'identical contract'):
            self.run_fake(resume=True)


class MeasurementTests(unittest.TestCase):
    def test_recorded_fvp_uart(self):
        root = Path(__file__).resolve().parents[3]
        directory = root / 'docs/paper/evidence/fvp-qualification-20260824'
        for name, total in [('qualification_uart.txt', 4115068), ('rnnoise_uart.txt', 49086)]:
            with self.subTest(name=name):
                self.assertEqual(validate_measurement((directory / name).read_text())['total'], total)

    def test_valid_and_cpu_only_observation(self):
        self.assertEqual(validate_measurement(UART)['total'], 10)
        cpu_only = UART.replace('ACTIVE: 6', 'ACTIVE: 0').replace('IDLE: 4', 'IDLE: 10')
        self.assertTrue(validate_measurement(cpu_only)['no_npu_activity'])

    def test_bad_measurements_are_never_success(self):
        invalid = [UART.replace('10 cycles', '10 bytes'),
                   UART + ' INFO - NPU AUX: -2 beats\n',
                   UART + 'INFO - NPU TOTAL: 10 cycles\n',
                   UART.replace('IDLE: 4', 'IDLE: 3'),
                   UART.replace('inferences: 1', 'inferences: 2'),
                   UART + 'NPU initialisation failed\n',
                   UART + 'HardFault\n',
                   UART + 'tensor arena is too small\n']
        for text in invalid:
            with self.subTest(text=text), self.assertRaises(CellFailure):
                validate_measurement(text)


if __name__ == '__main__':
    unittest.main()
