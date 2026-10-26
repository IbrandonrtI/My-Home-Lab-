#!/bin/bash
# Tests for "homelab theme" and "homelab bookmark" (scripts/homelab) in a temporary copy of the Homepage files.
# A small local web server plays Brandfetch. Nothing on this machine is touched. Last line: OK or FAIL.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
H="$REPO/scripts/homelab"
T="$(mktemp -d)"; PASS=0; FAIL=0
trap 'kill $SRV 2>/dev/null; rm -rf "$T"' EXIT
check(){ if ( eval "$2" ); then PASS=$((PASS+1)); else echo "FAIL  $1"; FAIL=$((FAIL+1)); fi; }

mkdir -p "$T/hp" "$T/www/example.com/theme/dark" "$T/www/plain.test/theme/dark"
cp "$REPO"/homepage-config/* "$T/hp/"
SVG='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4" fill="red"/></svg>'
printf '%s%*s' "$SVG" 120 '' >"$T/www/example.com/theme/dark/symbol.svg"
printf 'not a picture, just a web page that says sorry %*s' 150 '' >"$T/www/plain.test/theme/dark/symbol.svg"
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
check "the entry has name, abbreviation and address, and no icon line" 'grep -A3 "^    - Example:" $T/hp/bookmarks.yaml | grep -q "href: https://example.com" && ! grep -A4 "^    - Example:" $T/hp/bookmarks.yaml | grep -q icon'
check "the first backup of the original file was kept" '[ -f $T/hp/bookmarks.yaml.before-theme ] && grep -q YouTube $T/hp/bookmarks.yaml.before-theme && ! grep -q Example $T/hp/bookmarks.yaml.before-theme'
out=$(hl bookmark add Example example.com Productivity); check "a duplicate name is refused" 'echo "$out" | grep -q "already in"'
out=$(hl bookmark brandfetch bad); check "a malformed client ID is refused" 'echo "$out" | grep -q "client ID is letters"'
out=$(hl bookmark brandfetch ABCDEF123456); check "the client ID is saved, mode 600" 'echo "$out" | grep -q saved && [ "$(stat -c %a $T/hp/.brandfetch-client-id)" = 600 ]'
out=$(hl bookmark add "Good Site" https://www.example.com "Brand New Group")
check "with an ID, the SVG is downloaded into images/ and used as the icon" 'echo "$out" | grep -q "Logo saved" && grep -q "<svg" $T/hp/images/good-site.svg && grep -q "icon: /images/good-site.svg" $T/hp/bookmarks.yaml'
check "a new group is created, after the others, with a blank line before it" 'grep -B1 "^- Brand New Group:" $T/hp/bookmarks.yaml | head -1 | grep -q "^$"'
out=$(hl bookmark add "Fake Logo" plain.test Others); check "a reply that is not an SVG is not saved" 'echo "$out" | grep -q "gave no SVG" && [ ! -e $T/hp/images/fake-logo.svg ] && ! grep -A4 "Fake Logo" $T/hp/bookmarks.yaml | grep -q icon'
out=$(hl bookmark add "Down Site" down.test Others); check "an unknown site: added without a logo, no crash" 'echo "$out" | grep -q "Added" && ! echo "$out" | grep -qi traceback'
out=$(hl bookmark remove "good site"); check "remove is not case sensitive and deletes the saved logo" 'echo "$out" | grep -q Removed && [ ! -e $T/hp/images/good-site.svg ] && ! grep -q "Good Site" $T/hp/bookmarks.yaml'
check "removing the last bookmark of a group removes the group" '! grep -q "Brand New Group" $T/hp/bookmarks.yaml'
out=$(hl bookmark remove nothing-here); check "removing an unknown bookmark says so" 'echo "$out" | grep -q "No bookmark named"'
check "the other bookmarks are unchanged" 'grep -q "YouTube" $T/hp/bookmarks.yaml && grep -q "Outlook" $T/hp/bookmarks.yaml && grep -c "^- " $T/hp/bookmarks.yaml | grep -q "^[4-5]$"'
cp "$T/hp/bookmarks.yaml.before-theme" "$T/hp/bookmarks.yaml"; : >"$T/hp/.brandfetch-client-id"; rm -f "$T/hp/.brandfetch-client-id"
out=$(HOMELAB_BRANDFETCH_ID=FROMENV12345 hl bookmark add "Env Site" example.com Productivity); check "the client ID can also come from the environment" 'echo "$out" | grep -q "Logo saved"'
out=$(hl bookmark); check "bookmark with no command prints how to use it" 'echo "$out" | grep -q "homelab bookmark add NAME URL"'

# ---- theme
out=$(hl theme); check "theme shows the current look and how to change it" 'echo "$out" | grep -q "Background" && echo "$out" | grep -q "homelab theme cards"'
out=$(hl theme background "https://example.com/pic.jpg?a=1&b=2"); check "a web background is written as a quoted value" 'echo "$out" | grep -q "Background set" && grep -q "image: .https://example.com/pic.jpg?a=1&b=2." $T/hp/settings.yaml'
printf 'fake image' >"$T/pic.png"; out=$(hl theme background "$T/pic.png"); check "a local picture is copied into images/ and used" 'grep -q "image: /images/background.png" $T/hp/settings.yaml && [ -f $T/hp/images/background.png ]'
out=$(hl theme background "$T/nothing.png"); check "a missing file is refused" 'echo "$out" | grep -q "neither a web address"'
out=$(hl theme brightness 25); check "brightness is written" 'grep -q "^  brightness: 25$" $T/hp/settings.yaml'
out=$(hl theme brightness 250); check "brightness out of range is refused" 'echo "$out" | grep -q "from 0 to 100" && grep -q "^  brightness: 25$" $T/hp/settings.yaml'
out=$(hl theme blur none); check "blur none removes the key" '! grep -q "^  blur:" $T/hp/settings.yaml'
out=$(hl theme blur xl); check "blur xl is written once" '[ "$(grep -c "^  blur: xl$" $T/hp/settings.yaml)" = 1 ]'
check "the other settings.yaml keys are untouched" 'grep -q "^title: Home Lab" $T/hp/settings.yaml && grep -q "^theme: dark" $T/hp/settings.yaml && grep -q "^maxGroupColumns: 4" $T/hp/settings.yaml'
out=$(hl theme cards blue 40); check "cards colour and opacity are written to a marked block at the end of custom.css" 'tail -5 $T/hp/custom.css | grep -q "rgba(30, 58, 138, 0.4)" && grep -q "homelab theme >>>" $T/hp/custom.css'
out=$(hl theme cards "#112233"); check "a hex colour keeps the opacity" 'grep -q "rgba(17, 34, 51, 0.4)" $T/hp/custom.css'
out=$(hl theme accent immich purple); check "one service's accent is written" 'grep -q "#immich-card { --accent: 147, 51, 234; }" $T/hp/custom.css'
out=$(hl theme accent all "#00ff00"); check "all accents can be set at once" '[ "$(grep -c -- "--accent: 0, 255, 0" $T/hp/custom.css)" = 9 ]'
out=$(hl theme accent nonsense red); check "an unknown service is refused" 'echo "$out" | grep -q "Unknown service"'
out=$(hl theme cards nocolor); check "an unknown colour is refused and names the choices" 'echo "$out" | grep -q "I don.t know the card colour" && echo "$out" | grep -q slate'
check "everything above the marked block in custom.css is byte-for-byte the original" '[ "$(sed -n "1,/homelab theme >>>/p" $T/hp/custom.css | sed "\$d" | sed -e :a -e "/^\$/{\$d;N;ba" -e "}" | md5sum)" = "$(sed -e :a -e "/^\$/{\$d;N;ba" -e "}" $REPO/homepage-config/custom.css | md5sum)" ]'
out=$(hl theme); check "theme shows the changes" 'echo "$out" | grep -q "rgb(17, 34, 51), 40% solid" && echo "$out" | grep -q "immich"'
out=$(hl theme reset); check "reset removes the block and brings the shipped background back" '! grep -q "homelab theme" $T/hp/custom.css && grep -q "unsplash" $T/hp/settings.yaml && grep -q "^  brightness: 42$" $T/hp/settings.yaml && grep -q "^  blur: md$" $T/hp/settings.yaml'
check "after reset custom.css equals the shipped file" 'diff -q <(sed -e :a -e "/^\$/{\$d;N;ba" -e "}" $T/hp/custom.css) <(sed -e :a -e "/^\$/{\$d;N;ba" -e "}" $REPO/homepage-config/custom.css) >/dev/null'
check "no temporary files are left behind" '[ -z "$(ls $T/hp | grep "\.tmp$")" ]'
out=$(HOMELAB_HOMEPAGE_DIR=$T/nowhere hl theme); check "a missing Homepage folder gives a plain message" 'echo "$out" | grep -q "does not exist" && ! echo "$out" | grep -qi traceback'
out=$(env -u HOMELAB_ALLOW_ROOT bash "$H" theme 2>&1 </dev/null); [ "$(id -u)" -eq 0 ] && check "as root it refuses and explains" 'echo "$out" | grep -q "without sudo"'

echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ] && echo OK || echo FAIL
