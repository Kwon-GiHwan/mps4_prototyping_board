"""H13 verify-build fix: the stock VERIFY_TEST_OUTPUT dump code in MLEK 26.03 no longer compiles against
fwk::iface::Model (returns shared_ptr<TensorIface>). Replace the two helpers INSIDE the #if VERIFY_TEST_OUTPUT
block only; stock builds (flag undefined) compile the same bytes as before. Original kept at /tmp/h13/orig."""
import re
F = "/opt/arm/ml-embedded-evaluation-kit/source/app/use_case/inference_runner/src/UseCaseHandler.cc"
s = open("/tmp/h13/orig/UseCaseHandler.cc").read()
new_block = '''#if VERIFY_TEST_OUTPUT
static void DumpInputs(fwk::iface::Model& model, const char* message)
{
    info("%s\\n", message);
    for (size_t inputIndex = 0; inputIndex < model.GetNumInputs(); inputIndex++) {
        auto t = model.GetInputTensor(inputIndex);
        arm::app::DumpTensorData(t->GetData<uint8_t>(), t->Bytes(), 16);
    }
}

static void DumpOutputs(fwk::iface::Model& model, const char* message)
{
    info("%s\\n", message);
    for (size_t outputIndex = 0; outputIndex < model.GetNumOutputs(); outputIndex++) {
        auto t = model.GetOutputTensor(outputIndex);
        arm::app::DumpTensorData(t->GetData<uint8_t>(), t->Bytes(), 16);
    }
}
#endif /* VERIFY_TEST_OUTPUT */'''
pat = re.compile(r"#if VERIFY_TEST_OUTPUT\nstatic void DumpInputs.*?#endif /\* VERIFY_TEST_OUTPUT \*/", re.S)
assert len(pat.findall(s)) == 1
open(F, "w").write(pat.sub(lambda m: new_block, s))
print("patched")

# --- UseCaseCommonUtils: drop the TfLiteTensor-based DumpTensor (declaration + definition), both inside the
# VERIFY_TEST_OUTPUT guard; DumpTensorData (uint8_t*) is all the verify build uses.
import os, shutil
K = "/opt/arm/ml-embedded-evaluation-kit/source/app/main"
for rel, pat_s in (("include/UseCaseCommonUtils.hpp",
                    r"    /\*\*\n     \* @brief       Helper function to dump a tensor to stdout.*?void DumpTensor\(const TfLiteTensor\* tensor,\n\s+size_t lineBreakForNumElements = 16\);\n\n"),
                   ("UseCaseCommonUtils.cc",
                    r"\n    void DumpTensor\(const TfLiteTensor\* tensor, const size_t lineBreakForNumElements\)\n    \{.*?\n    \}\n")):
    src = os.path.join(K, rel); keep = os.path.join("/tmp/h13/orig", os.path.basename(rel))
    if not os.path.exists(keep):
        shutil.copy(src, keep)
    text = open(keep).read()
    p = re.compile(pat_s, re.S)
    assert len(p.findall(text)) == 1, rel
    open(src, "w").write(p.sub(lambda m: "\n" if rel.endswith(".cc") else "", text))
    print("patched", rel)
