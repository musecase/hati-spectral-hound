# Built with GPT-5.6 and Codex

HATI is a collaboration between Robyn, a first-time hackathon builder who does
not write code, and Codex running GPT-5.6 Sol High. Robyn supplied the problem,
field knowledge, product judgment, hardware, physical observations, safety
constraints, and a vigorous red-team instinct. Codex translated those decisions
into a tested Python system and helped diagnose the camera, network, vision, and
actuator integrations.

The application itself uses GPT-5.6 Luna for bounded five-frame visual
classification. Luna proposes labels and confidence; it never authorizes a
physical action. Deterministic Python code applies the safety policy.

## Where Codex accelerated the work

- Turned a plain-language project brief into typed events, configuration,
  decision rules, tests, operator scripts, and submission documentation.
- Diagnosed a misleading camera-network failure, added authenticated DHCP
  rediscovery, and selected snapshot-first capture after RTSP stalled on the
  camera's Wi-Fi link.
- Built local polygon motion detection, a pre-trigger buffer, and exactly five
  captured frames per event.
- Used official OpenAI documentation to choose a cost-bounded model call,
  structured output, explicit image detail, token accounting, and duplicate-call
  protection.
- Mapped the Tuya diffuser from water-only observations and implemented weak,
  dark, time-capped activation with unconditional shutdown and off verification.
- Continuously converted physical tests and red-team questions into regression
  tests and fail-closed behavior.

## Key decisions made together

| Decision | Why it matters |
| --- | --- |
| Five frames and four predator votes | A single blurry frame cannot trigger action. |
| Human in any frame is an absolute veto | Predator consensus can never override a person. |
| Model proposes; code decides | Generative output is kept outside the authorization boundary. |
| Unknown, missing, duplicate, or unusable evidence fails closed | Uncertainty produces no physical action. |
| One API request per event | Bounds cost and leaves an auditable inference trace. |
| Weak, dark, maximum five-second burst | Minimizes disturbance and prevents an unbounded mister run. |
| Disarmed and dry-run by default | Setup and judging do not unexpectedly operate hardware. |
| Learning is offline and evaluation-gated | The live system cannot rewrite its own safety boundary. |
| Secrets and real household media stay local | The public repository remains reproducible without exposing a family or network. |

## Verified milestones

- Foscam authenticated capture and Wi-Fi rediscovery were verified on July 13,
  2026.
- A real five-frame indoor motion event was captured on July 14, 2026.
- GPT-5.6 Luna classified that event in one request. A human appeared in four
  frames, and the deterministic local decision produced `DENY / HUMAN_VETO`.
- The Tuya diffuser completed bounded water-only tests in weak, dark mode and was
  verified off afterward.
- The public judge demo exercises authorization and dry-run actuation without a
  camera, API key, network, or physical device.

## Honest current limitations

The final coop placement has not yet been field-tested, and HATI has not claimed
a live wildlife detection. Plush and replay tests are labeled as controlled
tests, not proof of real-world accuracy. Notifications and a judge-facing UI are
future work. These limits are kept explicit so the demo shows what was actually
built rather than what the ghost dog merely aspires to haunt.
