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
- Diagnosed a misleading camera-network failure and added authenticated DHCP
  rediscovery. Snapshot-first capture recovered a clean image, then the first
  outdoor event exposed 19-second snapshot latency; Codex replaced repeated
  requests with a continuously drained RTSP session and keyframe warmup.
- Built local polygon motion detection, a pre-trigger buffer, and exactly five
  captured frames per event.
- Used official OpenAI documentation to choose a cost-bounded model call,
  structured output, explicit image detail, token accounting, and duplicate-call
  protection.
- Mapped the Tuya diffuser from water-only observations and implemented
  configurable, time-capped activation with an observed medium-blue light,
  active-state confirmation, unconditional shutdown, and off verification.
- Built the Telegram owner loop: photo alerts, review labels, status, dry-run
  testing, and a separate authenticated manual-deploy path.
- Added a loopback-only Gemma 4 E4B gate after field activity exposed avoidable
  repeated calls. Its first shadow benchmark matched poultry and people but
  exposed a dangerous raccoon-as-chicken error. Removing a poultry hint and
  adding bounded `clear` / `likely` / `uncertain` output corrected the protected
  rerun. The owner then enabled only two benign suppressions: a clear resident
  bird with no contradictory panel, or a clear/likely human veto. Gemma can save
  a Luna call but can never authorize the diffuser.
- Connected capture, GPT vision, deterministic authorization, bounded actuation,
  durable audit storage, and Telegram review behind one restart-safe command.
- Converted a red-team question about crashes into a pre-dispatch `actuating`
  reservation and persistent cooldown reconstruction, so restarting cannot replay
  an uncertain physical command.
- Turned “show one real improvement” into a feedback-derived, versioned prompt
  candidate and regression gate instead of allowing the live system to rewrite
  itself. Correct reviews protect behavior; only conservative false-alarm rules
  can be proposed automatically; more permissive changes require manual review.
- Built and deployed an interactive judge experience, public CI, and submission
  documentation from the same verified event records and tests.
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
| Persist intent before actuator dispatch | A crash may lose one spray, but can never replay it. |
| Rebuild cooldown from event traces | Restarting the program cannot erase rate limits. |
| Full mist, medium-blue status light, maximum five-minute run | Makes activation visible while preserving a strict upper bound and verified shutdown. |
| Disarmed and dry-run by default | Setup and judging do not unexpectedly operate hardware. |
| Learning is offline and evaluation-gated | The live system cannot rewrite its own safety boundary. |
| Local Gemma may suppress only narrow benign cases | A local model can save paid calls but can never create permission to actuate. |
| Secrets and real household media stay local | The public repository remains reproducible without exposing a family or network. |

## Verified milestones

- Foscam authenticated capture and Wi-Fi rediscovery were verified on July 13,
  2026.
- A real five-frame indoor motion event was captured on July 14, 2026.
- GPT-5.6 Luna classified that event in one request. A human appeared in four
  frames, and the deterministic local decision produced `DENY / HUMAN_VETO`.
- The Tuya diffuser completed bounded water-only tests and was verified off
  afterward. The finished contract uses the locally observed `big` mist enum, an
  observed medium-blue RGB setting, and a 300-second maximum.
- The public judge demo exercises authorization and dry-run actuation without a
  camera, API key, network, or physical device.
- The controlled improvement fixture corrects one plush-decoy error, moves from
  3/4 to 4/4, and records zero regressions. It demonstrates the promotion
  mechanism, not live-wildlife accuracy.
- The July 16 reviewed hand event is the first real protected regression case. A
  real candidate promotion still awaits an owner-reviewed false alarm, such as
  the plush test.
- The final coop view triggered a real outdoor event on July 15. GPT-5.6 Luna
  labeled four empty frames and one human frame; deterministic code produced
  `DENY / HUMAN_VETO`.
- The live owner-only Telegram bot delivered that event and stored Robyn's
  `correct` feedback beside its inference and decision trace. The encrypted bot
  credential never entered source control.
- The production continuous supervisor, one-event demonstration path,
  feedback-derived learning gate, and restart behavior are covered by 95 local
  tests.

## Honest current limitations

HATI has not claimed a live wildlife detection. Plush, replay, and improvement
fixtures are labeled as controlled tests, not proof of real-world accuracy. The
feedback-driven learning path is implemented and tested, but no real prompt
candidate has yet been promoted because the reviewed field classifications have
been correct. The controlled 3/4 to 4/4 fixture proves the deterministic gate,
while the planned plush false alarm provides the honest live candidate test. The
first outdoor pass also revealed that repeated JPEG snapshots were too slow;
continuous RTSP corrected that capture path, while a longer unattended field run
and a broader night-event set remain future validation. The judge site still
needs the finished public video. These limits are kept explicit so the demo shows
what was actually built rather than what the ghost dog merely aspires to haunt.
