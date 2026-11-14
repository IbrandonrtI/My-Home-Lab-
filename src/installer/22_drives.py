def backup_mounted():
    return os.path.ismount(P("/mnt/backup")) or os.environ.get("HLS_MOUNTED_BACKUP") == "1"


DRIVE_NAMES_FILE = "/etc/homelab-drive-names"


def is_mount(path):
    return os.path.ismount(P(path)) or os.path.basename(path) in os.environ.get("HLS_MOUNTED_DISKS", "").split()


def pretty_size(nbytes):
    if nbytes >= 0.95e12:
        return "%g TB" % round(nbytes / 1e12, 1)
    if nbytes >= 1e9:
        return "%d GB" % round(nbytes / 1e9)
    return "%d MB" % round(nbytes / 1e6)


LVM_MIN_FREE = 20 * 1024 ** 3


def root_lvm_info():
    """If / is an LVM logical volume that can be grown, return its source, size and the free space of its volume group; otherwise None."""
    if not (have("lvs") and have("lvextend")):
        return None
    rc, text = run(["findmnt", "-no", "SOURCE,FSTYPE", "/"], timeout=10)
    parts = text.split()
    if rc != 0 or not parts or not parts[0].startswith("/dev/"):
        return None
    src, fstype = parts[0], (parts[1] if len(parts) > 1 else "")
    if fstype and fstype not in ("ext2", "ext3", "ext4", "xfs"):
        return None
    rc, text = run(["lvs", "--noheadings", "--nosuffix", "--units", "b", "--separator", "|", "-o", "lv_size,vg_free", src], timeout=20)
    if rc != 0:
        return None
    for line in text.splitlines():
        f = [x.strip() for x in line.split("|")]
        if len(f) == 2:
            try:
                return {"src": src, "size": int(float(f[0])), "free": int(float(f[1]))}
            except ValueError:
                return None
    return None


def clean_folder_name(text):
    text = re.sub(r"[^\w .()+,-]", " ", text.replace("_", " "))
    return re.sub(r"\s+", " ", text).strip(" .-")


def drive_name_overrides():
    names = {}
    for line in read_file(P(DRIVE_NAMES_FILE)).splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if clean_folder_name(v):
                names[k.strip()] = clean_folder_name(v)
    return names


def disk_device(mountpoint):
    rc, src = run(["findmnt", "-n", "-o", "SOURCE", "--target", mountpoint], timeout=15)
    src = src.strip().splitlines()[0].strip() if rc == 0 and src.strip() else ""
    if not src.startswith("/dev/"):
        return "", ""
    disk = ""
    rc, txt = run(["lsblk", "-nslo", "NAME,TYPE", src], timeout=15)
    for line in txt.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == "disk":
            disk = "/dev/" + parts[0]
            break
    return src, disk


def disk_facts(mountpoint):
    src, disk = disk_device(mountpoint)
    if not src:
        return "", 0, ""
    label = run(["lsblk", "-no", "LABEL", src], timeout=15)[1].strip().splitlines()
    label = label[0].strip() if label else ""
    model, size = "", 0
    if disk:
        rc, txt = run(["lsblk", "-dnbo", "MODEL,SIZE", disk], timeout=15)
        line = txt.strip().splitlines()[0].strip() if rc == 0 and txt.strip() else ""
        m = re.match(r"^(.*?)\s*(\d+)$", line)
        if m:
            model, size = m.group(1).strip(), int(m.group(2))
    return model, size, label


BRANDS = [
    (r"SAMSUNG|^MZ[- ]?\w|^HM\d{3}|^HN-M", "Samsung"),
    (r"TOSHIBA|^MQ0\d|^DT0\d|^HDW|^MK\d{4}|^MG0\d|^KBG|^KXG", "Toshiba"),
    (r"WESTERN DIGITAL|^WDC|^WD ?\d|^WDS", "Western Digital"),
    (r"HGST|^HU[SH]", "HGST"),
    (r"HITACHI|^HT[ES]\d|^HDS", "Hitachi"),
    (r"SEAGATE|^ST\d{3,}[A-Z]{2}", "Seagate"),
    (r"CRUCIAL|^CT\d{2,}", "Crucial"),
    (r"KINGSTON|^SA400|^SKC|^SNV|^SUV|^SV300", "Kingston"),
    (r"SANDISK|^SDSSD|^SD[A-Z]{2}\d", "SanDisk"),
    (r"INTEL|^SSDSC|^SSDPE", "Intel"),
    (r"MICRON|^MTFD", "Micron"),
    (r"ADATA|^SU\d{3}", "ADATA"),
    (r"LEXAR", "Lexar"),
    (r"CORSAIR", "Corsair"),
    (r"SABRENT", "Sabrent"),
    (r"PATRIOT", "Patriot"),
    (r"PLEXTOR", "Plextor"),
    (r"KIOXIA", "Kioxia"),
    (r"TRANSCEND", "Transcend"),
    (r"LITE-?ON", "Lite-On"),
    (r"SK ?HYNIX", "SK hynix"),
    (r"MAXTOR", "Maxtor"),
    (r"FUJITSU", "Fujitsu"),
    (r"\bPNY\b", "PNY"),
    (r"TEAM ?GROUP|^TEAM ", "TeamGroup"),
]


