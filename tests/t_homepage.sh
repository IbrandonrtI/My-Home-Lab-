#!/bin/bash
# Tests for "homelab theme" and "homelab bookmark" (scripts/homelab) in a temporary copy of the Homepage files.
# A small local web server plays Brandfetch. Nothing on this machine is touched. Last line: OK or FAIL.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
H="$REPO/scripts/homelab"
T="$(mktemp -d)"; PASS=0; FAIL=0
trap 'kill $SRV 2>/dev/null; rm -rf "$T"' EXIT
check(){ if ( eval "$2" ); then PASS=$((PASS+1)); else echo "FAIL  $1"; FAIL=$((FAIL+1)); fi; }

mkdir -p "$T/hp" "$T/www/example.com/theme/dark" "$T/www/plain.test/theme/dark" "$T/www/png.test/theme/dark" "$T/www/jpeg.test/theme/dark" "$T/www/both.test/theme/dark"
cp "$REPO"/homepage-config/* "$T/hp/"
SVG='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4" fill="red"/></svg>'
printf '%s%*s' "$SVG" 120 '' >"$T/www/example.com/theme/dark/symbol.svg"
printf 'not a picture, just a web page that says sorry %*s' 150 '' >"$T/www/plain.test/theme/dark/symbol.svg"
printf '\x89PNG\r\n\x1a\n%*s' 200 '' >"$T/www/png.test/theme/dark/logo.png"
printf '\xff\xd8\xff\xe0%*s' 200 '' >"$T/www/jpeg.test/theme/dark/icon.jpeg"
printf '\x89PNG\r\n\x1a\n%*s' 200 '' >"$T/www/both.test/theme/dark/symbol.png"; printf '\xff\xd8\xff\xe0%*s' 200 '' >"$T/www/both.test/theme/dark/symbol.jpeg"
printf 'sorry, this is a web page %*s' 200 '' >"$T/www/plain.test/theme/dark/logo.png"
PORT=$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1])')
( cd "$T/www" && exec python3 -m http.server "$PORT" --bind 127.0.0.1 >/dev/null 2>&1 ) & SRV=$!
for _ in $(seq 1 50); do python3 -c "import socket;socket.create_connection(('127.0.0.1',$PORT),0.2)" 2>/dev/null && break; sleep 0.1; done

export HOMELAB_HOMEPAGE_DIR="$T/hp" HOMELAB_DOCS_DIR="$REPO" HOMELAB_ALLOW_ROOT=1 NO_COLOR=1 HOMELAB_BRANDFETCH_BASE="http://127.0.0.1:$PORT"
unset HOMELAB_BRANDFETCH_ID
hl(){ bash "$H" "$@" 2>&1; }

# ---- bookmarks
out=$(hl bookmark list); check "list shows the shipped groups" 'echo "$out" | grep -q "Entertainment" && echo "$out" | grep -q "YouTube"'
out=$(hl bookmark add Example example.com Productivity)
check "add without a Brandfetch ID works and says how to save the ID" 'echo "$out" | grep -q "Added .Example. to .Productivity." && echo "$out" | grep -q "homelab bookmark brandfetch"'
check "the entry has name, abbreviation, address (with the closing slash) and the plain globe icon" 'grep -A3 "^    - Example:" $T/hp/bookmarks.yaml | grep -q "href: https://example.com/$" && grep -A4 "^    - Example:" $T/hp/bookmarks.yaml | grep -q "icon: mdi-web$"'
check "the first backup of the original file was kept" '[ -f $T/hp/bookmarks.yaml.before-theme ] && grep -q YouTube $T/hp/bookmarks.yaml.before-theme && ! grep -q Example $T/hp/bookmarks.yaml.before-theme'
out=$(hl bookmark add Example example.com Productivity); check "a duplicate name is refused" 'echo "$out" | grep -q "already in"'
out=$(hl bookmark brandfetch bad); check "a malformed client ID is refused" 'echo "$out" | grep -q "client ID is letters"'
out=$(hl bookmark brandfetch ABCDEF123456); check "the client ID is saved, mode 600" 'echo "$out" | grep -q saved && [ "$(stat -c %a $T/hp/.brandfetch-client-id)" = 600 ]'
out=$(hl bookmark add "Good Site" https://www.example.com "Brand New Group")
check "with an ID, the icon is the Brandfetch address (nothing is saved on this machine)" 'echo "$out" | grep -q "Logo: Brandfetch" && grep -q "icon: http://127.0.0.1:$PORT/example.com/theme/dark/symbol.svg?c=ABCDEF123456$" $T/hp/bookmarks.yaml && [ ! -e $T/hp/images ]'
check "a new group is created, after the others, with a blank line before it" 'grep -B1 "^- Brand New Group:" $T/hp/bookmarks.yaml | head -1 | grep -q "^$"'
check "a new category is put on the LINKS tab in the layout, with an icon" 'grep -A2 "^  Brand New Group:" $T/hp/settings.yaml | grep -q "tab: LINKS" && grep -A2 "^  Brand New Group:" $T/hp/settings.yaml | grep -q "icon: mdi-bookmark-multiple" && [ ! -e $T/hp/settings.yaml.before-theme ]'
out=$(hl bookmark add "Fake Logo" plain.test Others); check "a reply that is not an SVG gives the plain globe" 'echo "$out" | grep -q "no SVG" && grep -A4 "Fake Logo" $T/hp/bookmarks.yaml | grep -q "icon: mdi-web$"'
check "the Others category gets its own icon and is in the layout once" '[ "$(grep -c "^  Others:" $T/hp/settings.yaml)" = 1 ] && grep -A2 "^  Others:" $T/hp/settings.yaml | grep -q "mdi-dots-horizontal-circle"'
check "the layout is still in one piece (every group has a tab, the rest of the file is unchanged)" 'grep -q "^hideVersion: true" $T/hp/settings.yaml && grep -q "^  Productivity:" $T/hp/settings.yaml && python3 -c "import re,sys; s=open(sys.argv[1]).read(); sys.exit(0 if len(re.findall(r\"(?m)^    tab: \",s))==len(re.findall(r\"(?m)^  [^ #][^:]*:\\s*\$\",s[s.index(\"\\nlayout:\"):])) else 1)" $T/hp/settings.yaml'
out=$(hl bookmark add "Down Site" down.test Others); check "an unknown site: added without a logo, no crash" 'echo "$out" | grep -q "Added" && ! echo "$out" | grep -qi traceback'
mkdir -p "$T/hp/images"; printf '<svg/>' >"$T/hp/images/old-logo.svg"; hl bookmark add "Old Entry" old.test "Brand New Group" /images/old-logo.svg >/dev/null
out=$(hl bookmark remove "good site"); check "remove is not case sensitive" 'echo "$out" | grep -q Removed && ! grep -q "Good Site" $T/hp/bookmarks.yaml'
out=$(hl bookmark remove "old entry"); check "a logo saved by an older version is deleted with its bookmark" '[ ! -e $T/hp/images/old-logo.svg ]'
check "removing the last bookmark of a group removes the group" '! grep -q "Brand New Group" $T/hp/bookmarks.yaml'
out=$(hl bookmark remove nothing-here); check "removing an unknown bookmark says so" 'echo "$out" | grep -q "No bookmark named"'
check "the other bookmarks are unchanged" 'grep -q "YouTube" $T/hp/bookmarks.yaml && grep -q "Outlook" $T/hp/bookmarks.yaml && grep -c "^- " $T/hp/bookmarks.yaml | grep -q "^[4-5]$"'
cp "$T/hp/bookmarks.yaml.before-theme" "$T/hp/bookmarks.yaml"; : >"$T/hp/.brandfetch-client-id"; rm -f "$T/hp/.brandfetch-client-id"
out=$(HOMELAB_BRANDFETCH_ID=FROMENV12345 hl bookmark add "Env Site" example.com Productivity); check "the client ID can also come from the environment" 'echo "$out" | grep -q "Logo: Brandfetch" && grep -A4 "Env Site" $T/hp/bookmarks.yaml | grep -q "c=FROMENV12345"'
out=$(hl bookmark); check "bookmark with no command prints how to use it" 'echo "$out" | grep -q "homelab bookmark add NAME URL"'

# ---- theme
out=$(hl theme); check "theme shows the current look and how to change it" 'echo "$out" | grep -q "Background" && echo "$out" | grep -q "homelab theme cards"'
out=$(hl theme background "https://example.com/pic.jpg?a=1&b=2"); check "a web background is written as a quoted value" 'echo "$out" | grep -q "Background set" && grep -q "image: .https://example.com/pic.jpg?a=1&b=2." $T/hp/settings.yaml'
printf 'fake image' >"$T/pic.png"; out=$(hl theme background "$T/pic.png"); check "a local picture is copied into images/ and used" 'grep -q "image: /images/background.png" $T/hp/settings.yaml && [ -f $T/hp/images/background.png ]'
check "a local picture says Homepage must be restarted (or must get the folder)" 'echo "$out" | grep -qE "docker restart homepage|/app/public/images"'
out=$(hl theme background "$T/nothing.png"); check "a missing file is refused" 'echo "$out" | grep -q "neither a web address"'
out=$(hl theme background xl "https://example.com/blur.jpg"); check "background BLUR URL sets the picture and the blur together" 'echo "$out" | grep -q "blur xl" && grep -q "image: .https://example.com/blur.jpg." $T/hp/settings.yaml && [ "$(grep -c "^  blur: xl$" $T/hp/settings.yaml)" = 1 ]'
out=$(hl theme background none "https://example.com/blur2.jpg"); check "background none URL removes the blur" 'echo "$out" | grep -q "no blur" && ! grep -q "^  blur:" $T/hp/settings.yaml'
out=$(hl theme background 3xl "https://example.com/blur3.jpg"); check "3xl is allowed" 'grep -q "^  blur: 3xl$" $T/hp/settings.yaml'
cp $T/hp/settings.yaml $T/settings.keep; out=$(hl theme background huge "https://example.com/blur4.jpg"); check "a word that is not a blur changes nothing and lists the blurs" 'echo "$out" | grep -q "is not a blur" && echo "$out" | grep -q "2xl" && cmp -s $T/hp/settings.yaml $T/settings.keep'
out=$(hl theme background "https://example.com/blur5.jpg"); check "background URL alone keeps the blur" 'grep -q "^  blur: 3xl$" $T/hp/settings.yaml'
out=$(hl theme blur 3xl); out=$(hl theme blur md)
out=$(hl theme brightness 25); check "brightness is written" 'grep -q "^  brightness: 25$" $T/hp/settings.yaml'
out=$(hl theme brightness 250); check "brightness out of range is refused" 'echo "$out" | grep -q "from 0 to 100" && grep -q "^  brightness: 25$" $T/hp/settings.yaml'
out=$(hl theme blur none); check "blur none removes the key" '! grep -q "^  blur:" $T/hp/settings.yaml'
out=$(hl theme blur xl); check "blur xl is written once" '[ "$(grep -c "^  blur: xl$" $T/hp/settings.yaml)" = 1 ]'
check "the other settings.yaml keys are untouched" 'grep -q "^title: Home Lab" $T/hp/settings.yaml && grep -q "^theme: dark" $T/hp/settings.yaml && grep -q "^maxGroupColumns: 4" $T/hp/settings.yaml'
out=$(hl theme cards blue 40); check "cards colour and opacity are written to a marked block at the end of custom.css" 'tail -5 $T/hp/custom.css | grep -q "rgba(30, 58, 138, 0.4)" && grep -q "homelab theme >>>" $T/hp/custom.css'
out=$(hl theme cards "#112233"); check "a hex colour keeps the opacity" 'grep -q "rgba(17, 34, 51, 0.4)" $T/hp/custom.css'
out=$(hl theme cards immich purple); check "one service's colour is changed in place" 'grep -q "^#immich-card      { --accent: 147, 51,  234;  }" $T/hp/custom.css'
out=$(hl theme accent nonsense red); check "an unknown service is refused" 'echo "$out" | grep -q "know a service called"'
out=$(hl theme cards nocolor); check "an unknown colour is refused and names the choices" 'echo "$out" | grep -q "I don.t know the card colour" && echo "$out" | grep -q slate'
check "above the marked block custom.css differs from the shipped file in the Immich colour line only" '[ "$(diff <(sed "/homelab theme >>>/,\$d" $T/hp/custom.css | sed -e :a -e "/^\$/{\$d;N;ba" -e "}") <(sed -e :a -e "/^\$/{\$d;N;ba" -e "}" $REPO/homepage-config/custom.css) | grep -c "^<")" = 1 ]'
out=$(hl theme); check "theme shows the changes" 'echo "$out" | grep -q "rgb(17, 34, 51), 40% solid" && echo "$out" | grep -qi "immich"'
out=$(hl theme reset); check "reset removes the block and brings the shipped background back" '! grep -q "homelab theme" $T/hp/custom.css && grep -q "unsplash" $T/hp/settings.yaml && grep -q "^  brightness: 42$" $T/hp/settings.yaml && grep -q "^  blur: md$" $T/hp/settings.yaml'
check "after reset custom.css equals the shipped file" 'diff -q <(sed -e :a -e "/^\$/{\$d;N;ba" -e "}" $T/hp/custom.css) <(sed -e :a -e "/^\$/{\$d;N;ba" -e "}" $REPO/homepage-config/custom.css) >/dev/null'
check "no temporary files are left behind" '[ -z "$(ls $T/hp | grep "\.tmp$")" ]'
# ---- one card at a time: its numbers in the "accent colors (R, G, B)" list of custom.css are changed in place
cp "$T/hp/custom.css" "$T/css.before"
out=$(hl theme cards Adgrard home blue); check "a typo and a name with spaces still find AdGuard Home" 'echo "$out" | grep -q "AdGuard Home card is now blue" && grep -q "^#adguard-card     { --accent: 36,  140, 255;  }   /\* AdGuard Home blue \*/$" $T/hp/custom.css'
check "only that one line of custom.css changed (nothing was added)" '[ "$(diff $T/css.before $T/hp/custom.css | grep -c "^>")" = 1 ] && [ "$(wc -l <$T/css.before)" = "$(wc -l <$T/hp/custom.css)" ]'
out=$(hl theme cards immich "#00ff00"); check "a hex colour works for one card" 'grep -q "^#immich-card      { --accent: 0,   255, 0;    }" $T/hp/custom.css'
out=$(hl theme cards speedtest orange); check "a short name is enough" 'echo "$out" | grep -q "Speedtest Tracker card"'
out=$(hl theme cards nextcloud); check "a service without a colour asks for one" 'echo "$out" | grep -q "Which colour" && echo "$out" | grep -q "nextcloud blue"'
out=$(hl theme cards immich blue 40); check "a number does not go with one card" 'echo "$out" | grep -q "only goes with the all-cards form"'
out=$(hl theme cards nonsense green); check "an unknown service lists the real ones" 'echo "$out" | grep -q "know a service called" && echo "$out" | grep -q "Tailscale, AdGuard Home"'
out=$(hl theme); check "theme lists the cards that have their own colour" 'echo "$out" | grep -q "Card colours  AdGuard Home rgb(36, 140, 255)" && echo "$out" | grep -q "cards SERVICE COLOR" && echo "$out" | grep -q "cards COLOR NUMBER"'
out=$(hl theme cards adguard home default); check "default puts the shipped numbers back" 'echo "$out" | grep -q "shipped colour" && grep -q "^#adguard-card     { --accent: 104, 186, 72;   }   /\* AdGuard green \*/$" $T/hp/custom.css'
out=$(hl theme accent immich red); check "accent still works as an older name for the same thing" 'grep -q "^#immich-card      { --accent: 209, 18,  18;   }" $T/hp/custom.css'
out=$(hl theme accent all "#00ff00"); check "accent all colours every card that has a line" '[ "$(grep -c -- "--accent: 0,   255, 0;" $T/hp/custom.css)" = 9 ]'
out=$(hl theme cards all purple 50); check "cards COLOR NUMBER colours every card in a marked block" 'grep -q "^\.service-card { background: rgba(59, 7, 100, 0.5)" $T/hp/custom.css'
sed 's/^    - Netdata:/    - My Cloud:/; s/netdata-card/mycloud-card/' $T/hp/services.yaml >$T/hp/services.new && mv $T/hp/services.new $T/hp/services.yaml
out=$(hl theme cards my cloud pink); check "a service with no colour line in custom.css is explained" 'echo "$out" | grep -q "no colour line for the My Cloud card"'
printf '    - No Id Here:\n        href: http://x\n' >>$T/hp/services.yaml
out=$(hl theme cards no id here red); check "a service without an id line is explained" 'echo "$out" | grep -q "no .id:. line"'
out=$(hl theme reset); check "reset puts every colour back and removes the block" '! grep -q "homelab theme" $T/hp/custom.css && grep -q "^#netdata-card     { --accent: 0,   171, 68;   }   /\* Netdata Green \*/$" $T/hp/custom.css && grep -q "^#immich-card      { --accent: 209, 18,  18;   }   /\* Immich red \*/$" $T/hp/custom.css'
check "after all that, custom.css equals the shipped file again" 'diff -q <(sed -e :a -e "/^\$/{\$d;N;ba" -e "}" $T/hp/custom.css) <(sed -e :a -e "/^\$/{\$d;N;ba" -e "}" $REPO/homepage-config/custom.css) >/dev/null'
cp "$REPO/homepage-config/services.yaml" "$T/hp/services.yaml"

