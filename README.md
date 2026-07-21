# HATI — Spectral Hound

[![Test HATI](https://github.com/musecase/hati-spectral-hound/actions/workflows/tests.yml/badge.svg)](https://github.com/musecase/hati-spectral-hound/actions/workflows/tests.yml)

[Interactive judge site](https://hati-spectral-hound.amarygma.chatgpt.site) ·
[Public repository](https://github.com/musecase/hati-spectral-hound)

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
- low-latency continuous Foscam RTSP capture with startup warmup and authenticated
  JPEG fallback
- authenticated `/24` camera rediscovery when DHCP changes the address
- configurable normalized polygon zones and local frame-difference motion detection
- one-event watching with a pre-trigger frame and exactly five event frames
- staged GPT-5.6 Luna vision classification: frames 2 and 4 screen ordinary events;
  only uncertain or threat-like events send frames 1, 3, and 5 for the original
  four-of-five authorization rule; request, image, and token usage are recorded
- an LM Studio/Gemma 4 E4B local gate with bounded `clear` / `likely` /
  `uncertain` output; the owner deployment may suppress Luna only for a clear
  resident-bird event or a clear/likely human veto, and can never authorize action
- one continuous `supervise` runtime connecting motion capture, vision,
  deterministic policy, bounded actuation, audit storage, Telegram review, and
  automatic recovery; `run-once` remains available for controlled demonstrations
- typed event, observation, system-state, and decision records
- deterministic temporal consensus and authorization logic
- a real local Tuya 3.5 diffuser actuator with configurable mist strength and
  optional observed RGB settings, a five-minute hard cap, unconditional shutdown
  attempts, active-state confirmation, and off-state verification
- atomic local event storage and structured JSON logging
- simulated raccoon, human, chicken, and low-consensus event flows
- a one-command, no-hardware judge demo with inspectable sample cases
- Telegram event alerts, owner-only feedback, status and dry-run commands, and a
  bounded manual-deploy path
- restart-safe actuation reservations and cooldown reconstruction from durable event
  traces, preventing command replay after a crash or restart
- a feedback-driven learning path that protects confirmed behavior, queues only
  conservative false-alarm prompt candidates in the background, reruns bounded real
  event frames, and promotes only after a correction with zero protected-case
  regressions
- 100+ tests for camera discovery, motion zones, event capture, continuous recovery,
  decision safety,
  Telegram control, evaluation promotion, and actuator failure handling
- a public, interactive judge site built with the OpenAI Sites production starter

The final coop view has completed a real outdoor owner-pass loop: motion capture,
one five-image GPT-5.6 Luna request, deterministic `HUMAN_VETO`, Telegram photo
alert, and owner `correct` feedback stored in the event trace. The water-only
physical actuator is also verified.
The live Telegram owner link has completed authenticated `/status` and feedback
round trips.
Its restart-safe poller stores only the last processed update ID locally; secrets
remain Windows-user encrypted and ignored by Git. Hardware mode remains disarmed
and test mode remains enabled by default.

## Quick start

From PowerShell:

```powershell
.\scripts\setup.ps1
.\scripts\hati.ps1 demo all --config config\hati.example.json
.\scripts\hati.ps1 doctor --config config/hati.example.json
.\scripts\hati.ps1 evaluate-improvement --cases sample_data/improvement_cases.json
.\scripts\learn-from-latest-event.ps1
.\scripts\start-hati.ps1
.\scripts\test.ps1
```

The demo exercises predator consensus, the human veto, resident-animal safety,
low-consensus denial, and dry-run actuation. It needs no camera, API key, local
network, or physical hardware, and writes inspectable JSON traces beneath
`data/demo_runs/`. Runtime traces are ignored by Git by default.
The published synthetic cases are in
[sample_data/eval_cases.json](sample_data/eval_cases.json).

While the continuous Telegram operator link is running, `False alarm` feedback
durably queues a single background improvement job. HATI proposes only the audited
conservative observer safeguard, reruns the source frames and up to three protected
real events, records at most four token-bounded five-frame model calls, and writes
an active policy only when the miss is corrected with zero regressions. Telegram
reports whether the candidate was promoted or rejected. Correct feedback becomes a
protected regression example without a model call.

`learn-from-latest-event.ps1` remains the explicit recovery/manual-review path.
Missed-threat feedback cannot enter the automatic queue or loosen actuation. The
human veto and deterministic authorization boundary are never editable by either
path.

The optional local Gemma gate is intentionally experimental. Its first
saved-event benchmark matched a poultry event and a human event but confidently
misread a replayed raccoon as chicken. Shadow mode caught the unsafe skip. A
neutral follow-up prompt plus bounded `clear` / `likely` / `uncertain` certainty
correctly triaged the same three protected events, but that set is far too small
to justify broad trust. The owner deployment now enables one narrow suppression:
one `clear` chicken or goose can skip Luna only when every other frame is also a
clear resident bird or clearly empty. A `clear` or `likely` human also suppresses
Luna as a local human veto. An uncertain human, mammal, unknown, contradictory
frame, or local failure still calls Luna. Gemma can suppress a paid call but can
never authorize the diffuser. The public example remains disabled and in shadow
mode. See
[the local-gate evidence](docs/LOCAL_GATE.md).

When Gemma escalates, Luna first sees event frames 2 and 4. Two confident benign,
empty, resident-animal, or human observations end the event without sending the
remaining images. Any predator, unknown, unusable frame, low-confidence result, or
disagreement sends frames 1, 3, and 5. Only the combined five-frame result can reach
the deterministic four-vote authorization rule; the two-frame screen can only deny.

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

Run the complete live path for one motion event, then stop:

```powershell
.\scripts\hati.ps1 run-once --config config/hati.local.json
```

`run-once` captures exactly one event, makes at most one vision request, applies
the deterministic authorization boundary, conditionally invokes the bounded
actuator, saves the complete audit trace, and sends the result to Telegram. It
remains harmless with the checked-in defaults (`armed: false`, `test_mode: true`).
Before any authorized actuator call, HATI persists an `actuating` reservation;
after a crash or restart, that event is never replayed. Cooldown is reconstructed
from earlier event traces instead of living only in process memory.

For normal operation, run `scripts\start-hati.ps1`. It starts the same continuous
supervisor in either disarmed or armed mode. Disarmed mode performs the complete
observation, decision, audit, and Telegram path while locking out physical action.
Armed mode requires the exact operator confirmation `ARM HATI`; an authorized
predator consensus may then run the configured physical actuator. Camera failures
are retried, processing resumes from the same saved event, Telegram feedback is
polled concurrently, and Ctrl+C stops the supervisor.

The finished diffuser configuration is medium-agnostic: `spray_mode: "big"` and
`burst_seconds: 300` mean full mist for at most five minutes. Water is used during
field validation; changing the reservoir contents does not change HATI's software.
Lights remain forced off, shutdown is attempted unconditionally, and successful
completion requires an off-state readback.

Classify one captured event in one paid five-image request, then run the saved
observations through deterministic authorization as a separate local-only step:

```powershell
.\scripts\hati.ps1 classify-event --config config/hati.local.json --event data/events/EVENT_ID/event.json
.\scripts\hati.ps1 decide-event --config config/hati.local.json --event data/events/EVENT_ID/event.json
```

The classifier refuses already-classified events to prevent accidental duplicate
API charges. `decide-event` never invokes the actuator.

To safely resume an existing captured or classified event through the same
production pipeline, use:

```powershell
.\scripts\hati.ps1 process-event --config config/hati.local.json --event data/events/EVENT_ID/event.json
```

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

## Collaboration with Codex

As a noncoder, I relied heavily on Codex for the implementation of this project:
I personally wrote 0% of the code, and I did not use another coding assistant
such as Claude, Gemini, or Kimi. The entire codebase was developed through Codex.
I collaborated with GPT-5.6-Sol in ChatGPT on the initial design and requirements,
then used its handoff documents to begin building with Codex. HATI also uses
GPT-5.6-Luna through the API as its remote visual interpreter.

My role was in identifying the problem, developing the design and behavioral
logic, making decisions, red-teaming the system, assembling and repairing the
hardware, extending the Wi-Fi network, and conducting field tests. Codex handled
the architecture, implementation, tests, documentation, debugging, and deployment
while checking with me whenever decisions or permissions were required. ChatGPT
even helped me select a better Wi-Fi setup and correctly repair the diffuser
wiring after mice ate through it.

I had a lot of fun building HATI, and the completed system functions as I
intended. More importantly, this project showed me that not knowing how to code
does not mean I cannot make useful things with code. I look forward to seeing
what I can build next.

## Product sequence

**SEE → IDENTIFY → VERIFY → ACT → REVIEW**

Codex builds. Luna sees. HATI decides. The hound acts.

## License

HATI is released under the [MIT License](LICENSE).
