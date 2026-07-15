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
or another non-authorizing label. If it is mislabeled as a predator, that is a
useful red-team failure to add to the evaluation set; it must not be presented as
a successful wildlife detection.

## 3. Positive vision test

Use recorded raccoon footage or clearly licensed raccoon images displayed in the
camera's view. Label this as replayed media. It demonstrates the five-frame model
path without pretending a wild raccoon arrived on schedule.

## 4. Controlled actuator proof

Use water only, indoors or in a safely contained setup. Demonstrate one weak,
dark, bounded burst followed by verified shutdown. Keep the device disarmed for
all other demo steps.

## Suggested presentation order

1. Show the family-and-flock problem and conservation motivation.
2. Run the four-case hardware-free safety demo.
3. Show a real camera event and its saved five-frame trace.
4. Run the replayed positive vision test and identify it honestly.
5. Demonstrate the water-only mister loop.
6. Show the Telegram alert, tap one feedback label, and run `/status` or `/test`.
7. Run `evaluate-improvement` and show the 3/4 → 4/4, zero-regression gate.
8. Close with the human veto, fail-closed rules, and owner-controlled learning loop.

Do not include identifiable children or private household footage in the public
repository or submission media without appropriate consent.
