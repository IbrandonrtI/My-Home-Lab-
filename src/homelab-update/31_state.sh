summary_epoch() { local e=""; [ -r "$SUMMARY_FILE" ] && e=$(head -1 "$SUMMARY_FILE"); [[ "$e" =~ ^[0-9]+$ ]] && echo "$e"; }

OLD_STATE=()
read_state() {
  OLD_STATE=()
  [ -r "$STATE_FILE" ] || return 0
  local l
  while IFS= read -r l; do [ -n "$l" ] && OLD_STATE+=("$l"); done <"$STATE_FILE"
}

write_outputs() {
  local epoch=$1 line stacks img dig at st s
  local -a order=(); local -A per=()
  local all=""
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    all+="$line"$'\n'
    IFS='|' read -r stacks img dig at st <<<"$line"
    for s in ${stacks//,/ }; do
      if [ -z "${per[$s]+x}" ]; then order+=("$s"); per[$s]="$img=$st"; else per[$s]+=",$img=$st"; fi
    done
  done
  printf '%s' "$all" | cut -d'|' -f1-4 | put image-state || return 1
  {
    echo "$epoch"
    for s in "${order[@]}"; do printf '%s  %s\n' "$s" "${per[$s]}"; done
  } | put image-updates
}

evaluate_state() {
  local line stacks img dig at st
  for line in "${OLD_STATE[@]}"; do
    IFS='|' read -r stacks img dig at <<<"$line"
    st=$(classify "$img" "$dig")
    [ "$st" = current ] || printf '%s|%s|%s|%s|%s\n' "$stacks" "$img" "$dig" "$at" "$st"
  done
}

