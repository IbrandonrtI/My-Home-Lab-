# subst() turns the repository's placeholders into this machine's values, and (only when HOMELAB_OLD_* are set)
# the values of an earlier server too. An empty "old value" must never match anything.
import os
os.environ["HOMELAB_OLD_USER"] = "olduser"
os.environ["HOMELAB_OLD_LAN"] = "10.9.8.7"
os.environ["HOMELAB_OLD_FQDN"] = "pc.old-net.ts.net"
prog = os.environ.get("HLS_PROG", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "installer", "homelab-setup"))
src = open(prog).read().replace('if __name__ == "__main__":', "if False:")
ns = {}
exec(compile(src, "hs", "exec"), ns)
Ctx, subst = ns["Ctx"], ns["subst"]
Ctx.fqdn, Ctx.tailnet, Ctx.lan, Ctx.home = "pc.new-net.ts.net", "new-net.ts.net", "192.168.77.5", "/home/newuser"
problems = []
text = ("a: 192.168.X.X b: pc.your-tailnet.ts.net c: /home/your-username/x d: 10.9.8.7 e: pc.old-net.ts.net "
        "f: old-net.ts.net g: /home/olduser/y h: PUID: \"123\"")
got = subst(text)
for want in ("a: 192.168.77.5", "b: pc.new-net.ts.net", "c: /home/newuser/x", "d: 192.168.77.5", "e: pc.new-net.ts.net",
             "f: new-net.ts.net", "g: /home/newuser/y"):
    if want not in got:
        problems.append("missing %r in %r" % (want, got))
# with nothing set, only the placeholders change and "/home/" alone is never rewritten
ns["OLD_USER"] = ns["OLD_LAN"] = ns["OLD_FQDN"] = ns["OLD_TAILNET"] = ""
got2 = subst("x /home/ y 10.9.8.7 z /home/olduser/q 192.168.X.X")
if got2 != "x /home/ y 10.9.8.7 z /home/olduser/q 192.168.77.5":
    problems.append("empty old values changed the text: %r" % got2)
print("OK" if not problems else "FAIL: " + "; ".join(problems))
