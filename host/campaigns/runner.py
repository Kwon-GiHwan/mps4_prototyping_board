"""Durable exhaustive campaigns: failed cells remain visible and do not disappear."""

from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
import tempfile

from . import build as builder
from . import board, fvp
from .config import file_sha, make_plan
from .options import validate_options
from .errors import CellFailure
from .measurement import validate_measurement


def write_json(path, value):
    path = Path(path)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                     prefix='.' + path.name, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def initialize(config, output, resume=False):
    output = Path(output).resolve()
    plan = make_plan(config)
    if resume:
        stored = json.loads((output / 'results.json').read_text())
        if stored.get('plan_id') != plan['plan_id'] or stored.get('config') != plan['config'] or stored.get('contract') != plan['contract']:
            raise ValueError('resume requires the identical contract, model bytes and configuration')
        originals = [{k: cell[k] for k in ('id', 'model', 'target', 'options')} for cell in plan['cells']]
        actual = [{k: cell[k] for k in ('id', 'model', 'target', 'options')} for cell in stored['cells']]
        if actual != originals:
            raise ValueError('stored matrix differs from the requested plan')
        if json.loads((output / 'plan.json').read_text()) != plan:
            raise ValueError('original plan differs from requested configuration')
        _verify_successes(stored, config)
        plan = stored
    else:
        output.mkdir(parents=True, exist_ok=False)
        write_json(output / 'plan.json', plan)
    return plan, output


def _resources(target):
    if target['kind'] != 'board':
        return {'target:' + target['id']}
    settings = target.get('board', {})
    return {'board:' + path
            for key in ('mcc_port', 'uart_port', 'block_device', 'partition')
            if settings.get(key)
            for path in (settings[key], str(Path(settings[key]).resolve()))
            } | {'target:' + target['id']}


def _verify_successes(plan, config):
    terminal = {'PENDING', 'RUNNING', 'SUCCESS', 'MEMORY_ERROR', 'BUILD_ERROR',
                'EXECUTION_ERROR', 'TIMEOUT', 'UNSUPPORTED_CONFIGURATION',
                'ENVIRONMENT_UNAVAILABLE', 'INVALID_MEASUREMENT', 'IDENTITY_MISMATCH',
                'MEASUREMENT_MISMATCH', 'BOARD_RECOVERY_ERROR', 'TARGET_BLOCKED',
                'INTERRUPTED', 'INTERNAL_ERROR'}
    for cell in plan['cells']:
        if cell['status'] not in terminal:
            raise ValueError('unknown stored cell status')
        if cell['status'] != 'SUCCESS':
            continue
        if len(cell['attempts']) != config['measurement']['repetitions']:
            raise ValueError('successful cell has incomplete repetitions')
        artifacts = cell['artifacts']
        if _build_identity(artifacts) != plan.get('build_identity'):
            raise ValueError('resume build identity differs')
        paths = {**artifacts['input_paths'], 'vela': artifacts['vela_path'],
                 'axf': artifacts['axf']}
        for name, expected in artifacts['hashes'].items():
            if file_sha(paths[name]) != expected:
                raise ValueError('resume artifact differs: ' + name)
        for relative, expected in artifacts['deployable_hashes'].items():
            if file_sha(Path(artifacts['bin_dir']) / relative) != expected:
                raise ValueError('resume deployment artifact differs')
        for attempt in cell['attempts']:
            raw = attempt['measurement_uart']
            if attempt['status'] != 'SUCCESS' or file_sha(raw['path']) != raw['sha256']:
                raise ValueError('resume measurement evidence differs')
            if validate_measurement(Path(raw['path']).read_text()) != attempt['metrics']:
                raise ValueError('resume parsed measurement differs')
            for path_key, hash_key in [('uart_path', 'uart_sha256'),
                                       ('uart_binary_path', 'uart_binary_sha256')]:
                if path_key in attempt and file_sha(attempt[path_key]) != attempt[hash_key]:
                    raise ValueError('resume original UART differs')
        if config['measurement']['repeat_policy'] == 'exact':
            if any(a['metrics']['events'] != cell['attempts'][0]['metrics']['events']
                   for a in cell['attempts'][1:]):
                raise ValueError('resume repeat policy violation')


def _build_identity(artifacts):
    return {'mlek_revision': artifacts['resolved']['mlek_revision'],
            'tools': artifacts['tools'],
            'versions': artifacts['resolved']['versions'],
            'vela_config': artifacts['hashes']['vela_config'],
            'toolchain': artifacts['hashes']['toolchain']}


def _failure(cell, error):
    cell['status'] = error.status
    cell['failure'] = {'stage': error.stage, 'detail': error.detail,
                       'target_unusable': error.target_unusable}
    if cell['attempts'] and cell['attempts'][-1]['status'] == 'RUNNING':
        cell['attempts'][-1].update(status=error.status, failure=cell['failure'])


