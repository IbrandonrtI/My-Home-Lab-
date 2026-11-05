# ================================================================ the command line
def main(argv):
    """Read the command line and run the command."""
    try:
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except (AttributeError, ValueError):
        pass
    args = list(argv[1:])
    i = 0
    cmd = None
    pos = []
    while i < len(args):
        a = args[i]
        if a in ("--dry-run", "-n"):
            Opt.dry = True
        elif a in ("--yes", "-y"):
            Opt.yes = True
        elif a == "--no-restore":
            Opt.no_restore = True
        elif a == "--force-existing":
            Opt.force_existing = True
        elif a == "--backup" and i + 1 < len(args):
            i += 1
            Opt.backup = args[i]
        elif a == "--repo" and i + 1 < len(args):
            i += 1
            Opt.repo = args[i]
        elif a in ("-h", "--help", "help"):
            out(HELP % VERSION)
            return 0
        elif a in ("--version", "version"):
            out("homelab-setup " + VERSION)
            return 0
        elif a == "--quiet":
            pass
        elif a in ("--all", "-a"):
            Opt.all = True
        elif a in ("--details", "-d"):
            Opt.details = True
        elif a.startswith("-"):
            out("Unknown option %s. Try: homelab-setup help" % a)
            return 1
        else:
            pos.append(a)
        i += 1
    cmd = pos[0] if pos else "checklist"
    if cmd not in COMMANDS and cmd not in ("done", "skip", "cards"):
        out("Unknown command '%s'. Try: homelab-setup help" % cmd)
        return 1
    ensure_root()
    try:
        if cmd in ("done", "skip"):
            if len(pos) < 2:
                out("Which step? Example: homelab-setup %s reboot-test" % cmd)
                return 1
            cmd_mark("ack" if cmd == "done" else "skip", pos[1])
        elif cmd == "cards":
            return cmd_cards(pos[1:])
        else:
            COMMANDS[cmd]()
    except Abort as e:
        Live.close()
        out("")
        bad(str(e))
        return 1
    except KeyboardInterrupt:
        Live.close()
        out("")
        say("Stopped. Finished steps stay finished; run the same command again to continue.")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
