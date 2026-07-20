# Observed hardware notes

This file records observed facts separately from integration assumptions.

## Foscam G4

- Model: Foscam G4
- Wired and Wi-Fi private-LAN addresses observed during setup; exact addresses
  remain in ignored local configuration
- HTTP service observed: port `88`
- HTTPS service observed: port `443`
- RTSP service observed: port `88` (shared with HTTP)
- RTSP `OPTIONS` handshake: successful
- Stream names `videoSub` and `videoMain`: authentication requested as expected
- Port `554`: not used by this camera's current configuration
- Firmware path observed during setup: `1.14.1.8_2.94.2.63`
- Final firmware observed in app: `1.14.1.8_2.94.2.67`
- Firmware status after incremental updates: app reports up to date
- Connection during setup: wired Ethernet
- Factory reset completed through the Foscam app to clear an unavailable legacy login
- New local camera administrator login created after reset; credentials not recorded here
- Local address after reset: reachable on the configured private-LAN HTTP port
- Dedicated HATI camera user: `hati_viewer`, Operator role
- HATI credential storage: Windows-user-bound encrypted CLIXML on D, ignored by Git
- RTSP substream verified: `videoSub`, 1280 x 720
- RTSP main stream verified: `videoMain`, 2304 x 1536
- First authenticated frame capture completed: 2026-07-13
- Browser Wi-Fi test for the configured 2.4 GHz extender network: successful;
  configuration saved
- Ethernet-to-Wi-Fi handoff verified through DHCP rediscovery
- Earlier negative subnet checks were invalid because the workspace sandbox denied
  local TCP connections; a permitted scan found the camera at `.206`
- Authenticated Wi-Fi snapshot verified: 1920 x 1080 JPEG
- RTSP `OPTIONS` succeeds over Wi-Fi; early one-frame OpenCV probes did not receive
  a clean H.264 keyframe, so authenticated JPEG was used for initial recovery
- Final coop Wi-Fi/extender placement field-tested on 2026-07-15; a real motion
  event was captured, classified, denied by human veto, and owner-reviewed
- Repeated JPEG requests took roughly 19 seconds per frame at the field link, so
  event capture now keeps one RTSP session open, discards startup frames, and
  continuously drains it; this replacement cadence still needs field validation
- The camera later dropped completely from Wi-Fi at the 97°F field placement;
  port 88 and the app were both unavailable, so HATI failed closed without a new
  event, inference call, or actuation

The `/videoSub` and `/videoMain` paths in local configuration are now verified.
No plaintext camera credentials are stored in the repository.

## Tuya scent mister

- Paired successfully in the Smart Life app
- Test liquid: water only
- Private-LAN address observed behind extender proxying; exact address remains
  in ignored local configuration
- Tuya LAN port observed open: TCP `6668`
- App controls observed: master power, weak/strong spray mode, independent RGB
  light, and separate cloud schedules for spray and light
- Spray schedule accuracy warning: approximately +/- 30 seconds; schedules are
  unsuitable for reactive bounded actuation
- Water-only manual test on 2026-07-14:
  - weak mode
  - visible mist began after approximately one second
  - output was continuous while powered
  - output stopped promptly when powered off after five seconds
- Tuya cloud project linked to the Smart Life account; private cloud credentials
  are stored in Windows-user-bound encrypted CLIXML and ignored by Git
- Cloud discovery identified the device as an ASAKUKI Smart Oil Diffuser,
  category `jsq`, model `100-DFGeneric`
- A 16-character LAN local key was retrieved and stored only in ignored local
  configuration
- Read-only local status succeeded using Tuya protocol `3.5`
- Baseline status exposed ten data points: `1`, `11`, `12`, `13`, `14`, `103`,
  `108`, `109`, `110`, and `111`
- First physical HATI command completed on 2026-07-14 with water only:
  - DP `1` was confirmed off, enabled for 5.2 seconds, disabled, and verified off
  - observed output was weak mist with multicolor illumination
  - this establishes DP `1` as the master run control
- Second bounded water test sampled the active state after 1.5 seconds:
  - DP `1`: `false` to `true` (master run control)
  - DP `103`: `off` to `small` (weak spray)
  - DP `11`: `false` to `true` (light enabled)
- Finished deterrence command: DP `1=true`, DP `103=big`, DP `11=true`, and the
  locally observed medium-blue RGB settings, followed by a maximum 300-second
  bounded delay, DP `1=false`, DP `11=false`, and verified shutdown
- No timberwolf formulation has been introduced
- TinyTuya `1.20.0` installed in the D-drive project environment
- Passive Tuya broadcast scan returned no device metadata
- Tuya's official `jsq` humidifier schema uses `large` for maximum mist, but this
  legacy unit was observed directly on 2026-07-18 using the device-specific enum
  `big`. While Smart Life Strong Mode was active, local status reported
  `DP 1=true`, `DP 103=big`, and `DP 11=true`; HATI then forced power and light
  off and verified both off.
- HATI first completed a two-second dark water-only validation. It then completed
  a second two-second water-only validation using `DP 1=true`, `DP 103=big`,
  `DP 11=true`, and the selected medium-blue setting. The device normalized the
  requested RGB `(0, 204, 255)` to `(6, 210, 249)`; HATI accepted that small
  device-side rounding, confirmed the active state, and then verified
  `DP 1=false`, `DP 11=false`, and `DP 103=off`.

Device IDs, local keys, cloud credentials, MAC addresses, and public IP addresses
must remain outside the repository and submission media.
