"""A fake machine for testing homelab-setup: shared state ('the world') for the fake commands and fake web services."""
import fcntl
import json
import os
import re
import secrets
import time

SIM = os.environ.get("SIM_DIR", os.path.join(os.environ.get("TMPDIR", "/tmp"), "homelab-sim"))
WORLD = SIM + "/world.json"
ROOT = os.environ.get("HLS_ROOT", SIM + "/root")

DEFAULT = {
    "pkgs": ["python3", "bash"],
    "bin": [],
    "images": [],
    "containers": {},
    "units": {"systemd-resolved": "active", "tailscaled": "inactive", "docker": "inactive", "cron": "active"},
    "enabled": {"systemd-resolved": True},
    "ts": {"logged_in": False, "approved": False, "https": False, "hostname": "", "serve": {}},
    "portainer": {"setup_token": "", "token_in_log": False, "admin": None, "pw": None, "window_closed": False, "tokens": {}, "endpoints": [], "stacks": [], "jwt": None},
    "adguard": {"configured": False},
    "immich": {"user": None, "keys": {}},
    "beszel": {"users": {}, "superusers": {}, "universal": None},
    "nc": {"calls": 0, "token": "", "conf": {}, "domains": {}},
    "speedtest": {"user": None, "tokens": []},
    "fb": {"gen": "", "user": "admin", "pw": ""},
    "users_in_docker": [],
    "usermod": [],
    "crontab": "",
    "warnings": [],
    "events": [],
    "ts_api_key": "tskey-api-VALID123",
}


class World:
    def __enter__(self):
        os.makedirs(SIM, exist_ok=True)
        self.lock = open(SIM + "/lock", "w")
        fcntl.flock(self.lock, fcntl.LOCK_EX)
        try:
            self.d = json.load(open(WORLD))
        except (OSError, ValueError):
            self.d = json.loads(json.dumps(DEFAULT))
        return self.d

    def __exit__(self, *a):
        tmp = WORLD + ".tmp"
        json.dump(self.d, open(tmp, "w"), indent=1)
        os.replace(tmp, WORLD)
        fcntl.flock(self.lock, fcntl.LOCK_UN)
        self.lock.close()


def event(w, msg):
    w["events"].append("%s %s" % (time.strftime("%H:%M:%S"), msg))


def running(w, name):
    c = w["containers"].get(name)
    return bool(c and c.get("running"))


def hostpath(p):
    return ROOT + p


# ---------------------------------------------------------------- compose handling for the fake Portainer
OLD_VALUES = ["your-tailnet", "192.168.X.X", "/home/your-username"]      # placeholders that must be replaced before deploying
SYSTEM_PREFIXES = ("/var/run/docker.sock", "/proc", "/sys", "/etc/")
SYSTEM_EXACT = {"/", "/mnt/storage", "/host"}


def interpolate_check(text, env):
    missing = []
    for m in re.finditer(r"\$\{([A-Z_][A-Z0-9_]*)(:-[^}]*)?\}", text):
        if m.group(2) is None and not env.get(m.group(1)):
            missing.append(m.group(1))
    return missing


def deploy_stack(w, name, text, env, user_msgs):
    """Pretend to be docker compose behind Portainer. Returns (ok, message)."""
    import yaml
    envd = {e["name"]: e["value"] for e in env}
    for old in OLD_VALUES:
        if old in text:
            return False, "the stack file still contains a value from the original server: %s" % old
    miss = interpolate_check(text, envd)
    if miss:
        return False, "variable(s) not set: %s" % ", ".join(sorted(set(miss)))
    doc = yaml.safe_load(text)
    for svc, cfg in (doc.get("services") or {}).items():
        cname = cfg.get("container_name") or "%s-%s-1" % (name, svc)
        if cfg.get("env_file"):
            pass
        if cfg.get("network_mode") == "host" and name == "adguard" and w["units"].get("systemd-resolved") == "active":
            return False, "failed to bind host port 0.0.0.0:53: address already in use"
        if cfg.get("network_mode") == "host" and name == "beszel-agent":
            for k in ("KEY", "TOKEN"):
                v = str((cfg.get("environment") or {}).get(k, ""))
                if not v or v in ("yours",):
                    return False, "beszel-agent %s is a placeholder" % k
        for v in cfg.get("volumes") or []:
            src = str(v).split(":")[0]
            if src.startswith("/") and not src.startswith(SYSTEM_PREFIXES) and src not in SYSTEM_EXACT:
                if not os.path.isdir(hostpath(src)):
                    w["warnings"].append("stack %s: docker would create %s root-owned" % (name, src))
        if name == "speedtest-tracker":
            ak = str((cfg.get("environment") or {}).get("APP_KEY", ""))
            if not re.fullmatch(r"base64:[A-Za-z0-9+/=]{43,44}", ak):
                return False, "APP_KEY is not a valid base64 key: %s" % ak
        mounts = [str(v).split(":")[1] for v in (cfg.get("volumes") or []) if ":" in str(v)]
        w["containers"][cname] = {"image": str(cfg.get("image")), "stack": name, "running": True, "mounts": mounts}
    if name == "filebrowser":
        w["fb"]["gen"] = w["fb"]["gen"] or secrets.token_urlsafe(12)
        w["fb"]["pw"] = w["fb"]["pw"] or w["fb"]["gen"]
    return True, "ok"