# ---- bookmark categories
cp "$REPO/homepage-config/bookmarks.yaml" "$T/hp/bookmarks.yaml"
out=$(hl bookmark add Netflix netflix.com onlineshopping); check "a category is found whatever the capital letters and spaces" 'echo "$out" | grep -q "Added .Netflix. to .Online Shopping." && ! echo "$out" | grep -q "new category" && grep -c "^- " $T/hp/bookmarks.yaml | grep -q "^3$"'
out=$(hl bookmark add Foo foo.com Entertanment); check "a small typo in the category is forgiven" 'echo "$out" | grep -q "to .Entertainment."'
out=$(hl bookmark add Zed zed.com); check "with no category and nobody to answer, it goes to Others and says so" 'echo "$out" | grep -q "Added .Zed. to .Others." && echo "$out" | grep -q "new category" && grep -q "^- Others:" $T/hp/bookmarks.yaml'
printf '2\n' >$T/ans; out=$(HOMELAB_TTY=$T/ans hl bookmark add Pick pick.com); check "with no category, a numbered list lets you choose" 'echo "$out" | grep -q "1) Entertainment" && echo "$out" | grep -q "A new category" && echo "$out" | grep -q "Added .Pick. to .Online Shopping."'
printf '5\nGames\n' >$T/ans; out=$(HOMELAB_TTY=$T/ans hl bookmark add Chess chess.com); check "the list can also create a new category" 'echo "$out" | grep -q "Added .Chess. to .Games." && grep -q "^- Games:" $T/hp/bookmarks.yaml'
out=$(hl bookmark add YouTube yt.com Productivity); check "the same name may be in two categories" 'echo "$out" | grep -q "Added"'
out=$(hl bookmark remove YouTube); check "removing a name that is in two categories needs the category" 'echo "$out" | grep -q "Say which one" && [ "$(grep -c "YouTube" $T/hp/bookmarks.yaml)" = 2 ]'
printf '2\n' >$T/ans; out=$(HOMELAB_TTY=$T/ans hl bookmark remove YouTube); check "... or you pick it from a list" 'echo "$out" | grep -q "Removed .YouTube. from .Productivity." && grep -A1 "^- Entertainment:" $T/hp/bookmarks.yaml | grep -q YouTube'
out=$(hl bookmark remove youtube entertainment); check "remove NAME CATEGORY takes it out of that category only" 'echo "$out" | grep -q "from .Entertainment." && ! grep -q YouTube $T/hp/bookmarks.yaml && grep -q Twitch $T/hp/bookmarks.yaml'
out=$(hl bookmark remove Amazon Productivity); check "a name that is not in that category is refused" 'echo "$out" | grep -q "No bookmark named .Amazon. in .Productivity."'
out=$(hl bookmark remove Amazon Nowhere); check "an unknown category lists the real ones" 'echo "$out" | grep -q "no category" && echo "$out" | grep -q "Entertainment"'
out=$(hl bookmark move Amazon Productivity); check "move puts a bookmark in another category" 'echo "$out" | grep -q "Moved .Amazon. from .Online Shopping. to .Productivity." && grep -A30 "^- Productivity:" $T/hp/bookmarks.yaml | grep -q Amazon'
out=$(hl bookmark move Amazon productivity); check "moving into the category it is already in is refused" 'echo "$out" | grep -q "already in"'
hl bookmark move Newegg Productivity >/dev/null; hl bookmark move eBay Productivity >/dev/null; hl bookmark move Netflix Productivity >/dev/null; hl bookmark move Pick Productivity >/dev/null
check "a category that becomes empty is removed" '! grep -q "^- Online Shopping:" $T/hp/bookmarks.yaml'
hl bookmark add Plug plug.com "Smart Home" >/dev/null
out=$(hl bookmark move Newegg smart home 1); check "move: a category with spaces needs no quotes" 'echo "$out" | grep -q "Moved .Newegg. from .Productivity. to .Smart Home. as number 1" && ! echo "$out" | grep -q "new category"'
out=$(hl bookmark move Newegg Productivity 2); check "move: a quoted category and a number still work" 'echo "$out" | grep -q "to .Productivity. as number 2"'
out=$(hl bookmark add Gadget gadget.com smart home); check "add: a category with spaces needs no quotes" 'echo "$out" | grep -q "Added .Gadget. to .Smart Home." && ! echo "$out" | grep -q "new category"'
out=$(hl bookmark remove Gadget smart home); check "remove: a category with spaces needs no quotes" 'echo "$out" | grep -q "Removed .Gadget. from .Smart Home."'
out=$(hl bookmark add a b c d e f g h i j); check "too many words suggests quotes" 'echo "$out" | grep -q "in quotes"'
out=$(hl bookmark); check "the usage text mentions categories and move" 'echo "$out" | grep -q CATEGORY && echo "$out" | grep -q "bookmark move"'
check "the file is still valid: every category has bookmarks, no blank-line pile-ups" '! grep -q "^$" <(tail -1 $T/hp/bookmarks.yaml) && ! grep -Pzo "\n\n\n" $T/hp/bookmarks.yaml >/dev/null'

