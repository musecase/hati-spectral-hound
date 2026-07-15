# Foscam G4 first hardware session

The first objective is intentionally narrow:

> HATI sees movement near the coop and creates a usable event record.

Do not configure model inference or actuation during this session.

## Before connecting

- Power the camera indoors first.
- Connect it to the same local network as the HATI laptop.
- Give it a unique, non-default password.
- If the camera supports a dedicated local user, create one for HATI with only
  the permissions it needs.
- Record the camera IP address privately.
- Do not paste a credential-bearing RTSP URL into chat, source files, screenshots,
  terminal history intended for sharing, or Git.

## Information to collect

- camera IP address
- local RTSP port
- confirmed low-bandwidth stream path
- confirmed high-quality stream path
- resolution and frame rate of each stream
- whether the camera IP remains stable after a reboot

Foscam devices commonly expose `videoSub` and `videoMain` paths, but the exact
G4 configuration must be observed rather than assumed. The example config uses
those names only as placeholders.

## Safe local configuration

Copy `config/hati.example.json` to the ignored file `config/hati.local.json` and
put only the host, port, and verified paths there. Supply the username and
password through `HATI_CAMERA_USERNAME` and `HATI_CAMERA_PASSWORD` environment
variables.

## Acceptance check

Milestone 1 is complete only when all of these are true:

1. The local snapshot or low-bandwidth stream source can be opened reliably.
2. A configurable polygon covers the intended coop approach.
3. Walking through that polygon creates exactly one event rather than a storm of
   duplicate events.
4. The event contains several timestamped, usable frames.
5. The event trace explains why capture started and where its files live.
6. No secrets appear in the trace or logs.

Run the one-event acceptance check with:

```powershell
.\scripts\hati.ps1 watch --config config/hati.local.json
```

The watcher includes the frame immediately before the trigger so a fast animal
cannot leave the scene before all evidence is captured. It stops after one event;
continuous operation and event cooldown behavior are separate acceptance work.

Observed indoor acceptance result on 2026-07-14: a controlled human doorway pass
caused a 7.30% zone change and produced one five-frame event with an inspectable
trace. This is an indoor engineering test, not a coop field result.

## Field-of-view notes

Prefer a view that makes an approaching animal cross the protected zone for
several frames. Avoid pointing the motion zone at waving vegetation, roads,
reflective water, or the full chicken run. The chickens are residents, not an
endless supply of motion events.
