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
check("same names get the mount name added", m.unique_names([("/mnt/disks/MAIN1", "X"), ("/mnt/disks/MAIN2", "X"), ("/mnt/disks/MAIN3", "Y")]),
      [("/mnt/disks/MAIN1", "X (MAIN1)"), ("/mnt/disks/MAIN2", "X (MAIN2)"), ("/mnt/disks/MAIN3", "Y")])
with tempfile.TemporaryDirectory() as d:
    m.ROOT = d
    os.makedirs(d + "/etc")
    open(d + "/etc/homelab-drive-names", "w").write("# comment\nMAIN1 = 1TB HDD\nbogus line\nBACKUP1=///\n boot = My Mint\n")
    m.P = lambda p: d + p
    check("names file: chosen names are read, empty and bad lines ignored", m.drive_name_overrides(), {"MAIN1": "1TB HDD", "boot": "My Mint"})
    m.disk_facts = lambda mp: ("MODEL X", 1000204886016, "")
    check("a chosen name wins over the drive's own", m.drive_name("/mnt/disks/MAIN1", "fallback"), "1TB HDD")
    check("the system drive can be named with boot", m.drive_name("/", "boot-drive", prefer_label=True), "My Mint")
    check("without a chosen name: model and size", m.drive_name("/mnt/disks/MAIN2", "fallback"), "MODEL X 1 TB")
    m.disk_facts = lambda mp: ("", 0, "Data Disk")
    check("without a model: the file system label", m.drive_name("/mnt/disks/MAIN2", "fallback"), "Data Disk")
    m.disk_facts = lambda mp: ("MODEL X", 250059350016, "Linux Mint")
    check("the system drive prefers its label", m.drive_name("/home", "boot-drive", prefer_label=True), "Linux Mint")
    check("a data drive prefers model and size over its label", m.drive_name("/mnt/disks/MAIN2", "fallback"), "MODEL X 250 GB")
    m.disk_facts = lambda mp: ("MODEL X", 250059350016, "MAIN2")
    check("a generic label (MAIN2) is never used as the name", m.drive_name("/home", "boot-drive", prefer_label=True), "MODEL X 250 GB")
    m.disk_facts = lambda mp: ("", 0, "")
    check("nothing known: the fallback", m.drive_name("/mnt/disks/MAIN2", "MAIN2"), "MAIN2")
print("OK" if not bad else "FAIL")
sys.exit(1 if bad else 0)
