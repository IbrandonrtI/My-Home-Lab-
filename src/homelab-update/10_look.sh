if [ -t 1 ] && [ -z "${NO_COLOR:-}" ] && [ "${TERM:-dumb}" != "dumb" ]; then
  B=$'\033[1m'; D=$'\033[2m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; C=$'\033[36m'; N=$'\033[0m'
else
  B=""; D=""; G=""; Y=""; R=""; C=""; N=""
fi
case "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" in
  *[Uu][Tt][Ff]-8*|*[Uu][Tt][Ff]8*) S_OK="✓"; S_UP="↑"; S_DL="↓"; S_PEND="●"; S_BAD="✗"; S_WARN="!"; S_DOT="·"; S_ARR="→"; S_RULE="─" ;;
  *)                                S_OK="+"; S_UP="^"; S_DL="v"; S_PEND="*"; S_BAD="x"; S_WARN="!"; S_DOT="-"; S_ARR="->"; S_RULE="-" ;;
esac

rule() {
  local w t="$1" n pad
  w=$(term_cols); [ "$w" -gt 76 ] && w=76
  n=$(( w - ${#t} - 8 )); [ "$n" -lt 3 ] && n=3
  pad=$(printf '%*s' "$n" '' | sed "s/ /$S_RULE/g")
  printf '\n  %s%s%s%s %s%s%s %s%s%s\n\n' "$D" "$S_RULE" "$S_RULE" "$N" "$B" "$t" "$N" "$D" "$pad" "$N"
}
line_ok()   { printf '   %s%s%s  %s\n' "$G" "$S_OK" "$N" "$*"; }
line_warn() { printf '   %s%s%s  %s\n' "$Y" "$S_WARN" "$N" "$*"; }
line_bad()  { printf '   %s%s%s  %s\n' "$R" "$S_BAD" "$N" "$*"; }
line_note() { printf '   %s%s  %s%s\n' "$D" "$S_DOT" "$*" "$N"; }
img_row()   { printf '   %s%s%s  %-18s %s%-32s%s %s\n' "$1" "$2" "$N" "$3" "$D" "$4" "$N" "$5"; }
term_cols() { local c; c=$(tput cols 2>/dev/null) || c=80; [[ "$c" =~ ^[0-9]+$ ]] || c=80; [ "$c" -lt 40 ] && c=40; echo "$c"; }
kv() {
  local k=$1 first=1 l w
  w=$(( $(term_cols) - 16 )); [ "$w" -gt 90 ] && w=90
  [ "$k" = image ] && w=500
  while IFS= read -r l; do
    if [ "$first" -eq 1 ]; then printf '      %s%-9s%s %s\n' "$D" "$k" "$N" "$l"; first=0
    else printf '      %9s %s\n' "" "$l"; fi
  done < <(printf '%s\n' "$2" | fold -s -w "$w")
}
hb()        { numfmt --to=iec --suffix=B "$1" 2>/dev/null || echo "$1 B"; }

read -r -d '' PYLIB <<'PY' || true
import json, os, re, sys, urllib.error, urllib.parse, urllib.request


def split_ref(ref):
    """'ghcr.io/gethomepage/homepage:v2.6.0' -> (registry host, repository, tag)."""
    first, _, rest = ref.partition("/")
    if rest and ("." in first or ":" in first or first == "localhost"):
        host, path = first, rest
    else:
        host, path = "docker.io", ref
    name, _, tag = path.rpartition(":") if ":" in path.split("/")[-1] else (path, "", "")
    if host == "docker.io":
        host = "registry-1.docker.io"
        if "/" not in name:
            name = "library/" + name
    elif host == "lscr.io":
        host = "ghcr.io"
    return host, name, tag


def fetch(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), r.headers


def registry_get(base, path, auth=None):
    """GET from a registry; follows the token login that registries ask for."""
    url = base + path
    hdr = {"Accept": "application/json"}
    if auth:
        hdr["Authorization"] = "Bearer " + auth
    try:
        return fetch(url, hdr), auth
    except urllib.error.HTTPError as e:
        if e.code != 401 or auth:
            raise
        ch = e.headers.get("WWW-Authenticate", "")
        realm = re.search(r'realm="([^"]+)"', ch)
        if not realm:
            raise
        q = {k: v for k, v in re.findall(r'(service|scope)="([^"]+)"', ch)}
        tok, _ = fetch(realm.group(1) + "?" + urllib.parse.urlencode(q))
        js = json.loads(tok)
        token = js.get("token") or js.get("access_token")
        return registry_get(base, path, token)


def all_tags(ref):
    host, name, _ = split_ref(ref)
    base = os.environ.get("HLU_REGISTRY_BASE") or "https://" + host
    path, tags, token = "/v2/%s/tags/list?n=1000" % name, [], None
    for _ in range(40):
        (body, hdrs), token = registry_get(base, path, token)
        tags += json.loads(body).get("tags") or []
        nxt = re.search(r'<([^>]+)>;\s*rel="next"', hdrs.get("Link", "") or "")
        if not nxt:
            break
        path = nxt.group(1)
        if path.startswith("http"):
            path = "/" + path.split("/", 3)[3]
    return tags


def newer_tag(ref):
    """The highest tag that has the same shape as the running one (v2.6.0 -> v2.7.0) and is newer, or ''."""
    _, _, cur = split_ref(ref)
    m = re.fullmatch(r"(v?)(\d+(?:\.\d+)+)", cur)
    if not m:
        return ""
    pre, nums = m.group(1), tuple(int(x) for x in m.group(2).split("."))
    best = nums
    best_tag = ""
    for t in all_tags(ref):
        mt = re.fullmatch(r"(v?)(\d+(?:\.\d+)+)", t)
        if not mt or mt.group(1) != pre:
            continue
        v = tuple(int(x) for x in mt.group(2).split("."))
        if len(v) == len(nums) and v > best:
            best, best_tag = v, t
    return best_tag


