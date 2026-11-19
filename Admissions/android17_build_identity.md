# Android Emulator Build Identity Audit

Target: `emulator-5554`
Audit time: 2026-11-14T12:44:47Z to 2026-11-14T12:45:18Z (UTC)
Mode: read-only. Only `adb devices`, `adb shell getprop`, `find`, `ls`, `readelf -n`, `sha256sum`, `cat /proc/version`, `pidof`, and `grep /proc/<pid>/maps` were run. No install, update, restart, or configuration change was made. No experiment was started.

Labels: VERIFIED (read from the device in this audit), UNKNOWN (not determined).

---

## 1. Connection

Command (12:44:47Z):

```
which adb
adb version
adb devices -l
adb -s emulator-5554 get-state
```

Output:

```
/Users/lishuandysun/Downloads/platform-tools/adb
Android Debug Bridge version 1.0.41
Version 37.0.1-15733141
List of devices attached
emulator-5554          device product:sdk_phone64_arm64 model:Android_SDK_built_for_arm64 device:emu64a transport_id:3
device
```

VERIFIED: `emulator-5554` is connected and in the `device` state. The earlier audit (before this one) found it offline, so the emulator was restarted or reconnected between the two audits.

---

## 2. Build Properties

Command (12:45:02Z): `adb -s emulator-5554 shell getprop <name>` for each property.

| Property | Value |
|---|---|
| ro.build.fingerprint | `Android/sdk_phone64_arm64/emu64a:17/CE2A.260420.051.A3/16571990:userdebug/test-keys` |
| ro.build.version.release | `17` |
| ro.build.version.sdk | `37` |
| ro.build.id | `CE2A.260420.051.A3` |
| ro.build.type | `userdebug` |
| ro.build.tags | `test-keys` |
| ro.product.cpu.abi | `arm64-v8a` |
| ro.product.manufacturer | `unknown` |
| ro.product.model | `Android SDK built for arm64` |
| ro.build.version.security_patch | `2026-08-05` |
| ro.build.version.incremental | `16571990` |
| ro.system.build.fingerprint | `Android/generic_system/generic:17/CE2A.260420.051.A3/16571990:userdebug/test-keys` |
| ro.vendor.build.fingerprint | `Android/sdk_phone64_arm64/emu64a:17/CE2A.260420.051.A3/16571990:userdebug/test-keys` |
| ro.product.name | `sdk_phone64_arm64` |
| ro.product.device | `emu64a` |
| ro.hardware | `ranchu` |
| ro.kernel.qemu | `1` |

VERIFIED: The build fingerprint is read directly from `ro.build.fingerprint`. It is not inferred from the Android version.

Kernel (`cat /proc/version`): `Linux version 6.12.81-android16-6-g4f69fc7b210c-ab16167562-4k ... #1 SMP PREEMPT Tue Aug 25 07:36:40 UTC 2026`

VERIFIED: The `adb` shell reports one fingerprint for the vendor and product partitions, and the same build ID and incremental number for the system partition.

---

## 3. Audio Library Locations

Command (12:45:02Z):

```
find /system /apex /vendor /system_ext /product -name "<name>"
```

Output for the three requested names:

```
/system/lib64/libOpenSLES.so
/system/lib64/libaudioclient.so
```

`libaudioflinger.so` was not found under those paths. A broad search (12:45:11Z) with `find / -xdev -name "libaudioflinger*"` returned:

```
/system/lib64/libaudioflinger_datapath.so
/system/lib64/libaudioflinger_fastpath.so
/system/lib64/libaudioflinger_timing.so
/system/lib64/libaudioflinger_utils.so
```

VERIFIED: On this image, AudioFlinger code is split across `libaudioflinger_*.so` modules. There is no standalone `libaudioflinger.so`. The core AudioFlinger module that defines `createTrack_l` was not located by name in this audit, so its build ID is UNKNOWN.

---

## 4. Sizes, Modification Times, Build IDs, Hashes

Command (12:45:02Z): `ls -l` on each library.

| Library | Path | Size (bytes) | mtime (device) |
|---|---|---|---|
| libOpenSLES.so | /system/lib64/libOpenSLES.so | 35896 | 2026-10-12 14:13 |
| libaudioclient.so | /system/lib64/libaudioclient.so | 553160 | 2026-10-12 13:49 |
| libaudioflinger_datapath.so | /system/lib64/libaudioflinger_datapath.so | 51872 | 2026-10-12 14:13 |
| libaudioflinger_fastpath.so | /system/lib64/libaudioflinger_fastpath.so | 85528 | 2026-10-12 14:13 |
| libaudioflinger_timing.so | /system/lib64/libaudioflinger_timing.so | 35368 | 2026-10-12 14:13 |
| libaudioflinger_utils.so | /system/lib64/libaudioflinger_utils.so | 52648 | 2026-10-12 14:13 |

