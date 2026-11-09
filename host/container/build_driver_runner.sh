#!/bin/sh
# Driver runner image (docs/plan/driver_runner_plan.md J1): MLEK b2c0bb2's own cmake with the stock-MLEK platform options
# (the same flags as host/container/build_mlek_equiv.sh's stock build) and the out-of-tree use case pmu_runner.
#   sh build_driver_runner.sh <repo copy with firmware/driver_runner and firmware/common> <out dir (new)>
# The MLEK tree is not modified (checked before and after). Kept: the image set (boot.bin bram.bin ddr.bin images.txt
# if produced), the ELF, the map, the logs and the digests; the build tree is deleted (small board-host disk).
set -u
SRC="$1"; OUT="$2"
M=/opt/arm/ml-embedded-evaluation-kit; B="$OUT/build"
[ -e "$OUT" ] && { echo "FAIL: $OUT exists"; exit 1; }
mkdir -p "$OUT" || exit 1
cd "$M" || exit 1
git diff --quiet -- source scripts && git -C dependencies/core-driver diff --quiet || { echo "FAIL: MLEK tree not clean"; exit 1; }
export SOURCE_DATE_EPOCH=1776763519
cmake -B "$B" -S "$M" -DCMAKE_TOOLCHAIN_FILE=$M/scripts/cmake/toolchains/bare-metal-gcc.cmake -DTARGET_PLATFORM=mps4 \
  -DTARGET_SUBSYSTEM=sse-320 -DFPGA_PLATFORM_SSE_320=ON -DETHOS_U_NPU_ID=U85 -DETHOS_U_NPU_CONFIG_ID=Z1024 \
  -DETHOS_U_NPU_MEMORY_MODE=Dedicated_Sram -DETHOS_U_NPU_ENABLED=ON \
  -DUSE_CASES_SEARCH_DIR_LIST="$SRC/firmware/driver_runner/use_case" -DUSE_CASE_BUILD=pmu_runner \
  -Dpmu_runner_ACTIVATION_BUF_SZ=0x00200000 > "$OUT/cmake.log" 2>&1 || { echo "FAIL: cmake (see cmake.log)"; exit 1; }
cmake --build "$B" -j8 > "$OUT/build.log" 2>&1 || { echo "FAIL: build (see build.log)"; tail -30 "$OUT/build.log"; exit 1; }
git diff --quiet -- source scripts && git -C dependencies/core-driver diff --quiet || { echo "FAIL: MLEK tree changed by the build"; exit 1; }
cp "$B"/bin/mlek_pmu_runner.axf "$B"/bin/mlek_pmu_runner.map "$OUT/" || exit 1
# Gate: the driver hooks must be ours (strong, T), not the driver's weak defaults (W), and the driver must call them.
NM=/opt/arm/gcc-arm-none-eabi/bin/arm-none-eabi-nm; OD=/opt/arm/gcc-arm-none-eabi/bin/arm-none-eabi-objdump
for s in ethosu_address_remap ethosu_irq_handler ethosu_semaphore_create ethosu_semaphore_take ethosu_semaphore_give \
         hooks_install; do
  "$NM" "$OUT/mlek_pmu_runner.axf" | grep -q " T $s\$" || { echo "FAIL gate: $s is not the runner's strong definition"; exit 1; }
done
"$OD" -d "$OUT/mlek_pmu_runner.axf" | awk '/<ethosu_dev_run_command_stream>:/,/^$/' | grep -q "bl.*<ethosu_address_remap>" \
  || { echo "FAIL gate: ethosu_dev_run_command_stream does not call ethosu_address_remap"; exit 1; }
"$NM" "$OUT/mlek_pmu_runner.axf" | grep -q " T ethosu_inference_begin\$" \
  || { echo "FAIL gate: MLEK's profiler begin/end not linked (the platform is not stock)"; exit 1; }
echo "GATE OK: driver hooks are the runner's, MLEK profiler hooks are MLEK's"
mkdir -p "$OUT/image" && cp "$B"/bin/sectors/images.txt "$B"/bin/sectors/pmu_runner/* "$OUT/image/" || exit 1
(cd "$OUT/image" && sha256sum * > image.sha256)
rm -rf "$B"
echo "BUILT pmu_runner:"; cat "$OUT/image/image.sha256"