# ---- icon link and place number
cp "$REPO/homepage-config/bookmarks.yaml" "$T/hp/bookmarks.yaml"
out=$(hl bookmark add Netflix netflix.com Entertainment si-netflix 2); check "an icon name and a number are accepted after the category" 'echo "$out" | grep -q "as number 2" && grep -A4 "^    - Netflix:" $T/hp/bookmarks.yaml | grep -q "icon: si-netflix$"'
check "the number puts it in that place" '[ "$(hl bookmark list | sed -n "/Entertainment/,/Online/p" | sed -n 3p | awk "{print \$2}")" = Netflix ]'
out=$(hl bookmark add First first.test Entertainment https://x.test/i.svg 1); check "a web address as the icon is used as it is, and 1 means first" 'grep -A5 "^- Entertainment:" $T/hp/bookmarks.yaml | grep -q "^    - First:" && grep -A4 "^    - First:" $T/hp/bookmarks.yaml | grep -q "icon: https://x.test/i.svg$"'
out=$(hl bookmark add Plain plain.example Productivity generic); check "the word generic gives the plain globe without asking Brandfetch" 'grep -A4 "^    - Plain:" $T/hp/bookmarks.yaml | grep -q "icon: mdi-web$" && ! echo "$out" | grep -q Brandfetch'
out=$(hl bookmark add Late late.test Entertainment 99); check "a number past the end means last" 'echo "$out" | grep -q "as number 6"'
out=$(hl bookmark add Icon2 i2.test si-youtube 3); check "the category can be left out when an icon or number is given (then you are asked, or Others is used)" 'echo "$out" | grep -q "Added .Icon2. to .Others."'
out=$(hl bookmark add Zero z.test Entertainment 0); check "place 0 is refused" 'echo "$out" | grep -q "starts at 1"'
out=$(hl bookmark add Twice t.test Entertainment 2 3); check "two numbers are refused" 'echo "$out" | grep -q "Two numbers"'
out=$(hl bookmark move Late Entertainment); check "moving within the same category needs a number" 'echo "$out" | grep -q "add a number"'
out=$(hl bookmark move Late Entertainment 1); check "a number moves a bookmark within its category" 'echo "$out" | grep -q "as number 1" && grep -A5 "^- Entertainment:" $T/hp/bookmarks.yaml | grep -q "^    - Late:"'
out=$(hl bookmark move Plain Entertainment 2); check "moving to another category at a number" 'echo "$out" | grep -q "to .Entertainment. as number 2"'
out=$(hl bookmark list); check "list shows the number of each bookmark" 'echo "$out" | grep -q " 1\. Late"'
out=$(hl bookmark); check "the usage names ICON LINK and NUMBER" 'echo "$out" | grep -q "ICON LINK" && echo "$out" | grep -q "NUMBER"'

# ---- Brandfetch: SVG first, then PNG, then JPEG
export HOMELAB_BRANDFETCH_ID=PICKFORMAT1
out=$(hl bookmark add Svg example.com Others); check "an SVG is chosen when there is one" 'echo "$out" | grep -q "SVG" && grep -A4 "^    - Svg:" $T/hp/bookmarks.yaml | grep -q "symbol.svg"'
out=$(hl bookmark add Png png.test Others); check "no SVG: a PNG is used (the logo version found first)" 'echo "$out" | grep -q "PNG" && grep -A4 "^    - Png:" $T/hp/bookmarks.yaml | grep -q "png.test/theme/dark/logo.png?c=PICKFORMAT1$"'
out=$(hl bookmark add Jpeg jpeg.test Others); check "no SVG and no PNG: a JPEG is used" 'echo "$out" | grep -q "JPEG" && grep -A4 "^    - Jpeg:" $T/hp/bookmarks.yaml | grep -q "jpeg.test/theme/dark/icon.jpeg"'
out=$(hl bookmark add Both both.test Others); check "a PNG wins over a JPEG" 'grep -A4 "^    - Both:" $T/hp/bookmarks.yaml | grep -q "symbol.png"'
out=$(hl bookmark add Nothing nothing.test Others); check "no picture at all: the plain globe, and it says SVG, PNG or JPEG" 'echo "$out" | grep -q "no SVG, PNG or JPEG" && grep -A4 "^    - Nothing:" $T/hp/bookmarks.yaml | grep -q "icon: mdi-web$"'
unset HOMELAB_BRANDFETCH_ID

# ---- the temperature labels on the login screen
mkdir -p "$T/st"; NOW=$(date +%s)
printf 'MAIN1|/dev/sda|34|%s\nMAIN2|/dev/sdb|36|%s\nBACKUP1|/dev/sdc|standby|%s\nboot|/dev/nvme0n1|40|%s\n' "$NOW" "$NOW" "$NOW" "$NOW" >"$T/st/temps"
printf 'MAIN1|1 TB Samsung HDD\nMAIN2|1 TB Samsung HDD\nBACKUP1|4 TB Seagate HDD\n' >"$T/st/drive-names"
out=$(HOMELAB_STATE_DIR=$T/st HOMELAB_NAMES_FILE=$T/none hl status); check "Drive temps shows drive names, not MAIN1" 'echo "$out" | grep -q "4 TB Seagate HDD asleep" && ! echo "$out" | grep -q "BACKUP1 asleep"'
check "two drives with the same name keep their label too" 'echo "$out" | grep -q "1 TB Samsung HDD (MAIN1) 34" && echo "$out" | grep -q "1 TB Samsung HDD (MAIN2) 36"'
printf 'MAIN1=Photos drive\n' >"$T/st/names"; out=$(HOMELAB_STATE_DIR=$T/st HOMELAB_NAMES_FILE=$T/st/names hl status); check "a name you chose wins" 'echo "$out" | grep -q "Photos drive 34"'

# ---- the command list: every section prints as a table (command, then its description beside it) in a 100-column window
mkdir -p "$T/bin"; printf '#!/bin/sh\n' >"$T/bin/homelab-setup"; chmod +x "$T/bin/homelab-setup"
out=$(PATH="$T/bin:$PATH" COLUMNS=100 TERM=xterm-256color hl commands)
check "no description is printed below its command at 100 columns" '! echo "$out" | grep -q "^       [a-z(]"'
check "the Homepage commands show COLOR NUMBER and SERVICE COLOR" 'echo "$out" | grep -q "theme cards COLOR NUMBER" && echo "$out" | grep -q "theme cards SERVICE COLOR" && echo "$out" | grep -q "bookmark move NAME CATEGORY"'

# ---- the login screen is remembered for 2 minutes; a fresh boot only gets light checks
export HOMELAB_CACHE_DIR="$T/cache" HOMELAB_STATE_DIR="$T/st"
out=$(hl login); check "login: the first terminal does the checks" '! echo "$out" | grep -q "Shown as it was" && echo "$out" | grep -q "Status" && [ -s $T/cache/homelab-login/screen ]'
check "login: the saved screen is private to the user" '[ "$(stat -c %a $T/cache/homelab-login)" = 700 ]'
out=$(hl login); check "login: a terminal opened right after shows the saved screen and says how to get it live" 'echo "$out" | grep -q "Shown as it was" && echo "$out" | grep -q "homelab status" && echo "$out" | grep -q "Status"'
out=$(hl); check "login: typing homelab is always live" '! echo "$out" | grep -q "Shown as it was"'
out=$(hl status); check "login: homelab status is always live" '! echo "$out" | grep -q "Shown as it was"'
out=$(HOMELAB_LOGIN_CACHE_SECS=0 hl login); check "login: an old screen is not reused" '! echo "$out" | grep -q "Shown as it was"'
out=$(COLUMNS=60 hl login); check "login: a different window width gets a new screen" '! echo "$out" | grep -q "Shown as it was"'
out=$(HOMELAB_UPTIME=0 hl login); check "login: a screen made before the last boot is not reused" '! echo "$out" | grep -q "Shown as it was"'
rm -rf "$T/cache"
out=$(HOMELAB_UPTIME=120 hl login); check "login: right after a boot the apps are not asked, and it says why" 'echo "$out" | grep -q "just started and the apps are still starting"'
rm -rf "$T/cache"
out=$(HOMELAB_UPTIME=5000 hl login); check "login: later it checks the apps as usual" '! echo "$out" | grep -q "just started and the apps"'
unset HOMELAB_CACHE_DIR HOMELAB_STATE_DIR

# ---- the readings job: low priority; system updates are looked up at most every 6 hours when the schedule runs it
mkdir -p "$T/fb"; cat >"$T/fb/apt-get" <<'EOS'
#!/bin/sh
echo run >>"$APT_LOG"
echo "Inst a [1] (2 x)"; echo "Inst b [1] (2 x)"
EOS
chmod +x "$T/fb/apt-get"
SAMPLE="$REPO/scripts/homelab-sample"
sample(){ APT_LOG="$T/apt.log" HOMELAB_EXTRA_PATH="$T/fb" HOMELAB_STATE_DIR="$T/ss" "$@" bash "$SAMPLE" </dev/null 2>&1; }
rm -rf "$T/ss" "$T/apt.log"
if [ "$(id -u)" -eq 0 ]; then
  sample env HOMELAB_UPTIME=100000 >/dev/null >"$T/s1.out"; check "sample: the first scheduled run looks up updates" '[ "$(wc -l <$T/apt.log)" = 1 ] && grep -q "^2|" $T/ss/apt'
  sample env HOMELAB_UPTIME=100000 >"$T/s2.out"; check "sample: a second scheduled run soon after does not" '[ "$(wc -l <$T/apt.log)" = 1 ]'
  printf '2|%s\n' "$(( $(date +%s) - 7 * 3600 ))" >"$T/ss/apt"
  sample env HOMELAB_UPTIME=100000 >"$T/s3.out"; check "sample: after 6 hours it looks again" '[ "$(wc -l <$T/apt.log)" = 2 ]'
  printf '2|0\n' >"$T/ss/apt"
  sample env HOMELAB_UPTIME=100 >"$T/s4.out"; check "sample: in the first 10 minutes after a boot it leaves updates alone but still reads temperatures" '[ "$(wc -l <$T/apt.log)" = 2 ] && [ -e $T/ss/temps ]'
fi

out=$(HOMELAB_HOMEPAGE_DIR=$T/nowhere hl theme); check "a missing Homepage folder gives a plain message" 'echo "$out" | grep -q "does not exist" && ! echo "$out" | grep -qi traceback'
# shellcheck disable=SC2034  # out is used inside the quoted test command
out=$(env -u HOMELAB_ALLOW_ROOT bash "$H" theme 2>&1 </dev/null); [ "$(id -u)" -eq 0 ] && check "as root it refuses and explains" 'echo "$out" | grep -q "without sudo"'

echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ] && echo OK || echo FAIL