Command (12:45:11Z): `readelf -n <lib>` and `sha256sum <lib>`.

Output, `libOpenSLES.so`:

```
Displaying notes found in: .note.gnu.build-id
  Owner                 Data size       Description
  GNU                  0x00000010       NT_GNU_BUILD_ID 4f9b436de4a0a3b0a1f1886a2c6e44d0
```

Output, `libaudioclient.so`:

```
Displaying notes found in: .note.gnu.build-id
  Owner                 Data size       Description
  GNU                  0x00000010       NT_GNU_BUILD_ID d5e03623b0ca530f899f320ba7c9811d
```

SHA-256:
- `libOpenSLES.so`: `771ca94c10f7103d0f4e9a966f847d03c83327ac8db6ff2bc528cd36d899bdcc`
- `libaudioclient.so`: `0189039cd976a25deb1cfed6210932540f07b9719b53958b6671f04841f8bea1`

VERIFIED: GNU build IDs for both libraries are as listed above. Both libraries have `.note.android.ident` with API level 37.

Build IDs for `libaudioflinger_*.so`: UNKNOWN (not read in this audit).

---

## 5. Symbols and Debug Information

Command (12:45:11Z): `readelf -S` for debug sections.

Output:

```
/system/lib64/libOpenSLES.so
  [23] .gnu_debugdata    PROGBITS   (size 0x110)
/system/lib64/libaudioclient.so
  [27] .gnu_debugdata    PROGBITS   (size 0x2848)
```

VERIFIED: Both libraries contain only `.gnu_debugdata` (MiniDebugInfo, a compressed symbol table). No `.debug_*` sections and no `.gnu_debuglink` were found. Full DWARF debug info is not present on the device.

UNKNOWN: Whether matching symbol files are available from the AOSP symbol server or a build artifact. The AOSP source is needed for that. No local copy exists (see section 7).

---

## 6. Audioserver Process

Command (12:45:18Z): `pidof audioserver` and `grep` on `/proc/<pid>/maps`.

Output:

```
509
grep: /proc/509/maps: Permission denied
```

VERIFIED: The audioserver PID is 509 now. The November 14 log (raw_logs.txt, lines 23846 to 24615) shows AudioFlinger PID 506. The PID changed between the experiment and this audit, so audioserver was restarted after the experiment (or the device was rebooted). The mapped library list could not be read, because `/proc/509/maps` is not accessible to the shell user.

Consequence: this audit cannot confirm which library images audioserver had loaded during the experiment.

---

## 7. Source Selection

Local AOSP tree: not present in `~/aosp` or `~/android` (checked in the prior audit). Not re-checked here.

Matching source: the fingerprint is `Android/sdk_phone64_arm64/emu64a:17/CE2A.260420.051.A3/16571990:userdebug/test-keys`. The build ID is `CE2A.260420.051.A3`, and the incremental number is `16571990`. An AOSP tag or manifest matching this build ID must be obtained. No such source is available locally, and no network lookup was done in this audit.

---

## 8. Limitations

- The fingerprint read on 12:45Z is the current device state. It is not proven to be the same image that ran during the November 14 experiment at 12:19Z (UTC). The PID change (506 to 509) shows a restart, but not a change of system image. Confirm with the emulator's AVD or image history, or re-check the fingerprint against the experiment's `sessions.json` device record.
- The experiment's `sessions.json` device record uses the model string `Android SDK built for arm64` and Android 17. It does not record the fingerprint.
- `libaudioflinger.so` was not present. The module that defines `createTrack_l` is not identified.
- `/proc/509/maps` is not readable, so loaded libraries cannot be checked.

---

## 9. Result

- Fingerprint: `Android/sdk_phone64_arm64/emu64a:17/CE2A.260420.051.A3/16571990:userdebug/test-keys` (VERIFIED on the device at 12:45Z).
- libOpenSLES.so GNU build ID: `4f9b436de4a0a3b0a1f1886a2c6e44d0` (VERIFIED).
- libaudioclient.so GNU build ID: `d5e03623b0ca530f899f320ba7c9811d` (VERIFIED).
- libaudioflinger_*.so build IDs: UNKNOWN.
- Matching AOSP source can be selected by build ID `CE2A.260420.051.A3` (incremental `16571990`). It is not available in the workspace, so it cannot be used yet.
