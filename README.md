# HATI — Spectral Hound

[![Test HATI](https://github.com/musecase/hati-spectral-hound/actions/workflows/tests.yml/badge.svg)](https://github.com/musecase/hati-spectral-hound/actions/workflows/tests.yml)

HATI (Homestead Autonomous Threat Intervention) is a camera-triggered,
AI-assisted olfactory predator deterrent for a family poultry flock.

> Predators kept taking my chickens, so I used Codex to build an AI farm bouncer.

The safety boundary is deliberate:

**The vision model proposes an interpretation. Deterministic code authorizes physical action.**

HATI fails closed. Humans veto actuation, unknown observations cause no action,
multi-frame agreement is required, and every decision is recorded.

## Current state

The repository currently contains:

- human-readable JSON configuration with secrets supplied only by environment variables
- authenticated Foscam JPEG capture with RTSP fallback
- authenticated `/24` camera rediscovery when DHCP changes the address
- configurable normalized polygon zones and local frame-difference motion detection
- one-event watching with a pre-trigger frame and exactly five event frames
- one-request, five-frame GPT-5.6 Luna vision classification with structured output
  and recorded token usage
- typed event, observation, system-state, and decision records
- deterministic temporal consensus and authorization logic
- a real local Tuya 3.5 diffuser actuator with weak mode, forced-dark operation,
  a five-second hard cap, unconditional shutdown attempts, and off-state verification
- atomic local event storage and structured JSON logging
- simulated raccoon, human, chicken, and low-consensus event flows
- a one-command, no-hardware judge demo with inspectable sample cases
- Telegram event alerts, owner-only feedback, status and dry-run commands, and a
  bounded manual-deploy path
- an evaluation gate that promotes an improvement only when it fixes a known case
  with zero regressions
- 44 tests for camera discovery, motion zones, event capture, decision safety,
  Telegram control, evaluation promotion, and actuator failure handling
- a public, interactive judge site built with the OpenAI Sites production starter

The Foscam camera, first real motion event, GPT-5.6 Luna vision classification,
deterministic human veto, and water-only physical actuator are verified.
The Telegram integration is implemented and tested with a fake transport; live bot
registration is the remaining owner setup step. Hardware mode remains disarmed and
test mode remains enabled by default.

## Quick start

From PowerShell:

```powershell
.\scripts\setup.ps1
.\scripts\hati.ps1 demo all --config config\hati.example.json
.\scripts\hati.ps1 doctor --config config/hati.example.json
.\scripts\hati.ps1 evaluate-improvement --cases sample_data/improvement_cases.json
.\scripts\test.ps1
```

The demo exercises predator consensus, the human veto, resident-animal safety,
low-consensus denial, and dry-run actuation. It needs no camera, API key, local
network, or physical hardware, and writes inspectable JSON traces beneath
`data/demo_runs/`. Runtime traces are ignored by Git by default.
The published synthetic cases are in
[sample_data/eval_cases.json](sample_data/eval_cases.json).

The PowerShell helpers locate the installed Python runtime and set the source path
automatically. `setup.ps1` installs the pinned dependencies into the project-local
virtual environment inside the checkout.

Capture one authenticated substream frame. Without an encrypted local credential,
the command uses a password prompt that does not echo or store the value:

```powershell
.\scripts\hati.ps1 camera-probe --config config/hati.local.json --username hati_viewer
```

The probe uses the camera's authenticated JPEG endpoint first and retains RTSP as
a fallback. This avoids long H.264 startup delays on the G4's 2.4 GHz link.

Watch until one real motion event is captured, then stop:

```powershell
.\scripts\hati.ps1 watch --config config/hati.local.json
```

The command verifies or rediscovers the authenticated camera, captures a baseline,
measures changed pixels only inside the configured polygon, and saves one five-frame
event beneath `data/events/`. It does not call a model or actuator.

Classify one captured event in one paid five-image request, then run the saved
observations through deterministic authorization as a separate local-only step:

```powershell
.\scripts\hati.ps1 classify-event --config config/hati.local.json --event data/events/EVENT_ID/event.json
.\scripts\hati.ps1 decide-event --config config/hati.local.json --event data/events/EVENT_ID/event.json
```

The classifier refuses already-classified events to prevent accidental duplicate
API charges. `decide-event` never invokes the actuator.

The ASAKUKI/Tuya diffuser was mapped from observed water-only tests. Its private
device ID and LAN key live only in the ignored `config/tuya-device.json`. The
public example configuration uses `dry_run`; selecting `tuya_diffuser` does not
arm HATI. Physical action still requires the deterministic authorization boundary
and `runtime.armed: true`.

For repeatable local operation, save the camera credential with Windows user-bound
encryption. The encrypted file stays on D and is ignored by Git:

```powershell
.\scripts\save-camera-credential.ps1
```

## Local configuration

1. Copy `config/hati.example.json` to `config/hati.local.json`.
2. Adjust non-secret values in the local file.
3. Set camera credentials in the environment:

```powershell
$env:HATI_CAMERA_USERNAME = "your-camera-user"
$env:HATI_CAMERA_PASSWORD = "your-camera-password"
```

Do not put credentials in a stream URL stored in configuration, documentation,
logs, screenshots, or commits.

See [docs/CAMERA_SETUP.md](docs/CAMERA_SETUP.md) for the first hardware session.
See [docs/VISION_SETUP.md](docs/VISION_SETUP.md) for the model, credential, and
verified first-run details.
See [docs/TELEGRAM_SETUP.md](docs/TELEGRAM_SETUP.md) for owner alerts, feedback,
safe testing, and bounded manual deployment.
See [docs/DEMO_PLAN.md](docs/DEMO_PLAN.md) for the honest plush, replay, and
water-only demonstration sequence. See
[docs/BUILT_WITH_CODEX.md](docs/BUILT_WITH_CODEX.md) for the GPT-5.6/Codex
development narrative and key decisions.

## Product sequence

**SEE → IDENTIFY → VERIFY → ACT → REVIEW**

Codex builds. Luna sees. HATI decides. The hound acts.

## License

HATI is released under the [MIT License](LICENSE).
