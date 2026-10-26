# Nextcloud: syncing your devices

Nextcloud only becomes useful once your devices talk to it. This guide installs the Nextcloud app on each kind of device, signs it in to the server from [build guide, section 11](build-guide.md#11-nextcloud), and sets up a folder that syncs by itself. On a computer that folder is Documents. On a phone it's a way to send files to the server. Photos and videos from phones go through Immich ([build guide, section 10](build-guide.md#10-immich)), so I leave photo upload off in the Nextcloud app.

## 1. Before you start

1. **Turn on Tailscale on the device.** The server has no public address. A device can only reach `https://pc.your-tailnet.ts.net:1005` while Tailscale is installed, signed in to the same account and connected (see [build guide, section 5](build-guide.md#5-tailscale)). If an app can't connect, check this first.
1. **Know the server address and login.** The address is `https://pc.your-tailnet.ts.net:1005`. Use `https://`, keep the `:1005`, and add nothing after it. The login is the name and password from [build guide, section 11.1](build-guide.md#111-choose-your-passwords), or the one you changed it to.
1. **Sync is not a backup.** A synced folder is one set of files kept the same in several places. If you delete a file on one device, the deletion gets copied to all the others. Right now the server keeps one copy of its data on the data drive. The daily backup to a second drive is still on my [to-do list](../README.md#whats-next) (until a backup drive is connected, the backup sits on the boot drive), so keep another copy of anything you can't replace.

How much of each platform I've tested:

| Platform | Status |
| :--- | :--- |
| Windows | Tested on my setup |
| iPhone | Install, sign-in and browsing tested. Uploading follows Nextcloud's official instructions and I haven't tried it |
| Linux (Linux Mint and Ubuntu) | Follows Nextcloud's official instructions, not tested |
| macOS | Follows Nextcloud's official instructions, not tested |
| Android | Follows Nextcloud's official instructions, not tested |

Download links and requirements come from [nextcloud.com/install](https://nextcloud.com/install/), checked on 20 October 2026. They change, so check that page if a version below doesn't match.

## 2. Windows

**You need:** Windows 10 version 1809 or later, 64-bit. The installer is a `.msi` file.

**Step 1: check where your Documents folder really is.** On many Windows PCs, Documents lives inside OneDrive, which means OneDrive is already syncing it. Two sync tools on one folder can fight each other and make duplicate or conflicting files.

1. Open File Explorer. In the left panel, right-click **Documents** and choose **Properties**.
1. Open the **Location** tab and read the path.
   - `C:\Users\your-windows-username\Documents` is a normal folder.
   - A path with `OneDrive` in it, like `C:\Users\your-windows-username\OneDrive\Documents`, means OneDrive manages it.

If OneDrive manages it, pick one before you go on: turn off OneDrive's backup of Documents (in OneDrive's settings, under **Sync and backup**, then **Manage backup**, though the wording changes between versions), or sync a different folder with Nextcloud. My Documents folder was inside OneDrive and Nextcloud's sync worked with both turned on, but I didn't test it for long, and I don't know if Nextcloud supports that combination.

**Step 2: download and install.**

1. On a device with a browser, open [nextcloud.com/install](https://nextcloud.com/install/) and download the Windows desktop client (the `.msi` file).
1. Double-click it, accept the prompts and click **Yes** if Windows asks for permission. Finish the installer.
1. Start **Nextcloud** from the Start menu.

**Step 3: sign in.**

1. Enter the server address `https://pc.your-tailnet.ts.net:1005` and click **Next** (or **Log in**).
1. Your browser opens the Nextcloud login page. Log in, then click **Grant access**.
1. Go back to the Nextcloud window. It shows the account and asks how to set up the local folder.

**Step 4: the first-run screen.** It offers **Virtual files**, **Synchronize everything** and **Choose what to sync**, and shows a local folder (`C:\Users\your-windows-username\Nextcloud` by default). I chose **Synchronize everything**, kept the default folder and clicked **Done**.

> **Heads up.** This first connection downloads the whole server into the `Nextcloud` folder. Any folder you add in step 5 also shows up there, so you end up with a second copy of the same files. The note at the end of this part explains how to avoid or remove it. A cleaner order, which I haven't tested, is to click **Set up later** here and add only the folder you want in step 5.

**Step 5: add your Documents folder.**

1. Find the Nextcloud icon in the system tray at the bottom right. If you don't see it, click the small arrow to show hidden icons.
1. Click the icon, click your account name or avatar, then click **Settings**.
1. On your account's tab, click **Add Folder Sync Connection**.
1. Pick the local folder: your Documents folder, as shown on the Location tab in step 1. Click **Next**.
1. Pick the server folder. Make a new folder on the server called `Document sync`, select it and continue.
1. The last screen has an option for **virtual files**. I left it on. With virtual files your files show up in File Explorer but are only downloaded when you open them, which saves disk space. If you want every file stored on the PC all the time, turn it off. You can also right-click a file or folder and choose **Always keep on this device**.
1. Click **Finish**.

**Step 6: start it with Windows.** In the same Settings window, open the **General** tab and turn on the option to launch Nextcloud on system startup, so sync carries on after a restart.

**Check it:** in the Settings window, the connection should show a green check and the word "Synchronizing" followed by your Documents folder. Open `https://pc.your-tailnet.ts.net:1005` in a browser. The **Files** page should list the `Document sync` folder with your files in it. For a live test, make a text file called `sync-test.txt` in Documents. It should show up in the browser within a minute. Delete the test file afterwards.

**If you end up with a second copy.** Open `C:\Users\your-windows-username\Nextcloud`. If it has a `Document sync` folder with files in it, you have two local copies of the same server folder. That's what happened to me.

- **Never delete the extra copy in File Explorer.** Both folders are the same server folder, so deleting files in one place sends the deletion to the server and then to your real Documents folder.
- To remove it safely, first make sure the files are visible on the server in your browser. Then open the Settings window, expand the main `Nextcloud` connection, untick `Document sync` and click **Apply**. The window warns that unticked folders are removed from your local file system. Only the local copy in the `Nextcloud` folder goes away. The server and your real Documents folder stay as they are. I haven't run this step on my setup yet.

## 3. Linux (Linux Mint and Ubuntu)

**Not tested on my setup. This follows Nextcloud's official instructions.** There are two ways to install it. The AppImage is the one on Nextcloud's download page, so try it first. The Flatpak is the second option.

### Option 1: the AppImage (from Nextcloud's download page)

An AppImage is a single program file. You don't install it with the package manager. You make it executable and run it.

1. Open [nextcloud.com/install](https://nextcloud.com/install/) and download the Linux desktop client. The file ends in `.AppImage` and lands in your `Downloads` folder.
1. Open a terminal and make the file executable. The `*` stands for the version in the file name:

   ```bash
   cd ~/Downloads
   chmod +x Nextcloud-*.AppImage
   ```

1. Run it:

   ```bash
   ./Nextcloud-*.AppImage
   ```

1. If it fails with an error that mentions FUSE, install the library AppImages need and run it again. This is from my own knowledge, not from Nextcloud's page. On Linux Mint 22 and Ubuntu 24.04 the package is called `libfuse2t64`. On older releases (Linux Mint 21, Ubuntu 22.04) it's `libfuse2`:

   ```bash
   sudo apt install libfuse2t64
   ```

1. Move the file somewhere permanent so you don't lose it in Downloads:

   ```bash
   mkdir -p ~/Applications
   mv ~/Downloads/Nextcloud-*.AppImage ~/Applications/
   ```

1. To start it at login, open **Startup Applications** (Linux Mint) or **Startup Applications Preferences** (Ubuntu), add a new entry and give it the full path to the file in `~/Applications`.

### Option 2: the Flatpak (from Flathub)

Nextcloud GmbH publishes this client on Flathub as `com.nextcloud.desktopclient.nextcloud`. Nextcloud's own download page doesn't offer it for this client, so it's the second choice. Linux Mint comes with Flatpak and Flathub. On Ubuntu, install Flatpak and add the Flathub repository first (see [flathub.org/setup](https://flathub.org/setup)).

```bash
flatpak install flathub com.nextcloud.desktopclient.nextcloud
flatpak run com.nextcloud.desktopclient.nextcloud
```

Flatpak apps run in a sandbox, so the client may not be allowed to see your Documents folder. Check what it can access:

```bash
flatpak info --show-permissions com.nextcloud.desktopclient.nextcloud
```

If your Documents folder isn't covered, use a tool like Flatseal to allow it, or use the AppImage.

### Sign in and set up the sync (both options)

1. In the first window, enter `https://pc.your-tailnet.ts.net:1005` and continue. Log in in the browser and click **Grant access**.
1. On the local folder screen, keep the default (`~/Nextcloud`) and finish. The second-copy warning from [part 2](#2-windows) applies here too. If the screen lets you choose what to sync, untick everything. I haven't tested that.
1. Open the Nextcloud icon in the system tray, then **Settings**, then click **Add Folder Sync Connection**.
1. Pick your Documents folder (`~/Documents`), then make a server folder called `Document sync` and finish.
1. The client needs a password keyring (GNOME Keyring or KWallet) to remember your login. Most desktops have one. If it asks you to create or unlock a keyring, use your normal login password.

**Check it:** the connection shows a green check, and `https://pc.your-tailnet.ts.net:1005` lists the `Document sync` folder with your files.

## 4. macOS

**Not tested on my setup. This follows Nextcloud's official instructions.**

**You need:** macOS 13 or later. The download page also lists an older build for macOS 11. The installer is a `.pkg` file.

1. Open [nextcloud.com/install](https://nextcloud.com/install/) and download the macOS desktop client.
1. Double-click the `.pkg` file, click **Continue** and **Install**, enter your Mac's password when asked, then click **Close**.
1. Open **Nextcloud** from the Applications folder or Launchpad.
1. Enter `https://pc.your-tailnet.ts.net:1005`, continue, log in in the browser and click **Grant access**.
1. On the local folder screen, keep the default folder and finish. The second-copy warning from [part 2](#2-windows) applies here too.
1. Click the Nextcloud icon in the menu bar, then **Settings**, then **Add Folder Sync Connection**.
1. Pick your Documents folder. If macOS asks whether Nextcloud may access files in the Documents folder, click **Allow**.
1. Make a server folder called `Document sync` and finish.
1. In **General** settings, turn on the option to launch Nextcloud at login.

**Check for iCloud first.** If iCloud Drive is set to store your Desktop and Documents folders (in System Settings, under your Apple Account, then iCloud, though the wording changes between macOS versions), Apple is already syncing Documents. Don't sync the same folder with two tools. It's the same problem as OneDrive on Windows.

**About virtual files.** Nextcloud publishes a macOS build with virtual files, which adds a **Nextcloud** location to Finder's sidebar. I didn't use it. The steps above use the classic sync folders, which still work in that build but have no Finder icons.

**Check it:** the connection shows a green check, and `https://pc.your-tailnet.ts.net:1005` lists the `Document sync` folder with your files.

## 5. iPhone

**Install, sign-in and browsing are tested on my setup. Uploading follows Nextcloud's official instructions and I haven't tried it.**

**You need:** iOS 17.0 or later.

1. Open the App Store, search for **Nextcloud** and install the app from Nextcloud GmbH.
1. Turn on Tailscale on the iPhone and check that it's connected.
1. Open Nextcloud and enter the server address `https://pc.your-tailnet.ts.net:1005`.
1. Log in with your Nextcloud name and password, and allow access when the app asks.
1. The **Files** tab opens.

**Check it:** the **Files** tab lists the `Document sync` folder from your PC, with its size and when it last changed.

**Sending files from the phone.** Tap the **+** button at the bottom right of the Files tab and choose the option to upload files. Pick a file and it goes to the folder you have open. I haven't tested this and I haven't written out the menu names, because I haven't seen them on my phone.

**Limits.** As far as I could tell, the iPhone app doesn't keep a phone folder in sync with the server the way the desktop app does. Use the phone for browsing, opening files and uploading by hand. Photos and videos go to Immich. If the Nextcloud app shows photo auto upload settings, leave them off so you don't store every photo twice.

## 6. Android

**Not tested on my setup. This follows Nextcloud's official instructions.**

1. Install the Nextcloud app from Google Play (`com.nextcloud.client`), from F-Droid, or by downloading the APK from [nextcloud.com/install](https://nextcloud.com/install/).
1. Turn on Tailscale on the phone and check that it's connected.
1. Open the app, enter `https://pc.your-tailnet.ts.net:1005` and tap **Log in**. Log in in the browser and grant access.

**Check it:** the file list shows the `Document sync` folder from your PC.

**Sending files by hand.** Tap the **+** button and choose the option to upload files, then pick the files. The menu wording can differ between versions.

**Sending a folder automatically (auto upload).** The Android app can upload a folder from the phone on its own. The path below comes from a Nextcloud community forum thread, not from the official manual:

1. Open the app's **Settings**, then **Auto upload**.
1. Tap the three-dot menu and choose **Set up a custom folder**.
1. Pick the folder on the phone and the destination folder on the server.

Limits: it only uploads. Files that change on the server aren't copied back to the phone. On some phones it may only see photos and videos, because Android limits which files an app can read (one user reported this on Android 14). If background uploads stop, check the phone's battery settings, since they can pause apps. I leave the camera folder out, because Immich backs up photos and videos.

## 7. If it doesn't connect

- **The app says it can't reach the server.** Tailscale is off or disconnected on that device. Open Tailscale, connect, and try again.
- **The address is rejected.** It has to start with `https://`, end with `:1005` and have nothing after it. Use the Tailscale address on a phone or laptop that leaves the house. The local `http://192.168.X.X:8082` address only works at home, on the same network, and without `https` (see [build guide, section 11.2](build-guide.md#112-deploy-the-stack)).
- **The login fails a few times.** Nextcloud blocks an address after repeated failed logins (see [Security](security.md)). Wait a few minutes before you try again.
- **Files don't show up in the browser.** In the desktop app, open Settings and look for an error message under the connection. It names the file or the problem.
- **A folder won't sync because of an overlap.** Nextcloud's docs say a server folder can only sync to one local folder, and that the client can refuse a folder inside one that already syncs. On my setup the client accepted `Document sync` next to the main connection, but that's what made the second copy described in [part 2](#2-windows). Look at the connections list for the overlap and remove the one you don't need, using **Remove folder sync connection** from the three-dot menu. That stops syncing that folder.

Sync is not a backup. Deleting a file in a synced folder deletes it everywhere.