def drive_brand(model):
    text = re.sub(r"[_\s]+", " ", model.upper()).strip()
    for pattern, name in BRANDS:
        if re.search(pattern, text):
            return name
    return ""


def drive_kind(mountpoint, model=""):
    if re.search(r"\bSSD\b|NVME", model.upper().replace("_", " ")):
        return "SSD"
    disk = disk_device(mountpoint)[1]
    if not disk:
        return ""
    rc, txt = run(["lsblk", "-dnbo", "ROTA,TRAN", disk], timeout=15)
    parts = txt.split() if rc == 0 else []
    if not parts:
        return ""
    if len(parts) > 1 and parts[1].lower() == "nvme":
        return "SSD"
    if len(parts) > 1 and parts[1].lower() == "usb":
        rc2, rm = run(["lsblk", "-dno", "RM", disk], timeout=15)
        if re.search(r"CRUZER|DATATRAVELER|FLASH|JUMPDRIVE|ULTRA FIT|STORE N GO|TRANSMEMORY|MICRO SD|CARD READER", model.upper().replace("_", " ")) or (rc2 == 0 and rm.strip().split("\n")[0].strip() == "1"):
            return "Flash"
    return {"1": "HDD", "0": "SSD"}.get(parts[0], "")


def nice_drive_name(mountpoint, model, size):
    parts = [pretty_size(size) if size else "", drive_brand(model) or model, drive_kind(mountpoint, model)]
    if size and not any(parts[1:]):
        parts.append("drive")
    return clean_folder_name(" ".join(p for p in parts if p))


def boot_section_size(mountpoint):
    for line in read_file(P("/etc/fstab")).splitlines():
        parts = line.split()
        if len(parts) >= 2 and not parts[0].startswith("#") and parts[1] == mountpoint:
            try:
                return os.path.getsize(P(parts[0]))
            except OSError:
                return 0
    return 0


def drive_name(mountpoint, fallback, prefer_label=False):
    """Folder name for a drive: the name the user chose, otherwise its label or a size-and-model name such as "1 TB Samsung HDD", otherwise the fallback."""
    base = os.path.basename(mountpoint.rstrip("/")) or "boot"
    over = drive_name_overrides()
    if base in over:
        return over[base]
    if base.endswith("BOOT"):
        size = boot_section_size(mountpoint)
        return "%s boot drive section" % pretty_size(size) if size else "boot drive section"
    model, size, label = disk_facts(mountpoint)
    generic = re.fullmatch(r"(MAIN|BACKUP)\d*", label or "")
    if prefer_label and label and not generic and clean_folder_name(label):
        return clean_folder_name(label)
    if model or size:
        name = nice_drive_name(mountpoint, model, size)
        if name:
            return name
    if label and not generic and clean_folder_name(label):
        return clean_folder_name(label)
    return fallback


def pool_drives(role):
    prefix = "MAIN" if role == "main" else "BACKUP"
    found = sorted((d[len(ROOT):] if ROOT and d.startswith(ROOT) else d
                    for d in glob.glob(P("/mnt/disks/" + prefix + "[0-9]*")) + glob.glob(P("/mnt/disks/" + prefix + "BOOT"))),
                   key=lambda d: (d.endswith("BOOT"), int(re.sub(r"\D", "", os.path.basename(d)) or 0)))
    found = [d for d in found if is_mount(d)]
    if found:
        return found
    if role == "main":
        return ["/mnt/storage"] if os.path.ismount(P("/mnt/storage")) or os.environ.get("HLS_MOUNTED") == "1" else []
    return ["/mnt/backup"] if backup_mounted() else []


