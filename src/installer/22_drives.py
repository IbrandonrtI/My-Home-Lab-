# ================================================================ drives, pools, drive names and the volumes that Homepage and FileBrowser get
def backup_mounted():
    """The backup pool (/mnt/backup) is a real mount point (a backup drive has been connected with `sudo drives`)."""
    return os.path.ismount(P("/mnt/backup")) or os.environ.get("HLS_MOUNTED_BACKUP") == "1"


DRIVE_NAMES_FILE = "/etc/homelab-drive-names"


def is_mount(path):
    """A real mount point (tests can mark folders as mounted with HLS_MOUNTED_DISKS="MAIN1 BACKUP1")."""
    return os.path.ismount(P(path)) or os.path.basename(path) in os.environ.get("HLS_MOUNTED_DISKS", "").split()


def pretty_size(nbytes):
    """Size as a drive is sold: 1 TB, 750 GB, 256 GB."""
    if nbytes >= 0.95e12:
        return "%g TB" % round(nbytes / 1e12, 1)
    if nbytes >= 1e9:
        return "%d GB" % round(nbytes / 1e9)
    return "%d MB" % round(nbytes / 1e6)


LVM_MIN_FREE = 20 * 1024 ** 3     # less unused space than this is not worth a question


def root_lvm_info():
    """When / is a logical volume (LVM) on a file system lvextend can grow: {"src", "size", "free"} in bytes, where free is the
    unused space of its volume group. None for everything else (a plain partition, no LVM tools, an unreadable answer)."""
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
    """A name that is safe as a FileBrowser folder and inside a Docker volume line."""
    text = re.sub(r"[^\w .()+,-]", " ", text.replace("_", " "))
    return re.sub(r"\s+", " ", text).strip(" .-")


def drive_name_overrides():
    """Drive names chosen in /etc/homelab-drive-names ('LABEL=Name' per line)."""
    names = {}
    for line in read_file(P(DRIVE_NAMES_FILE)).splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if clean_folder_name(v):
                names[k.strip()] = clean_folder_name(v)
    return names


def disk_device(mountpoint):
    """(partition, whole disk) behind a mount point, as /dev/ paths; empty strings when unknown."""
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
    """(model, size in bytes, file system label) of the physical drive behind a mount point; empty when unknown."""
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


# Brand names, found in the model text a drive reports (matched against the model in capitals, underscores as spaces).
# The first match wins. A drive that matches nothing keeps its model text in its name.
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
    """The maker of a drive from its model text ('TOSHIBA MQ01ABD100' -> 'Toshiba'); empty when it is not known."""
    text = re.sub(r"[_\s]+", " ", model.upper()).strip()
    for pattern, name in BRANDS:
        if re.search(pattern, text):
            return name
    return ""


def drive_kind(mountpoint, model=""):
    """'SSD', 'HDD' or 'Flash' (a USB stick) for the drive behind a mount point; empty when it cannot be told.
    The model text wins (a USB box often says 'spinning disk' for an SSD), then NVMe, then the drive's own flag."""
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
    if len(parts) > 1 and parts[1].lower() == "usb":      # a USB stick: it can be pulled out (or its model says so) and often claims to spin like a hard drive
        rc2, rm = run(["lsblk", "-dno", "RM", disk], timeout=15)
        if re.search(r"CRUZER|DATATRAVELER|FLASH|JUMPDRIVE|ULTRA FIT|STORE N GO|TRANSMEMORY|MICRO SD|CARD READER", model.upper().replace("_", " ")) or (rc2 == 0 and rm.strip().split("\n")[0].strip() == "1"):
            return "Flash"
    return {"1": "HDD", "0": "SSD"}.get(parts[0], "")


def nice_drive_name(mountpoint, model, size):
    """'1 TB Samsung HDD': the size as the drive is sold, its maker (or its model text if the maker is not known),
    and HDD or SSD when that can be told."""
    parts = [pretty_size(size) if size else "", drive_brand(model) or model, drive_kind(mountpoint, model)]
    if size and not any(parts[1:]):
        parts.append("drive")          # nothing but the size is known: "1 TB drive"
    return clean_folder_name(" ".join(p for p in parts if p))


def boot_section_size(mountpoint):
    """Size in bytes of the file behind a boot drive section (the first column of its /etc/fstab line); 0 when unknown."""
    for line in read_file(P("/etc/fstab")).splitlines():
        parts = line.split()
        if len(parts) >= 2 and not parts[0].startswith("#") and parts[1] == mountpoint:
            try:
                return os.path.getsize(P(parts[0]))
            except OSError:
                return 0
    return 0


