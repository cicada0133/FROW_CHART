import os
import subprocess
import re

out_dir = "out_charts_kod"
if not os.path.exists(out_dir):
    os.makedirs(out_dir)

# Run cpp2flow
res = subprocess.run(["python", "cpp2flow.py", "kod.txt", out_dir], capture_output=True, text=True)
funcs = []
for line in res.stdout.splitlines():
    if line.startswith("Generating flowchart for "):
        func_name = line.replace("Generating flowchart for ", "").replace("...", "")
        if func_name != 'main':
            funcs.append(func_name)

# Run main_vertical
subprocess.run(["python", "main_vertical.py", "kod.txt", os.path.join(out_dir, "main.png")])
subprocess.run(["python", "main_vertical.py", "--staggered", "kod.txt", os.path.join(out_dir, "main_staggered.png")])

order_funcs = ["main"] + funcs
print("Functions in order:")
for i, f in enumerate(order_funcs, 1):
    print(f"{i}. {f}")

with open("func_order.txt", "w") as f:
    for item in order_funcs:
        f.write(item + "\n")
