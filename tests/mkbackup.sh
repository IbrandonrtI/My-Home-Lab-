#!/bin/bash
# mkbackup.sh DIR USER  -> a small fake backup tree like homelab-backup writes
D="$1"; U="${2:-testuser}"
rm -rf "$D"; mkdir -p "$D"/main/immich/library "$D"/main/nextcloud/data "$D"/main/filebrowser "$D"/db-dumps \
  "$D/boot-configs/home/$U/homepage-config" "$D/boot-configs/home/$U/nextcloud/html/config" "$D/boot-configs/etc"
echo "photo-bytes-1" > "$D/main/immich/library/photo1.jpg"
echo "photo-bytes-2" > "$D/main/immich/library/photo2.jpg"
echo "doc" > "$D/main/nextcloud/data/doc.txt"
echo "ff" > "$D/main/filebrowser/file.txt"
printf -- "- Bookmarks-from-backup:\n    - from_backup: true\n" > "$D/boot-configs/home/$U/homepage-config/bookmarks.yaml"
printf "<?php\n\$CONFIG = array (\n  'dbuser' => 'nextcloud',\n  'dbpassword' => 'OldNcDbPass123456',\n);\n" > "$D/boot-configs/home/$U/nextcloud/html/config/config.php"
echo "# fake" > "$D/boot-configs/etc/homelab-backup.conf"
echo "0 6 * * * /usr/local/sbin/homelab-backup" > "$D/boot-configs/root-crontab.txt"
echo "SELECT 1;" | gzip > "$D/db-dumps/nextcloud-20261020.sql.gz"
