#!/bin/sh
# Equivalence C-a/C-b/C-c (docs/plan/equivalence_plan.md §9): one MLEK b2c0bb2 inference_runner image for one model.
#   sh build_mlek_equiv.sh <model.tflite> <name> <verify|stock|events> <out root>
# verify = VERIFY_TEST_OUTPUT=1 with the amendment-2 six-line fix (dumps IFM/OFM; no performance number is used);
# stock  = the stage-B build (profiler counters ACTIVE + four beats);
# events = stock + mlek_profiler_events.py (counters 6-8: MAC_ACTIVE, MAC_DPU_ACTIVE, AO_ACTIVE).
# Vela output first, with the packer's options (G2 checks it equals the blob's); every MLEK source change is undone and
# checked by digest before exit; only the image set (boot.bin bram.bin ddr.bin images.txt), the Vela output, the logs
# and the digests are kept: the build tree is deleted (the board host's disk is small).
set -u
MODEL="$1"; NAME="$2"; VAR="$3"; OUT="$4"
M=/opt/arm/ml-embedded-evaluation-kit; HERE=$(cd "$(dirname "$0")" && pwd)
D="$OUT/$NAME/$VAR"; B="$D/build"
[ -e "$D" ] && { echo "FAIL: $D exists"; exit 1; }
mkdir -p "$D/vela" || exit 1
export SOURCE_DATE_EPOCH=1776763519
A=source/app/use_case/inference_runner/src/UseCaseHandler.cc H=source/app/main/include/UseCaseCommonUtils.hpp C=source/app/main/UseCaseCommonUtils.cc
cd "$M" || exit 1
git diff --quiet -- "$A" "$H" "$C" source/hal || { echo "FAIL: MLEK sources not clean"; exit 1; }
vela "$MODEL" --accelerator-config ethos-u85-1024 --optimise Performance --config "$M/scripts/vela/default_vela.ini" \
  --memory-mode Dedicated_Sram --system-config Ethos_U85_SYS_DRAM_Mid_1024 --output-dir "$D/vela" > "$D/vela.log" 2>&1 \
  || { echo "FAIL: vela"; exit 1; }
VT=$(ls "$D"/vela/*_vela.tflite); sha256sum "$VT" > "$D/mlek_vela.sha256"
FLAG=""
undo() {
  git checkout -- "$A" "$H" "$C" 2>/dev/null
  [ "$VAR" = events ] && python3 "$HERE/mlek_profiler_events.py" restore "$M" > "$D/restore.log" 2>&1
  git diff --quiet -- "$A" "$H" "$C" source/hal && echo "SOURCES_RESTORED" || echo "FAIL: sources not restored"
}
trap undo EXIT
case "$VAR" in
  verify)
    FLAG="-DVERIFY_TEST_OUTPUT=1"
    sed -i "100s/const Model& model/const fwk::iface::Model\& model/;108s/const Model& model/const fwk::iface::Model\& model/" $A
    sed -i "59s/void DumpTensor(const TfLiteTensor\* tensor,/void DumpTensor(const std::shared_ptr<fwk::iface::TensorIface>\& tensor,/" $H
    sed -i "106s/void DumpTensor(const TfLiteTensor\* tensor,/void DumpTensor(const std::shared_ptr<fwk::iface::TensorIface>\& tensor,/;113s/tensor->bytes;/tensor->Bytes();/;114s/tflite::GetTensorData<uint8_t>(tensor);/tensor->GetData<uint8_t>();/" $C
    git diff "$A" "$H" "$C" > "$D/verify_fix.diff"
    cmp -s "$D/verify_fix.diff" "$HERE/../../evidence/stage1/a2/mlek_golden/verify_test_output_fix6.diff" 2>/dev/null \
      && echo "PATCH_IDENTICAL_TO_A2" || echo "NOTE: compare verify_fix.diff with the a2 diff by hand";;
  stock) ;;
  events) python3 "$HERE/mlek_profiler_events.py" apply "$M" > "$D/apply.log" 2>&1 || { echo "FAIL: profiler patch"; exit 1; };;
  *) echo "FAIL: variant $VAR"; exit 1;;
esac
cmake -B "$B" -S "$M" -DCMAKE_TOOLCHAIN_FILE=$M/scripts/cmake/toolchains/bare-metal-gcc.cmake -DTARGET_PLATFORM=mps4 \
  -DTARGET_SUBSYSTEM=sse-320 -DFPGA_PLATFORM_SSE_320=ON -DETHOS_U_NPU_ID=U85 -DETHOS_U_NPU_CONFIG_ID=Z1024 \
  -DETHOS_U_NPU_MEMORY_MODE=Dedicated_Sram -DETHOS_U_NPU_ENABLED=ON -DUSE_CASE_BUILD=inference_runner \
  -Dinference_runner_ACTIVATION_BUF_SZ=0x00200000 -Dinference_runner_MODEL_PATH="$VT" $FLAG > "$D/cmake.log" 2>&1 \
  || { echo "FAIL: cmake"; exit 1; }
cmake --build "$B" -j8 > "$D/build.log" 2>&1 || { echo "FAIL: build"; exit 1; }
S="$B/bin/sectors"
mkdir -p "$D/image" && cp "$S/images.txt" "$S"/inference_runner/boot.bin "$S"/inference_runner/bram.bin \
  "$S"/inference_runner/ddr.bin "$D/image/" || { echo "FAIL: image set"; exit 1; }
(cd "$D/image" && sha256sum boot.bin bram.bin ddr.bin images.txt > image.sha256)
rm -rf "$B"
echo "BUILT $NAME $VAR: $(cut -c1-12 "$D/mlek_vela.sha256") image $(cut -c1-12 "$D/image/image.sha256" | tr '\n' ' ')"
