"""Count FWD weight-format commands and IFM2-as-weights convs in a model's Vela cms.

Runs in the benchmark-runner container with /tmp/pack_vela_workload.py present.
Uses the packer's Vela options -- FWD selection depends on them.
"""
import sys, struct, subprocess, tempfile, os, glob
sys.path.insert(0, "/tmp"); import pack_vela_workload as p
for model in sys.argv[1:]:
    d = tempfile.mkdtemp()
    subprocess.run(["vela", model, "--accelerator-config", "ethos-u85-1024", "--system-config", "Ethos_U85_SYS_DRAM_Low", "--memory-mode", "Dedicated_Sram", "--output-dir", d],
                   check=True, capture_output=True)
    info = p.inspect_vela(glob.glob(d + "/*_vela.tflite")[0])
    cms = info["cms"]; w = struct.unpack("<%dI" % (len(cms) // 4), cms); i = 0
    c = {"conv": 0, "conv_ifm2w": 0, "dw": 0, "fwd": 0, "swd": 0}
    while i < len(w):
        x = w[i]; op = x & 0x3FF; cmd1 = (x >> 14) & 1
        if not cmd1:
            if op == 2: c["conv_ifm2w" if (x >> 16) & 1 else "conv"] += 1
            elif op == 3: c["dw"] += 1
            elif op == 302: c["fwd" if (x >> 16) & 1 else "swd"] += 1
        i += 2 if cmd1 else 1
    print(os.path.basename(model), c)
