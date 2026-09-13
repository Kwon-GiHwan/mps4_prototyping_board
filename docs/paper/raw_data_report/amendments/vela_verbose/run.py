import csv, hashlib, json, os, re, subprocess, time
ROOT = "/tmp/vela_verbose"
rows = list(csv.DictReader(open(ROOT + "/vela_matrix.csv")))
out = open(ROOT + "/results.jsonl", "a")
done = set()
if os.path.exists(ROOT + "/results.jsonl"):
    for line in open(ROOT + "/results.jsonl"):
        try: done.add(json.loads(line)["cell_id"])
        except Exception: pass
for i, r in enumerate(rows):
    args = r["vela_args"]
    m = re.search(r"--output-dir (\S+)", args)
    cell = os.path.basename(m.group(1))
    if cell in done: continue
    odir = ROOT + "/cells/" + cell
    os.makedirs(odir, exist_ok=True)
    args2 = args.replace(m.group(1), odir) + " --verbose-performance --verbose-schedule --verbose-weights"
    t0 = time.time()
    with open(odir + "/vela_stdout.txt", "w") as f:
        rc = subprocess.call("vela " + args2, shell=True, stdout=f, stderr=subprocess.STDOUT)
    art = odir + "/" + r["output_artifact"]
    sha = hashlib.sha256(open(art, "rb").read()).hexdigest() if os.path.exists(art) else None
    rec = {"cell_id": cell, "rc": rc, "sha256": sha, "frozen_sha256": r["output_sha256"],
           "match": sha == r["output_sha256"], "seconds": round(time.time() - t0, 1), "args": args2}
    out.write(json.dumps(rec) + "\n"); out.flush()
    print(i + 1, cell, "match" if rec["match"] else "MISMATCH", rec["seconds"], flush=True)
print("DONE", flush=True)