def drive_name(mountpoint, fallback, prefer_label=False):
    """The folder name for a drive: a name you chose (/etc/homelab-drive-names), else the drive's own name
    (its file system label for the boot drive, else its size, maker and HDD or SSD, like "1 TB Samsung HDD"), else the fallback."""
    base = os.path.basename(mountpoint.rstrip("/")) or "boot"
    over = drive_name_overrides()
    if base in over:
        return over[base]
    if base.endswith("BOOT"):                        # a boot drive section: "100 GB boot drive section", from the size of its file
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
    """Mount points of the drives that are connected for a role (main or backup), as /mnt/disks/MAIN1 ..."""
    prefix = "MAIN" if role == "main" else "BACKUP"
    # real drives in order (MAIN1, MAIN2, ...); the boot drive section (MAINBOOT) is always last, like in the pool itself
    found = sorted((d[len(ROOT):] if ROOT and d.startswith(ROOT) else d
                    for d in glob.glob(P("/mnt/disks/" + prefix + "[0-9]*")) + glob.glob(P("/mnt/disks/" + prefix + "BOOT"))),
                   key=lambda d: (d.endswith("BOOT"), int(re.sub(r"\D", "", os.path.basename(d)) or 0)))
    found = [d for d in found if is_mount(d)]
    if found:
        return found
    # one plain drive mounted at the pool path (before it is converted into a pool), or the old single backup mount
    if role == "main":
        return ["/mnt/storage"] if os.path.ismount(P("/mnt/storage")) or os.environ.get("HLS_MOUNTED") == "1" else []
    return ["/mnt/backup"] if backup_mounted() else []


def fstab_pool_drives():
    """Mount points of drives that /etc/fstab already assigns to the pools (left by an earlier install): /mnt/disks/MAIN1 ..."""
    found = []
    for line in read_file(P("/etc/fstab")).splitlines():
        parts = line.split()
        if len(parts) >= 2 and not parts[0].startswith("#") and re.fullmatch(r"/mnt/disks/(MAIN|BACKUP)(\d+|BOOT)", parts[1]):
            found.append(parts[1])
    return found


def unique_names(items):
    """items: [(mount point, name)] -> the same list, with a number added to a name that more than one drive has
    ('1 TB Samsung HDD' twice becomes '1 TB Samsung HDD 1' and '1 TB Samsung HDD 2', in the order given)."""
    total, seen, out = {}, {}, []
    for _, n in items:
        total[n] = total.get(n, 0) + 1
    for mp, n in items:
        seen[n] = seen.get(n, 0) + 1
        out.append((mp, n if total[n] == 1 else "%s %d" % (n, seen[n])))
    return out


def boot_share_dir():
    """The folder on the boot drive that FileBrowser shows and that holds the stand-in backup: ~/boot-drive-files.
    A machine that already has the older ~/750GB_HDD (and not the new folder) keeps using it, so nothing there moves."""
    new, old = Ctx.home + "/boot-drive-files", Ctx.home + "/750GB_HDD"
    return old if os.path.isdir(P(old)) and not os.path.isdir(P(new)) else new


def filebrowser_mounts():
    """(host folder, folder name inside FileBrowser) for this machine: one folder, Backup-Pool, with a folder for each
    backup drive inside it, named after the drive ("1 TB Samsung HDD"). Nothing else is shown. With no backup drive
    connected there is nothing to show. A name shared by two drives of the same make gets a number, counted over
    the main and the backup drives, so it is the same name `sudo drives` shows."""
    every = [(role, mp, drive_name(mp, os.path.basename(mp))) for role in ("main", "backup") for mp in pool_drives(role)]
    named = unique_names([(mp, n) for _, mp, n in every])
    return [(mp, "/srv/Backup-Pool/" + n) for (role, _, _), (mp, n) in zip(every, named) if role == "backup"]


def filebrowser_volumes(text):
    """Replace the folder lines of FileBrowser's stack file (everything mounted under /srv) with this machine's backup drives."""
    m = re.search(r"(\n    volumes:\n)((?:      - .*(?:\n|$))+)", text)
    if not m or "/srv/Backup-Pool" not in m.group(2):
        return text          # the stack file was changed: leave it as it is
    keep = [l for l in m.group(2).splitlines() if ":/srv/" not in l]
    new = ['      - "%s:%s"' % d for d in filebrowser_mounts()] + keep
    return text[:m.start(2)] + "\n".join(new) + "\n" + text[m.end(2):]


HOMEPAGE_PARENT_LINE = "/mnt:/mnt:ro,rslave"
HOMEPAGE_PARENT_NOTE = "   # the Main and Backup Pool pills; rslave: a pool mounted later still shows"


def homepage_volumes(text):
    """Make the Homepage stack file mount the whole /mnt folder with rslave, so a pool that is mounted (or remounted) after
    Homepage started shows up inside it. A folder bound on its own (/mnt/backup) is a snapshot taken when the container was
    created: a pool mounted later is NOT in it, and the pill says 'API Error'. The single-pool lines are replaced by the parent
    line. Everything else in the file is left as it is. Returns the new text (the same text when nothing has to change)."""
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
    # no pool line at all: add the parent line after the last item of the volumes list
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
    """{mount point: file system type of the LAST mount on it} from the text of /proc/self/mountinfo."""
    types = {}
    for l in mountinfo.splitlines():
        if " - " not in l:
            continue
        head, tail = l.split(" - ", 1)
        f = head.split()
        if len(f) > 4 and tail.split():
            types[f[4].replace("\\040", " ")] = tail.split()[0]
    return types
