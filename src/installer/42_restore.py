# ================================================================ restore from a backup (only when one is found and you said yes)
def need_email():
    """The email address given at the start, or a message saying how to give it (Immich and Beszel need one)."""
    if not Ctx.email:
        raise Abort("An email address is required. Run `sudo homelab-setup install` and answer the questions.")


def restore_choice():
    """What the person chose to restore from a backup (saved in the state file)."""
    return State.data.get("restore", {})


def find_backups():
    """Folders that look like a backup of an earlier lab (they hold main/ and boot-configs/)."""
    cands = []
    if Opt.backup:
        cands.append(Opt.backup)
    else:
        cands += [P("/mnt/backup"), P(Ctx.home + "/boot-drive-files/backup-interim"), P(Ctx.home + "/750GB_HDD/backup-interim")]
        for pat in ("/media/*/*", "/media/*/*/*", "/mnt/*", "/mnt/*/*", "/mnt/disks/*"):
            cands += glob.glob(P(pat))
    found = []
    for c in cands:
        if os.path.isdir(c + "/main") and os.path.isdir(c + "/boot-configs") and c not in found:
            found.append(c)
    return found


def dir_size_gb(path):
    """Size of a folder in gigabytes."""
    rc, txt = run(["du", "-sb", path], timeout=300)
    try:
        return int(txt.split()[0]) / 1073741824.0
    except (ValueError, IndexError):
        return 0.0


def ask_restore_plan():
    """Install-time question: restore from a backup? Returns nothing; saves the choice."""
    if "restore" in State.data:
        return
    old = fstab_pool_drives()
    if old:
        out("")
        warn("This machine already has drive(s) set up for the pools, left by an earlier install (%s). The installer never changes drives, "
             "so they stay in the pool and mount at every boot. To start with no drive in a pool, run `sudo drives release` once the install is done "
             "(the files on the drives are not touched), then choose the drives you want with `sudo drives`." % ", ".join(sorted(old)))
    State.data["restore"] = {"path": "", "configs": False, "data": False}
    if Opt.no_restore:
        State.save()
        return
    found = find_backups()
    if not found:
        out("")
        say("No backup found: every service will start empty. To restore from a backup, connect it (or pass `--backup FOLDER`) and run `sudo homelab-setup install` again before the services are deployed.")
        State.save()
        return
    path = found[0]
    out("")
    say("Backup found: %s" % path.replace(ROOT, ""))
    if len(found) > 1:
        say("(Other candidates: %s)" % ", ".join(f.replace(ROOT, "") for f in found[1:]))
    users = os.listdir(path + "/boot-configs/home") if os.path.isdir(path + "/boot-configs/home") else []
    if users and Ctx.user not in users:
        warn("The backup belongs to the user %s, but this machine's user is %s. Restoring would write into /home/%s, so the saved settings are not restored. Create a user named %s to restore them."
             % (", ".join(users), Ctx.user, users[0], users[0]))
        cfg = False
    else:
        cfg = yesno("Restore the saved settings from it (Homepage, Nextcloud app files, AdGuard Home)?", True)
    size = dir_size_gb(path + "/main")
    data = yesno("Copy your photos and files back (about %.0f GB) before the services start?" % size, True)
    State.data["restore"] = {"path": path, "configs": cfg, "data": data}
    State.save()


@step
class RestoreConfigs(Step):
    id, group, title = "restore-configs", "Platform", "Saved settings restored from your backup"
    needs = ("folders",)

    def applies(self):
        return bool(restore_choice().get("configs"))

    def probe(self):
        return "done" if State.ran("restore-configs") else "todo"

    def run(self):
        path = restore_choice()["path"]
        tool = repo_file("scripts", "homelab-restore-configs")
        if not os.path.exists(tool):
            raise Abort("homelab-restore-configs is missing from the repository copy.")
        if Opt.dry:
            out("      would run the safe restore tool on %s (it shows a preview and asks you to type RESTORE)" % path)
            return
        env = dict(os.environ)
        if ROOT:
            env["HRC_ROOT"] = ROOT                      # tests only: restore into the fake root
        with Live.pause():
            rc = subprocess.run(["bash", tool, path], env=env).returncode
        if rc != 0:
            raise Abort("The restore tool stopped (code %s). Nothing was deleted. Run `sudo homelab-setup refresh` to try again." % rc)
        State.mark("restore-configs")


def has_user_files(folder):
    """True when the folder holds any file besides Immich's empty `.immich` marker files (the installer makes those itself when no drive is mounted)."""
    for _dir, _subs, files in os.walk(folder):
        if any(f != ".immich" for f in files):
            return True
    return False


@step
class RestoreData(Step):
    id, group, title = "restore-data", "Platform", "Photos and files copied back from your backup"
    needs = ("folders", "restore-configs")

    def applies(self):
        return bool(restore_choice().get("data"))

    def probe(self):
        return "done" if State.ran("restore-data") else "todo"

    def run(self):
        path = restore_choice()["path"] + "/main/"
        dest = P("/mnt/storage/")
        for sub in ("immich", "nextcloud"):
            d = dest + sub
            if has_user_files(d):
                raise Abort("%s already contains files and will not be overwritten. Move them away or skip the restore." % d.replace(ROOT, ""))
        size = dir_size_gb(path)
        free = shutil.disk_usage(dest).free / 1073741824.0
        if free < size + 5:
            raise Abort("Not enough space: the backup is %.0f GB and only %.0f GB is free at /mnt/storage." % (size, free))
        if Opt.dry:
            out("      would copy %.0f GB from %s to /mnt/storage with rsync" % (size, path))
            return
        out("      copying %.0f GB (this can take a long time; you can leave it running) ..." % size)
        with Live.pause():
            rc = subprocess.run(["rsync", "-aH", "--numeric-ids", "--info=progress2", "--exclude=/lost+found", path, dest]).returncode
        if rc not in (0, 24):
            raise Abort("rsync stopped with code %s. Run `sudo homelab-setup refresh` to continue where it stopped." % rc)
        State.mark("restore-data")


def immich_restored():
    """True when data was restored from a backup and Immich's own database dumps are present."""
    return bool(restore_choice().get("data")) and bool(glob.glob(P("/mnt/storage/immich/backups/*")))
