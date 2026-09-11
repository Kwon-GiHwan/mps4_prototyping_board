"""Explicit options and exhaustive model × target × variant × MAC planning."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re

CONTRACT = {
    "id": "stock-mlek-single-inference-v1",
    "runner": "inference_runner",
    "start": "fresh FVP process or fresh board boot, capture ready before reset",
    "completion": "one Inference completed marker, inference count one, one PMU block",
    "warmup_runs": 0,
    "input_policy": "unmodified stock MLEK runner from the recorded source revision",
    "cycle_scope": "NPU profile counters; host elapsed time is not inference latency",
    "cpu_fallback": "allowed and recorded; no model silently removed",
    "comparison": "same contract does not imply cross-platform absolute-cycle comparability",
}
VALID_MACS = {"ethos-u55": (32, 64, 128, 256), "ethos-u65": (256, 512),
              "ethos-u85": (128, 256, 512, 1024, 2048)}
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_sha(path):
    with Path(path).open('rb') as stream:
        result = hashlib.file_digest(stream, 'sha256') if hasattr(hashlib, 'file_digest') else None
        if result is not None:
            return result.hexdigest()
        h = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
        return h.hexdigest()


def _keys(value, allowed, where):
    if not isinstance(value, dict):
        raise ValueError(where + ' must be an object')
    extra = value.keys() - set(allowed)
    if extra:
        raise ValueError('%s: unknown keys %s' % (where, sorted(extra)))


def _positive(value, name):
    if type(value) is not int or value <= 0:
        raise ValueError(name + ' must be a positive integer')
    return value


def _identifier(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError('invalid identifier: %r' % value)
    return value


def _unique(items, kind):
    if not isinstance(items, list) or not items:
        raise ValueError(kind + ' must be a nonempty list')
    ids = [_identifier(item['id']) for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate ' + kind + ' id')


def _path(value, base):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('path must be a nonempty string')
    p = Path(value).expanduser()
    return str((base / p).resolve())


def load_config(path):
    source = Path(path).resolve()
    config = json.loads(source.read_text())
    _keys(config, ['schema_version', 'build', 'models', 'discover_models', 'targets',
                   'variants', 'measurement'], 'campaign')
    if type(config.get('schema_version')) is not int or config['schema_version'] != 1:
        raise ValueError('schema_version must be 1')
    build = config['build']
    _keys(build, ['mlek_root', 'vela', 'cmake', 'vela_config', 'toolchain_file', 'epoch',
                  'jobs', 'timeout_seconds', 'mlek_revision'], 'build')
    if 'mlek_revision' in build and (not isinstance(build['mlek_revision'], str) or
                                     not re.fullmatch('[0-9a-f]{40}', build['mlek_revision'])):
        raise ValueError('mlek_revision must be a full Git SHA-1 revision')
    build['mlek_root'] = _path(build['mlek_root'], source.parent)
    kit = Path(build['mlek_root'])
    for name, default in [('vela', 'vela'), ('cmake', 'cmake')]:
        build.setdefault(name, default)
        if not isinstance(build[name], str) or not build[name]:
            raise ValueError(name + ' must name an executable')
        if '/' in build[name]:
            build[name] = _path(build[name], source.parent)
    for name, default in [('vela_config', 'scripts/vela/default_vela.ini'),
                          ('toolchain_file', 'scripts/cmake/toolchains/bare-metal-gcc.cmake')]:
        build[name] = _path(build.get(name, default), kit)
    for key, default in [('epoch', 1776763519), ('jobs', 1), ('timeout_seconds', 1800)]:
        build[key] = _positive(build.get(key, default), key)
    measurement = config.setdefault('measurement', {})
    _keys(measurement, ['repetitions', 'timeout_seconds', 'repeat_policy'], 'measurement')
    for key, default in [('repetitions', 3), ('timeout_seconds', 3600)]:
        measurement[key] = _positive(measurement.get(key, default), key)
    measurement.setdefault('repeat_policy', 'record')
    if measurement['repeat_policy'] not in ('record', 'exact'):
        raise ValueError('repeat_policy must be record or exact')
    if ('models' in config) == ('discover_models' in config):
        raise ValueError('specify exactly one of models or discover_models')
    if 'discover_models' in config:
        discovery = config['discover_models']
        _keys(discovery, ['root', 'include', 'exclude'], 'discover_models')
        root = Path(_path(discovery.get('root', 'resources_downloaded'), kit))
        if not root.is_dir():
            raise ValueError('model discovery directory is unavailable: ' + str(root))
        includes = discovery.get('include', ['**/*.tflite'])
        excludes = discovery.get('exclude', ['**/*_vela.tflite'])
        for patterns in (includes, excludes):
            if not isinstance(patterns, list) or any(not isinstance(p, str) for p in patterns):
                raise ValueError('model glob patterns must be lists of strings')
        excluded = {p.resolve() for pattern in excludes for p in root.glob(pattern)}
        files = sorted({p.resolve() for pattern in includes for p in root.glob(pattern)
                        if p.is_file() and p.resolve() not in excluded})
        config['models'] = [
            {'id': 'model-' + hashlib.sha256(str(p.relative_to(root)).encode()).hexdigest()[:16],
             'path': str(p)} for p in files
        ]
        discovery['root'] = str(root)
    _unique(config['models'], 'models')
    for model in config['models']:
        _keys(model, ['id', 'path', 'sha256'], 'model')
        model['path'] = _path(model['path'], kit)
        expected = model.get('sha256')
        if expected is not None and (not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected)):
            raise ValueError('model sha256 must be a lowercase SHA-256 digest')
        if expected is None and Path(model['path']).is_file():
            model['sha256'] = file_sha(model['path'])
        else:
            model.setdefault('sha256', None)
    _unique(config['targets'], 'targets')
    for target in config['targets']:
        _keys(target, ['id', 'kind', 'npu', 'platform', 'subsystem', 'supported_macs',
                       'timing_adapter', 'system_config', 'memory_mode', 'executable',
                       'mac_parameter', 'board_prefix', 'cmake_options', 'board'], 'target')
        if target['kind'] not in ('fvp', 'board') or target['npu'] not in VALID_MACS:
            raise ValueError('unknown target kind or NPU')
        for key in ('platform', 'subsystem', 'system_config', 'memory_mode'):
            if not isinstance(target.get(key), str) or not target[key]:
                raise ValueError('target requires ' + key)
        if target.get('timing_adapter') not in ('ON', 'OFF'):
            raise ValueError('target timing_adapter must be explicit ON or OFF')
        macs = target['supported_macs']
        if not isinstance(macs, list) or not macs or any(type(m) is not int or m not in VALID_MACS[target['npu']] for m in macs):
            raise ValueError('invalid declared supported_macs')
        if target['kind'] == 'fvp':
            for key in ('executable', 'mac_parameter', 'board_prefix'):
                if not isinstance(target.get(key), str) or not target[key]:
                    raise ValueError('FVP target requires ' + key)
            if '/' in target['executable']:
                target['executable'] = _path(target['executable'], source.parent)
        target.setdefault('cmake_options', {})
        if not isinstance(target['cmake_options'], dict):
            raise ValueError('target cmake_options must be an object')
        if target['kind'] == 'board':
            settings = target.get('board', {})
            if not isinstance(settings, dict):
                raise ValueError('board must be an object')
            for key in ('mcc_port', 'uart_port', 'block_device', 'partition'):
                if key in settings:
                    settings[key] = os.path.abspath(source.parent / Path(settings[key]).expanduser())
    _unique(config['variants'], 'variants')
    for variant in config['variants']:
        _keys(variant, ['id', 'macs', 'activation_bytes', 'optimise', 'system_config',
                        'memory_mode', 'vela_options', 'cmake_options', 'fvp_parameters'], 'variant')
        if not isinstance(variant['macs'], list) or not variant['macs']:
            raise ValueError('variant requires MAC candidates')
        for mac in variant['macs']:
            _positive(mac, 'MAC candidate')
        if len(set(variant['macs'])) != len(variant['macs']):
            raise ValueError('duplicate MAC candidates')
        variant['activation_bytes'] = _positive(variant.get('activation_bytes', 0x200000), 'activation_bytes')
        for key in ('system_config', 'memory_mode'):
            if key in variant and (not isinstance(variant[key], str) or not variant[key]):
                raise ValueError('variant ' + key + ' must be a nonempty string')
        variant.setdefault('optimise', 'Performance')
        if variant['optimise'] not in ('Performance', 'Size'):
            raise ValueError('invalid optimisation policy')
        for name, default in [('vela_options', []), ('cmake_options', {}), ('fvp_parameters', {})]:
            variant.setdefault(name, default)
        if not isinstance(variant['vela_options'], list) or any(not isinstance(v, str) for v in variant['vela_options']):
            raise ValueError('vela_options must be an argv list')
        for name in ('cmake_options', 'fvp_parameters'):
            if not isinstance(variant[name], dict):
                raise ValueError(name + ' must be an object')
    # JSON canonicalization rejects NaN/infinity before a plan can be accepted.
    canonical(config)
    return config


def make_plan(config):
    cells = []
    for model in config['models']:
        for target in config['targets']:
            for variant in config['variants']:
                for mac in variant['macs']:
                    options = copy.deepcopy(variant)
                    options.pop('macs')
                    options['mac'] = mac
                    options['system_config'] = options.get('system_config', target['system_config']).format(mac=mac)
                    options['memory_mode'] = options.get('memory_mode', target['memory_mode'])
                    definition = {'model': model, 'target': target, 'options': options}
                    cells.append(dict(copy.deepcopy(definition), id=digest(definition),
                                      status='PENDING', attempts=[], failure=None))
    definition = {'contract': CONTRACT, 'config': config}
    return {'schema_version': 1, 'plan_id': digest(definition), **copy.deepcopy(definition), 'cells': cells}
