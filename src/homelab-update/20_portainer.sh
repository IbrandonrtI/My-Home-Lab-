# ---------------------------------------------------------------- Portainer
def pt_token():
    path = os.environ.get("HLU_SECRETS") or "/root/.homelab-setup/secrets.env"
    try:
        for line in open(path):
            if line.startswith("PORTAINER_TOKEN="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def pt(method, path, body=None):
    base = os.environ.get("HLU_PORTAINER") or "http://127.0.0.1:9000"
    key = pt_token()
    if not key:
        raise RuntimeError("no Portainer key is saved on this server")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"X-API-Key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.loads(e.read()).get("details", "")
        except Exception:
            pass
        raise RuntimeError("Portainer answered HTTP %d %s" % (e.code, detail))
    except urllib.error.URLError as e:
        raise RuntimeError("cannot reach Portainer (%s)" % e.reason)


def find_stack(name):
    for s in pt("GET", "/api/stacks"):
        if s.get("Name") == name:
            return s
    return None


def stack_update(name, pairs):
    """Change image names in the saved stack file (pairs of OLD NEW) and redeploy it, like 'Update the stack'."""
    s = find_stack(name)
    if not s:
        raise RuntimeError("Portainer has no stack named '%s'" % name)
    sid, eid = s["Id"], s.get("EndpointId") or 1
    text = pt("GET", "/api/stacks/%s/file?endpointId=%s" % (sid, eid)).get("StackFileContent", "")
    if not text:
        raise RuntimeError("could not read the stack file of '%s'" % name)
    for old, new in pairs:
        if old != new:
            if old not in text:
                raise RuntimeError("the stack file does not contain '%s' (it may use a variable), so its version cannot be changed here" % old)
            text = text.replace(old, new)
    env = [{"name": e["name"], "value": e["value"]} for e in (s.get("Env") or [])]
    pt("PUT", "/api/stacks/%s?endpointId=%s" % (sid, eid),
       {"stackFileContent": text, "env": env, "prune": False, "pullImage": False})


def main(a):
    cmd = a[0]
    try:
        if cmd == "tags":
            print(newer_tag(a[1]))
        elif cmd == "pt-has":
            print("yes" if find_stack(a[1]) else "no")
        elif cmd == "pt-update":
            pairs = [(a[i], a[i + 1]) for i in range(2, len(a) - 1, 2)]
            stack_update(a[1], pairs)
        else:
            return 2
    except (RuntimeError, urllib.error.URLError, OSError, ValueError, KeyError) as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


sys.exit(main(sys.argv[1:]))
PY
pylib() { python3 -c "$PYLIB" "$@"; }

STATE_FILE="$STATE_DIR/image-state"
SUMMARY_FILE="$STATE_DIR/image-updates"
ATTEMPT_FILE="$STATE_DIR/image-check-attempt"

die() { echo "$*" >&2; exit 1; }

need_root() { [ "$(id -u)" -eq 0 ] || die "Run it with sudo: sudo homelab-update ${1:-}"; }

take_lock() {   # take_lock quiet|loud
  mkdir -p "$(dirname "$LOCKFILE")" 2>/dev/null
  exec 9>"$LOCKFILE" || die "Cannot open $LOCKFILE"
  if ! flock -n 9; then
    [ "$1" = quiet ] && exit 0
    die "Another homelab-update is running right now. Wait for it to finish, then try again."
  fi
}

put() {   # put NAME  (content on stdin): write atomically, readable by everyone
  local tmp
  mkdir -p "$STATE_DIR" && chmod 755 "$STATE_DIR" 2>/dev/null
  tmp=$(mktemp "$STATE_DIR/.tmp.XXXXXX") || return 1
  cat >"$tmp" && chmod 644 "$tmp" && mv -f "$tmp" "$STATE_DIR/$1"
}

