#!/usr/bin/env python3
"""Unit tests for the drive names FileBrowser uses (pretty_size, clean_folder_name, unique_names, the names file).
Run: python3 tests/t_names.py   (last line is OK or FAIL; nothing outside a temp folder is touched)"""
import importlib.machinery
import importlib.util
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROG = os.path.join(HERE, "..", "installer", "homelab-setup")
os.environ["HLS_FAKE"] = "1"
loader = importlib.machinery.SourceFileLoader("hls", PROG)
spec = importlib.util.spec_from_loader("hls", loader)
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)

bad = 0


def check(name, got, want):
    global bad
    ok = got == want
    bad += not ok
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else "   got %r, wanted %r" % (got, want)))


check("1 TB as sold", m.pretty_size(1000204886016), "1 TB")
check("2 TB", m.pretty_size(2000398934016), "2 TB")
check("750 GB", m.pretty_size(750156374016), "750 GB")
check("256 GB", m.pretty_size(256060514304), "256 GB")
check("just under 1 TB is still shown as GB", m.pretty_size(900e9), "900 GB")
check("underscores become spaces", m.clean_folder_name("TOSHIBA_DT01ACA100"), "TOSHIBA DT01ACA100")
check("quotes, colons, slashes and $ are removed", m.clean_folder_name("My \"drive\": a/b $HOME"), "My drive a b HOME")
check("brackets and plus are kept", m.clean_folder_name("Disk (2) +"), "Disk (2) +")
check("only odd characters leave nothing", m.clean_folder_name("///:::"), "")
check("accents are kept", m.clean_folder_name("Música"), "Música")
check("same names get a number, in the order given", m.unique_names([("/mnt/disks/MAIN1", "X"), ("/mnt/disks/MAIN2", "X"), ("/mnt/disks/MAIN3", "Y")]),
      [("/mnt/disks/MAIN1", "X 1"), ("/mnt/disks/MAIN2", "X 2"), ("/mnt/disks/MAIN3", "Y")])
check("a name that is alone gets no number", m.unique_names([("/a", "X")]), [("/a", "X")])
with tempfile.TemporaryDirectory() as d:
    m.ROOT = d
    os.makedirs(d + "/etc")
    open(d + "/etc/homelab-drive-names", "w").write("# comment\nMAIN1 = 1TB HDD\nbogus line\nBACKUP1=///\n boot = My Mint\n")
    m.P = lambda p: d + p
    check("names file: chosen names are read, empty and bad lines ignored", m.drive_name_overrides(), {"MAIN1": "1TB HDD", "boot": "My Mint"})
    m.disk_facts = lambda mp: ("MODEL X", 1000204886016, "")
    m.drive_kind = lambda mp, model="": ""
    check("a chosen name wins over the drive's own", m.drive_name("/mnt/disks/MAIN1", "fallback"), "1TB HDD")
    check("the system drive can be named with boot", m.drive_name("/", "boot-drive", prefer_label=True), "My Mint")
    check("without a chosen name and with a maker nobody knows: size and model", m.drive_name("/mnt/disks/MAIN2", "fallback"), "1 TB MODEL X")
    m.disk_facts = lambda mp: ("", 0, "Data Disk")
    check("without a model: the file system label", m.drive_name("/mnt/disks/MAIN2", "fallback"), "Data Disk")
    m.disk_facts = lambda mp: ("MODEL X", 250059350016, "Linux Mint")
    check("the system drive prefers its label", m.drive_name("/home", "boot-drive", prefer_label=True), "Linux Mint")
    check("a data drive prefers its own name over its label", m.drive_name("/mnt/disks/MAIN2", "fallback"), "250 GB MODEL X")
    m.disk_facts = lambda mp: ("MODEL X", 250059350016, "MAIN2")
    check("a generic label (MAIN2) is never used as the name", m.drive_name("/home", "boot-drive", prefer_label=True), "250 GB MODEL X")
    m.disk_facts = lambda mp: ("", 0, "")
    check("nothing known: the fallback", m.drive_name("/mnt/disks/MAIN2", "MAIN2"), "MAIN2")
# the boot drive's share folder: the new name, but a machine that already has the old ~/750GB_HDD keeps it
with tempfile.TemporaryDirectory() as d:
    m.ROOT = d
    m.P = lambda p: d + p
    m.Ctx.home = "/home/u"
    os.makedirs(d + "/home/u")
    check("share folder on a new machine", m.boot_share_dir(), "/home/u/boot-drive-files")
    os.makedirs(d + "/home/u/750GB_HDD")
    check("share folder on a machine that has the old one", m.boot_share_dir(), "/home/u/750GB_HDD")
    os.makedirs(d + "/home/u/boot-drive-files")
    check("share folder once the new one exists too", m.boot_share_dir(), "/home/u/boot-drive-files")