def fstab_pool_drives():
    found = []
    for line in read_file(P("/etc/fstab")).splitlines():
        parts = line.split()
        if len(parts) >= 2 and not parts[0].startswith("#") and re.fullmatch(r"/mnt/disks/(MAIN|BACKUP)(\d+|BOOT)", parts[1]):
            found.append(parts[1])
    return found


def unique_names(items):
    total, seen, out = {}, {}, []
    for _, n in items:
        total[n] = total.get(n, 0) + 1
    for mp, n in items:
        seen[n] = seen.get(n, 0) + 1
        out.append((mp, n if total[n] == 1 else "%s %d" % (n, seen[n])))
    return out


def boot_share_dir():
    new, old = Ctx.home + "/boot-drive-files", Ctx.home + "/750GB_HDD"
    return old if os.path.isdir(P(old)) and not os.path.isdir(P(new)) else new


def filebrowser_mounts():
    every = [(role, mp, drive_name(mp, os.path.basename(mp))) for role in ("main", "backup") for mp in pool_drives(role)]
    named = unique_names([(mp, n) for _, mp, n in every])
    return [(mp, "/srv/Backup-Pool/" + n) for (role, _, _), (mp, n) in zip(every, named) if role == "backup"]


def filebrowser_volumes(text):
    m = re.search(r"(\n    volumes:\n)((?:      - .*(?:\n|$))+)", text)
    if not m or "/srv/Backup-Pool" not in m.group(2):
        return text
    keep = [l for l in m.group(2).splitlines() if ":/srv/" not in l]
    new = ['      - "%s:%s"' % d for d in filebrowser_mounts()] + keep
    return text[:m.start(2)] + "\n".join(new) + "\n" + text[m.end(2):]


HOMEPAGE_PARENT_LINE = "/mnt:/mnt:ro,rslave"
HOMEPAGE_PARENT_NOTE = "   # the Main and Backup Pool pills; rslave: a pool mounted later still shows"


def homepage_volumes(text):
    """Make the Homepage stack mount the whole /mnt folder with rslave, so pools mounted after Homepage started are still visible inside it."""
    lines = text.split("\n")
    item = re.compile(r"^(\s*)-\s*(['\"]?)(/[^\s:'\"]*):(/[^\s:'\"]*)((?::[^\s'\"#]*)?)\2\s*(#.*)?$")
    single = [i for i, l in enumerate(lines)
              if (m := item.match(l)) and m.group(3) in ("/mnt/storage", "/mnt/backup") and m.group(4) == m.group(3)]
    parent = [i for i, l in enumerate(lines) if (m := item.match(l)) and m.group(3) == "/mnt" and m.group(4) == "/mnt"]
    if parent:
        m = item.match(lines[parent[0]])
        opts = m.group(5)
        if "rslave" in opts or "rshared" in opts:
            if not single:
                return text
        else:
            mode = "rw" if re.search(r"(^|[:,])rw($|,)", opts) else "ro"
            note = ("   " + m.group(6)) if m.group(6) else ""
            lines[parent[0]] = "%s- /mnt:/mnt:%s,rslave%s" % (m.group(1), mode, note)
        for i in reversed(single):
            del lines[i]
        return "\n".join(lines)
    if single:
        indent = item.match(lines[single[0]]).group(1)
        for i in reversed(single[1:]):
            del lines[i]
        lines[single[0]] = "%s- %s%s" % (indent, HOMEPAGE_PARENT_LINE, HOMEPAGE_PARENT_NOTE)
        return "\n".join(lines)
    for n, l in enumerate(lines):
        if re.match(r"^\s*volumes:\s*$", l):
            j = n + 1
            last = None
            while j < len(lines) and (lines[j].strip() == "" or lines[j].lstrip().startswith(("-", "#"))):
                if lines[j].lstrip().startswith("-"):
                    last = j
                j += 1
            if last is None:
                return text
            indent = re.match(r"^(\s*)", lines[last]).group(1)
            lines.insert(last + 1, "%s- %s%s" % (indent, HOMEPAGE_PARENT_LINE, HOMEPAGE_PARENT_NOTE))
            return "\n".join(lines)
    return text


def mount_types(mountinfo):
    types = {}
    for l in mountinfo.splitlines():
        if " - " not in l:
            continue
        head, tail = l.split(" - ", 1)
        f = head.split()
        if len(f) > 4 and tail.split():
            types[f[4].replace("\\040", " ")] = tail.split()[0]
    return types
