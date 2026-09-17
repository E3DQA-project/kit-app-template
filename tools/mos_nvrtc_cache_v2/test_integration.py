"""Real embedded-NVRTC subprocess tests; no GPU context or GUI required."""
import ctypes as C
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def child():
    original = C.CDLL(os.environ['MOS_V2_LIBRARY'], mode=C.RTLD_LOCAL)
    lib = C.CDLL(None) if os.environ.get('MOS_TEST_PRELOAD') else C.CDLL(os.environ['MOS_V2_SHIM'], mode=C.RTLD_LOCAL)
    for symbol in ('nvrtcCreateProgram', 'nvrtcAddNameExpression', 'nvrtcGetLoweredName'):
        assert hasattr(lib, symbol), 'missing replay API: ' + symbol
    def bind(name, types):
        f = getattr(lib, name)
        f.restype, f.argtypes = C.c_int, types
        return f
    P = C.c_void_p
    create = bind('nvrtcCreateProgram', [C.POINTER(P), C.c_char_p, C.c_char_p, C.c_int, C.c_void_p, C.c_void_p])
    add = bind('nvrtcAddNameExpression', [P, C.c_char_p])
    compile_ = bind('nvrtcCompileProgram', [P, C.c_int, C.POINTER(C.c_char_p)])
    name = bind('nvrtcGetLoweredName', [P, C.c_char_p, C.POINTER(C.c_void_p)])
    size = bind('nvrtcGetPTXSize', [P, C.POINTER(C.c_size_t)])
    get = bind('nvrtcGetPTX', [P, C.c_void_p])
    destroy = bind('nvrtcDestroyProgram', [C.POINTER(P)])
    programs = []
    expressions = [b'kernel<float>', b'kernel<int>']
    if os.environ.get('MOS_TEST_EXTRA'):
        expressions.append(b'kernel<double>')
    outputs = []
    held = []
    for index in range(2):
        p = P()
        source = f'template<class T> __global__ void kernel(T* p) {{p[threadIdx.x]=T({index+7});}}'.encode()
        assert create(C.byref(p), source, b'test.cu', 0, None, None) == 0
        programs.append(p)
        for expr in expressions:
            assert add(p, expr) == 0
        opts = (C.c_char_p * 2)(b'--gpu-architecture=compute_90', b'--std=c++17')
        assert compile_(p, 2, opts) == 0
        n = C.c_size_t()
        assert size(p, C.byref(n)) == 0
        data = C.create_string_buffer(n.value)
        assert get(p, data) == 0
        names = {}
        for expr in expressions:
            ptr = C.c_void_p()
            assert name(p, expr, C.byref(ptr)) == 0, 'name lookup failed after compile/replay'
            value = C.string_at(ptr)
            assert value in data.raw
            held.append((ptr, value))
            names[expr.decode()] = value.decode()
        assert name(p, b'not_registered', C.byref(C.c_void_p())) != 0
        outputs.append(dict(names=names, ptx=data.raw.hex()))
    # Other programs and lookups must not invalidate returned name pointers.
    for ptr, value in held:
        assert C.string_at(ptr) == value
    for p in programs:
        assert destroy(C.byref(p)) == 0
    print(json.dumps(outputs))


def parent(shim, renderer):
    with tempfile.TemporaryDirectory(prefix='mos-name-cache-test-') as directory:
        env = dict(os.environ, MOS_V2_SHIM=str(Path(shim).resolve()), MOS_V2_LIBRARY=str(Path(renderer).resolve()),
                   MOS_V2_DIR=directory, MOS_V2_SCOPE='cpu-test-single-scene', MOS_V2_MODE='seed')
        if os.environ.get('MOS_TEST_PRELOAD'):
            env['LD_PRELOAD'] = env['MOS_V2_SHIM']
        def invoke():
            p = subprocess.run([sys.executable, __file__, '--child'], env=env, text=True, capture_output=True, timeout=40)
            assert p.returncode == 0, p.stderr
            return json.loads(p.stdout), p.stderr
        env['MOS_V2_MODE'] = 'auto'
        first, first_log = invoke()
        second, second_log = invoke()
        assert first == second
        assert first_log.count('event=compile ') == 2
        assert first_log.count('event=stored ') == 2
        assert second_log.count('event=hit ') == 2
        assert 'event=compile ' not in second_log
        env['MOS_V2_MODE'] = 'seed'
        cold, cold_log = invoke()
        env['MOS_V2_MODE'] = 'replay'
        warm, warm_log = invoke()
        assert warm == cold, 'warm PTX or names changed'
        assert warm_log.count('event=hit ') == 2, warm_log
        assert 'event=compile ' not in warm_log, warm_log
        artifacts = list(Path(directory).glob('*.bin'))
        assert len(artifacts) == 2
        # Truncation must be rejected BEFORE reporting a replay success.
        for path in artifacts:
            path.write_bytes(path.read_bytes()[:25])
        fallback, fallback_log = invoke()
        assert fallback == cold
        assert fallback_log.count('event=compile ') == 2, fallback_log
        # Source unchanged, but new name expressions require a different key.
        env['MOS_TEST_EXTRA'] = '1'
        extra, extra_log = invoke()
        assert extra_log.count('event=compile ') == 2, extra_log
        assert len(extra[0]['names']) == 3
        extra_warm, extra_warm_log = invoke()
        assert extra_warm == extra and extra_warm_log.count('event=hit ') == 2
        # Content corruption, distinct from truncation.
        for path in Path(directory).glob('*.bin'):
            data = bytearray(path.read_bytes())
            data[-1] ^= 1
            path.write_bytes(data)
        _, corrupt_log = invoke()
        assert corrupt_log.count('event=compile ') == 2
        print('PASS: cold/warm identity, skipped compile, two programs, pointer lifetime, missing name, truncation, checksum, name-key isolation')


if __name__ == '__main__':
    if sys.argv[1:] == ['--child']:
        child()
    else:
        parent(*sys.argv[1:])
