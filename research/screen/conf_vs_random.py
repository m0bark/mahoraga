import sys, io, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
_src = (open("research/screen/confirmation_test.py", encoding="utf-8").read()
        .split('print(f"{len(d)} entries')[0])
_src = "\n".join(l for l in _src.split("\n")
                 if "sys.stdout" not in l and "TextIOWrapper" not in l)
_g = {}
exec(_src, _g)
rows = _g["rows"]
out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
d = pd.DataFrame([r for r in rows if r])
R = d[d.arm == "R random"]
print("THE COMPARISON THAT MATTERS -- each arm vs RANDOM entries, same universe\n", file=out)
print(f"{'arm':<14}{'250d excess':>13}{'vs random':>12}{'SE':>7}{'t':>7}", file=out)
for a in ["A raw_dip", "B react_sma", "C react_low", "D no_dip"]:
    S = d[d.arm == a]
    diff = S.x250.mean() - R.x250.mean()
    se = np.sqrt(S.x250.var()/len(S) + R.x250.var()/len(R))
    print(f"{a:<14}{S.x250.mean()*100:12.2f}%{diff*100:11.2f}%{se*100:6.2f}%{diff/se:+7.2f}", file=out)
print("\nSANITY CHECK vs the survivorship-free QC verdict:", file=out)
print(f"  local:  raw_dip {d[d.arm=='A raw_dip'].x250.mean()*100:+.2f}%  "
      f"vs no_dip {d[d.arm=='D no_dip'].x250.mean()*100:+.2f}%  -> dip WINS", file=out)
print("  QC PIT: dip +6.90%/yr vs no_dip +12.09%/yr           -> dip LOSES", file=out)
print("  => this local universe INVERTS the sign of the base question.", file=out)
out.flush()
