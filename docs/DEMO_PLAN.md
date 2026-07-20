# Honest demo plan

The demo separates repeatable engineering evidence from live-wildlife luck. No
animal should be lured for the presentation.

## 1. Judge-runnable safety demo

Run:

```powershell
.\scripts\hati.ps1 demo all --config config\hati.example.json
```

This uses synthetic observations and no camera, API key, network, or physical
actuator. It should show:

- raccoon consensus: authorize, then call only the dry-run actuator;
- human present: deny with `HUMAN_VETO`;
- chickens only: deny;
- weak predator consensus: deny.

Every result writes an inspectable JSON trace under `data/demo_runs/`.

## 2. Threat Actor (Plush)

Borrowed stuffed wildlife is a physical false-positive and motion-pipeline test.
Its ground truth is **non-live decoy**, not predator. A safe result is `unknown`
or another non-authorizing label. If it is mislabeled as a predator, tap `False
alarm` while the continuous operator link is running. HATI will queue a
conservative prompt candidate in the background, rerun the source and protected
real events, and promote only after the miss is corrected with zero regressions.
It must not be
presented as a successful wildlife detection. If the initial plush classification
is already safe, record that result honestly and use the controlled improvement
fixture to demonstrate the gate.

## 3. Positive vision test

Use recorded raccoon footage or clearly licensed raccoon images displayed in the
camera's view. Label this as replayed media. It demonstrates the five-frame model
path without pretending a wild raccoon arrived on schedule.

## 4. Controlled actuator proof

Use water only, indoors or in a safely contained setup. Demonstrate the diffuser
control followed by verified shutdown. The finished configuration uses full mist,
a medium-blue status light, and a five-minute maximum; the edited submission
video does not need to linger for the entire interval. Keep the device disarmed
for all other steps.

## Suggested presentation order

1. Show the family-and-flock problem and conservation motivation.
2. Run the four-case hardware-free safety demo.
3. Show a real camera event and its saved five-frame trace.
4. Run the replayed positive vision test and identify it honestly.
5. Demonstrate the water-only mister loop.
6. Show the Telegram alert, tap one feedback label, and run `/status` or `/test`.
7. Tap `False alarm` to show the queued background check, or use
   `evaluate-improvement` to show the controlled 3/4 → 4/4 zero-regression gate.
8. Close with the human veto, fail-closed rules, and owner-controlled learning loop.

## Verified outdoor safety sequence

Use the July 15 owner-pass event as the primary real evidence. Label it **REAL
OUTDOOR EVENT**. Show the five-frame strip: four empty views followed by one clear
human frame. Then show the structured GPT-5.6 labels, `DENY / HUMAN_VETO`, the
Telegram alert, and the stored `correct` feedback. This is a stronger safety proof
than a staged positive detection because one human observation overrides every
possible predator interpretation.

Do not include identifiable children or private household footage in the public
repository or submission media without appropriate consent.

## Complete production command

The finished runtime continuously watches, processes, notifies, and recovers:

```powershell
.\scripts\start-hati.ps1
```

The same launcher selects disarmed or armed operation. For the video, select
disarmed first. A water-only live actuator demonstration should be a deliberate,
separately filmed armed start requiring the exact `ARM HATI` confirmation.
Ctrl+C stops the supervisor. Every actuator attempt is reserved before dispatch,
so a restart cannot repeat an uncertain command.
