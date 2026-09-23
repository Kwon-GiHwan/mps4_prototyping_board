"""Deploy-free control: run END_ONLY (mode 1) through the Tier B host sequence on the
current image. Distinguishes 'firmware EVENTS path stops counting' from 'host sequence
(RESET per set) stops counting'. Prints window/armed/enable/progress per run."""
import sys, pathlib, zlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from runner_proto import RunnerLink, PROTO_MEASURE_V2, INSTRUMENTATION_END_ONLY
PORT = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if01-port0"

def prime(l):
    b = b"\x00" * 64
    l.load_model_begin(len(b), zlib.crc32(b) & 0xFFFFFFFF); l.load_model_chunk(0, b); l.load_model_end(); l.load_input(b"")

def show(tag, l, rc):
    p = l.last_measurement.pmu
    print(f"{tag}: rc={rc} armed={p['cycle_counter_armed']} en={p['cycle_global_enable_verified']} "
          f"progress={p['cycle_progress_observed']} window_raw={p['npu_pmu_window_cycles_raw']} "
          f"mode_applied={p['instrumentation_mode_applied']} mmio_w={p['pmu_mmio_write_count_delta']}", flush=True)

l = RunnerLink(PORT, protocol=PROTO_MEASURE_V2)
print("ping:", l.ping())
print("--- A: RESET -> END_ONLY -> prime -> run x3   (the Tier B per-set shape, mode 1)")
l.reset_runner(); print("set_mode:", l.set_instrumentation_mode(INSTRUMENTATION_END_ONLY, [], 900)); prime(l)
for i in range(3): rc = l.run(timeout=60); show(f"A run{i+1}", l, rc)
print("--- B: second RESET cycle, same shape")
l.reset_runner(); l.set_instrumentation_mode(INSTRUMENTATION_END_ONLY, [], 901); prime(l)
for i in range(3): rc = l.run(timeout=60); show(f"B run{i+1}", l, rc)
print("--- C: EVENTS mode, count=1 (cycle id 17) through the same shape, for contrast")
l.reset_runner(); print("set_mode:", l.set_instrumentation_mode(2, [17], 902)); prime(l)
for i in range(2):
    rc = l.run(timeout=60); show(f"C run{i+1}", l, rc); print("   ev codes/values:", l.last_measurement.pmu["event_codes"][:1], l.last_measurement.pmu["event_values"][:1])
l.close()
