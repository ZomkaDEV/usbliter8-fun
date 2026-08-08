#!/usr/bin/env python3
"""Fetch and extract the firmware this port builds from.

Target: iPhone 11 (iPhone12,1 / n104ap), iOS 27.0 beta 4, build 24A5390f.

This is NOT upstream's get_fw.py. The b2/b3 version downloads
iPhone12,3,iPhone12,5 build 24A5380h, which is a different board AND a
different build. Running it here silently fetches the wrong firmware.

Follows the b2/b3 convention: the IPSW is downloaded into this work directory
and extracted into a sibling folder here, which make_cfw.py / get_boot.py /
get_rd.py then copy into CFW/.

The URL is resolved by the `ipsw` CLI from device + build rather than
hardcoded, because seed URLs rotate:

    brew install blacktop/tap/ipsw

After extraction the BuildManifest is checked, so a wrong or renamed archive
fails here instead of producing a subtly wrong CFW.

Two payloads inside are AEA encrypted. The build does NOT need them decrypted,
so this script leaves them alone. Decrypt only when pulling files out for
analysis; the keys for this build are public:

    094-13328-107.dmg.aea   root filesystem
        ei61kkuQ/ECeRytNoqaofHMtQUUHVovQMfKXpD9hR74=

    094-14805-111.dmg.aea   Cryptex1,SystemOS (holds the dyld_shared_cache)
        FsLQw9m+E0kTZMWw9av/qV8u/jvEwUIY4teP9CIQOJ0=

    ipsw fw aea --key-val 'base64:<key>' <file>.dmg.aea --output aea_out
    hdiutil attach -readonly -nobrowse -mountpoint /tmp/ios27-rootfs aea_out/<file>.dmg

Budget about 20 GB free: the root filesystem is 8.5 GB and the Cryptex 5.6 GB
once decrypted, on top of the IPSW itself.
"""

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

DEVICE = "iPhone12,1"
BUILD = "24A5390f"
VERSION = "27.0"
BOARD = "n104ap"

# Same shape as upstream's extracted folder name, e.g. b3 uses
# iPhone12,3,iPhone12,5_27.0_24A5380h_Restore. The build scripts reference this
# by exactly this relative name.
EXTRACT_DIR = f"{DEVICE}_{VERSION}_{BUILD}_Restore"

HERE = Path(__file__).resolve().parent


def run(*cmd):
    """Run a command, streaming output, and abort the script if it fails."""
    print(f"[*] {' '.join(cmd)}")
    if subprocess.call(cmd, cwd=HERE) != 0:
        sys.exit(f"[!] failed: {' '.join(cmd)}")


def verify_extracted(dest):
    """Prove the extracted tree is the firmware we expect, not merely present."""
    manifest = dest / "BuildManifest.plist"
    if not manifest.is_file():
        sys.exit(f"[!] {manifest} missing; extraction looks incomplete.")

    d = plistlib.load(manifest.open("rb"))
    got_build = d.get("ProductBuildVersion")
    got_types = d.get("SupportedProductTypes") or []
    got_boards = sorted({i.get("Info", {}).get("DeviceClass")
                         for i in d.get("BuildIdentities", [])})

    problems = []
    if got_build != BUILD:
        problems.append(f"ProductBuildVersion is {got_build!r}, expected {BUILD!r}")
    if DEVICE not in got_types:
        problems.append(f"SupportedProductTypes is {got_types}, expected to contain {DEVICE!r}")
    if BOARD not in got_boards:
        problems.append(f"DeviceClasses are {got_boards}, expected to contain {BOARD!r}")
    if problems:
        sys.exit("[!] wrong firmware extracted:\n    " + "\n    ".join(problems))

    print(f"[+] verified {DEVICE} / {BOARD} / {VERSION} ({BUILD})")


def main():
    if not shutil.which("ipsw"):
        sys.exit("[!] the `ipsw` CLI is required.\n"
                 "    brew install blacktop/tap/ipsw")

    dest = HERE / EXTRACT_DIR
    # A sentinel rather than a directory-existence check: a cancelled unzip leaves a
    # partial tree that an existence check would accept, and the build would then run
    # against a truncated IPSW.
    done = dest / ".extract-complete"
    if done.exists():
        print(f"[*] already extracted at {EXTRACT_DIR}, nothing to do")
        return

    archives = sorted(HERE.glob(f"*{BUILD}*.ipsw"))
    if not archives:
        run("ipsw", "download", "ipsw", "--device", DEVICE, "--build", BUILD, "--confirm")
        archives = sorted(HERE.glob(f"*{BUILD}*.ipsw"))
        if not archives:
            sys.exit(f"[!] no .ipsw for {DEVICE} {BUILD} found after download.\n"
                     f"    Check availability:\n"
                     f"      ipsw download ipsw --device {DEVICE} --build {BUILD} --urls")
    archive = archives[0]
    print(f"[*] using {archive.name}")

    dest.mkdir(parents=True, exist_ok=True)
    run("unzip", "-o", str(archive), "-d", str(dest))
    verify_extracted(dest)
    done.touch()

    print(f"[+] extracted to {EXTRACT_DIR}")
    print("[*] next: ./make_cfw.py, then ./restore_cfw.sh   (see README.md)")


if __name__ == "__main__":
    os.system(f"chmod +x '{HERE.parent}/tools/'*")
    main()
