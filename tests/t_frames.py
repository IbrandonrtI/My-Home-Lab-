# Prints the longest progress-bar text (visible characters) found in a saved terminal capture, how many were
# painted, and the row they were painted on.
import re, sys
raw = open(sys.argv[1], "rb").read().decode("utf-8", "replace")
found = re.findall(r"\x1b\[(\d+);1H\x1b\[\?7l(.*?)\x1b\[K", raw)
texts = [re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", t) for _, t in found if re.search(r"\d+ of \d+", t)]
rows = sorted({r for r, t in found})
print(max((len(t) for t in texts), default=0), len(texts), ",".join(rows))