# the maker, found in the model text
for model, brand in [("Samsung SSD 860 EVO 250GB", "Samsung"), ("SAMSUNG_HM641JI", "Samsung"), ("TOSHIBA MQ01ABD100", "Toshiba"), ("TOSHIBA_DT01ACA100", "Toshiba"),
                     ("MQ01ABD100", "Toshiba"), ("WDC WD10EZEX-00BN5A0", "Western Digital"), ("WD10SPZX-24Z10", "Western Digital"),
                     ("ST1000LM035-1RK172", "Seagate"), ("Hitachi HTS547575A9E384", "Hitachi"), ("HTS547575A9E384", "Hitachi"),
                     ("HGST HTS721010A9E630", "HGST"), ("CT500MX500SSD1", "Crucial"), ("KINGSTON SA400S37240G", "Kingston"),
                     ("SanDisk SDSSDA240G", "SanDisk"), ("USB DISK 3.0", ""), ("External HDD", ""), ("", "")]:
    check("maker of %r" % model, m.drive_brand(model), brand)
# the whole name: size, maker, HDD or SSD
kinds = {}
m.disk_facts = lambda mp: kinds[mp][:3]
m.drive_kind = lambda mp, model="": kinds[mp][3]
kinds["/a"] = ("TOSHIBA MQ01ABD100", 1000204886016, "", "HDD")
kinds["/b"] = ("Samsung SSD 860 EVO", 250059350016, "", "SSD")
kinds["/c"] = ("USB DISK 3.0", 500107862016, "", "")
kinds["/d"] = ("WDC WD10EZEX", 0, "", "HDD")
check("size, maker and HDD", m.drive_name("/a", "x"), "1 TB Toshiba HDD")
check("size, maker and SSD", m.drive_name("/b", "x"), "250 GB Samsung SSD")
check("unknown maker and unknown type: size and the model text", m.drive_name("/c", "x"), "500 GB USB DISK 3.0")
check("unknown size is left out", m.drive_name("/d", "x"), "Western Digital HDD")
# HDD or SSD: the model text first, then NVMe, then the drive's own spinning flag (a fresh copy of the program, without the mocks above)
loader2 = importlib.machinery.SourceFileLoader("hls2", PROG)
m2 = importlib.util.module_from_spec(importlib.util.spec_from_loader("hls2", loader2))
loader2.exec_module(m2)
m2.disk_device = lambda mp: ("/dev/sda1", "/dev/sda")
answer = {}
m2.run = lambda cmd, timeout=0: (answer["rc"], answer["out"])
for model, out, want, why in [("Samsung SSD 860", "", "SSD", "SSD in the model text wins"),
                              ("Samsung_SSD_860", "", "SSD", "SSD in the model text, with underscores"),
                              ("KINGSTON SA400", "0 sata", "SSD", "not spinning"),
                              ("TOSHIBA MQ01", "1 sata", "HDD", "spinning"),
                              ("TOSHIBA MQ01", "1 usb", "HDD", "spinning, over USB"),
                              ("Foo Bar", "1 nvme", "SSD", "NVMe is always an SSD"),
                              ("Foo Bar", "0", "SSD", "not spinning, no transport shown"),
                              ("Foo Bar", "", "", "no answer: not known")]:
    answer["rc"], answer["out"] = 0, out
    check("HDD or SSD: " + why, m2.drive_kind("/x", model), want)
# FileBrowser shows only Backup-Pool, one folder per backup drive; main drives are numbered with them but not shown
m.pool_drives = lambda role: {"main": ["/mnt/disks/MAIN1"], "backup": ["/mnt/disks/BACKUP1", "/mnt/disks/BACKUP2"]}[role]
m.drive_name = lambda mp, fb, prefer_label=False: "1 TB Samsung HDD"
check("FileBrowser: only backup drives, in Backup-Pool, numbered against all pool drives", m.filebrowser_mounts(),
      [("/mnt/disks/BACKUP1", "/srv/Backup-Pool/1 TB Samsung HDD 2"), ("/mnt/disks/BACKUP2", "/srv/Backup-Pool/1 TB Samsung HDD 3")])
m.pool_drives = lambda role: {"main": ["/mnt/disks/MAIN1"], "backup": []}[role]
check("FileBrowser: no backup drive, no folder", m.filebrowser_mounts(), [])
stack = 'x\n    volumes:\n      - "/mnt/backup:/srv/Backup-Pool"\n      - filebrowser_data:/database\nvolumes:\n'
check("the stack keeps its database volume when there are no drives", m.filebrowser_volumes(stack), 'x\n    volumes:\n      - filebrowser_data:/database\nvolumes:\n')
m.drive_kind = lambda mp, model="": ""
check("nothing known but the size", m.nice_drive_name("/x", "", 2000398934016), "2 TB drive")
check("a small test image is shown in MB", m.pretty_size(62914560), "63 MB")
print("OK" if not bad else "FAIL")
sys.exit(1 if bad else 0)