def run_campaign(config, output, *, resume=False):
    output = Path(output).resolve()
    if not resume:
        plan, output = initialize(config, output, False)
    lock = output / '.running'
    try:
        lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError('campaign is running or needs recovery; inspect .running before resuming') from exc
    os.close(lock_fd)
    try:
        if resume:
            plan, output = initialize(config, output, True)
    except BaseException:
        lock.unlink(missing_ok=True)
        raise
    quarantined = {
        resource for cell in plan['cells']
        if (cell.get('failure') or {}).get('target_unusable')
        for resource in _resources(cell['target'])
    }
    try:
        # A process killed while touching a board requires manual recovery. No retry
        # silently mixes a second attempt into the original sample count.
        for cell in plan['cells']:
            if cell['status'] == 'RUNNING':
                unsafe = cell['target']['kind'] == 'board'
                _failure(cell, CellFailure('INTERRUPTED', 'resume', 'previous attempt did not finish', target_unusable=unsafe))
                if unsafe:
                    quarantined.update(_resources(cell['target']))
        write_json(output / 'results.json', plan)
        for cell in plan['cells']:
            if cell['status'] != 'PENDING':
                continue
            if _resources(cell['target']) & quarantined:
                _failure(cell, CellFailure('TARGET_BLOCKED', 'preflight', 'target requires recovery', target_unusable=True))
                write_json(output / 'results.json', plan)
                continue
            cell['status'] = 'RUNNING'
            directory = output / cell['id']
            directory.mkdir(exist_ok=False)
            write_json(output / 'results.json', plan)
            try:
                target, options, model = cell['target'], cell['options'], cell['model']
                validate_options(target, options)
                if options['mac'] not in target['supported_macs']:
                    raise CellFailure('UNSUPPORTED_CONFIGURATION', 'preflight', 'MAC is outside the declared target support set')
                if not Path(model['path']).is_file():
                    raise CellFailure('ENVIRONMENT_UNAVAILABLE', 'preflight', 'model file is unavailable: ' + model['path'])
                if file_sha(model['path']) != model['sha256']:
                    raise CellFailure('IDENTITY_MISMATCH', 'preflight', 'model bytes differ from the planned input')
                artifacts = builder.build(cell, config, directory / 'build')
                identity = _build_identity(artifacts)
                cell['artifacts'] = artifacts
                if 'build_identity' in plan and plan['build_identity'] != identity:
                    raise CellFailure('IDENTITY_MISMATCH', 'identity', 'campaign build environment changed')
                plan.setdefault('build_identity', identity)
                write_json(output / 'results.json', plan)
                backend = fvp.run_fvp if target['kind'] == 'fvp' else board.run_board
                for repetition in range(1, config['measurement']['repetitions'] + 1):
                    run_dir = directory / ('run-%03d' % repetition)
                    run_dir.mkdir()
                    attempt = {'repetition': repetition, 'status': 'RUNNING'}
                    cell['attempts'].append(attempt)
                    write_json(output / 'results.json', plan)
                    result = backend(cell, config, artifacts, run_dir)
                    if target['kind'] == 'fvp':
                        identities = plan.setdefault('fvp_identities', {})
                        observed = result['executable_identity']
                        previous = identities.setdefault(target['id'], observed)
                        if previous != observed:
                            raise CellFailure('IDENTITY_MISMATCH', 'identity', 'FVP changed within campaign')
                    # Retain original bytes in the backend and normalized text here.
                    # Parser failure cannot erase the raw evidence for that attempt.
                    text = result.pop('uart')
                    raw = run_dir / 'measurement.uart.txt'
                    raw.write_text(text, encoding='utf-8')
                    attempt.update(result)
                    attempt['measurement_uart'] = {'path': str(raw), 'sha256': file_sha(raw)}
                    metrics = validate_measurement(text)
                    attempt.update(status='SUCCESS', metrics=metrics)
                    if config['measurement']['repeat_policy'] == 'exact' and repetition > 1:
                        first = cell['attempts'][0]['metrics']['events']
                        if metrics['events'] != first:
                            raise CellFailure('MEASUREMENT_MISMATCH', 'repeat', 'counter vector differs under exact repeat policy')
                    write_json(output / 'results.json', plan)
                cell['status'] = 'SUCCESS'
            except CellFailure as exc:
                _failure(cell, exc)
                if cell['attempts']:
                    cell['attempts'][-1].update(status=exc.status, failure=cell['failure'])
                if exc.target_unusable:
                    quarantined.update(_resources(cell['target']))
            except KeyboardInterrupt:
                unsafe = cell['target']['kind'] == 'board'
                _failure(cell, CellFailure('INTERRUPTED', 'execution', 'interrupted by operator', target_unusable=unsafe))
                write_json(output / 'results.json', plan)
                raise
            except Exception as exc:
                # Unexpected failures are never success and never inferred as memory errors.
                unsafe = cell['target']['kind'] == 'board'
                _failure(cell, CellFailure('INTERNAL_ERROR', 'execution', type(exc).__name__ + ': ' + str(exc), target_unusable=unsafe))
                if unsafe:
                    quarantined.update(_resources(cell['target']))
            write_json(output / 'results.json', plan)
        plan['summary'] = dict(Counter(cell['status'] for cell in plan['cells']))
        plan['execution_finished'] = not any(cell['status'] in ('PENDING', 'RUNNING') for cell in plan['cells'])
        write_json(output / 'results.json', plan)
        return plan
    finally:
        lock.unlink(missing_ok=True)
