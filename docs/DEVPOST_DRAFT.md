# Devpost draft — HATI / Spectral Hound

This is submission-ready source material, not a submitted entry. Robyn should
edit it into her own voice, add the finished public YouTube URL and Sites URL,
paste the Codex `/feedback` session ID, confirm the personal fields, and approve
the final Devpost submission.

## Project name

HATI — Spectral Hound

## Tagline

An AI farm bouncer that uses five-frame evidence and hard safety rules to deploy
a humane predator deterrent only when it should.

## Track

Apps for Your Life

## Inspiration

Predators do not just take poultry; they learn routines. Static lights, noises,
and smells can become part of the scenery. I wanted something between passive
fencing and lethal control: a selective response that appears when a predator is
actually testing the boundary, then disappears before it becomes familiar.

I am a homesteader, a parent, and a first-time hackathon participant who does not
write code. That made the experiment bigger than the device: could I bring field
knowledge, hardware, product judgment, and determined red-teaming, while Codex
turned those decisions into a real, testable system in one week?

## What it does

HATI stands for Homestead Autonomous Threat Intervention. A Foscam camera watches
a protected poultry zone. Local motion detection opens a short event window and
captures exactly five frames. Luna sends those frames to GPT-5.6 in one structured
vision request.

The model describes what it sees, but it never operates hardware. Deterministic
Python code requires temporal agreement, checks that the animal is a configured
target, and applies an absolute human veto. Unknown or incomplete evidence means
no autonomous action. An authorized event can trigger a full-mist Tuya diffuser
run with a configured medium-blue status light for no more than five minutes,
followed by unconditional shutdown attempts and an off-state check. One
continuous supervisor connects the entire
path from motion through Telegram. Before dispatch, it durably reserves the actuator attempt, so a
crash or restart cannot repeat an uncertain physical command; cooldown is rebuilt
from saved traces.

Telegram gives the owner the event evidence and outcome, collects one-tap
feedback, reports system status, runs safe tests, and supports a separate bounded
manual `/deploy` command. Correct feedback becomes protected regression evidence.
A reviewed false alarm may propose only a more conservative classifier policy,
which is promoted only after it corrects the miss with zero regressions across a
bounded set of protected real events. Feedback that could increase actuation is
held for manual review.

## How we built it

- Python 3.12 with typed records, JSON traces, OpenCV motion detection, and 95
  automated tests.
- Low-latency continuous Foscam RTSP capture with startup warmup, authenticated
  JPEG fallback, and authenticated `/24` rediscovery when DHCP changes the address.
- GPT-5.6 vision with five high-detail images, structured output, one request per
  event, token accounting, and duplicate-charge protection.
- Deterministic consensus, target allowlists, protected-zone checks, and a human
  veto outside the model.
- Local Tuya control with full mist mode, an observed medium-blue light setting, a
  five-minute hard cap, active-state confirmation, shutdown in failure paths, and
  verified off state.
- Telegram alerts, feedback, owner authentication, status, dry-run testing, and
  bounded manual deployment.
- Restart-safe end-to-end orchestration with at-most-once actuator attempts and
  persistent cross-event cooldown.
- Feedback-derived, versioned vision candidates with a bounded paid evaluation,
  automatic conservative-only promotion, and an immutable authorization boundary.
- A loopback-only Gemma 4 E4B gate with bounded certainty. Its first shadow
  benchmark exposed an unsafe raccoon-as-chicken disagreement; a neutral prompt
  corrected the protected rerun. The owner deployment now suppresses Luna only
  for a clear resident-bird event or a clear/likely human veto. Gemma can never
  authorize the diffuser.
- A public interactive judge site and GitHub Actions CI.

## Where Codex accelerated the work

Codex converted plain-language decisions into architecture, implementation,
tests, scripts, documentation, and the judge experience. It helped diagnose a
camera Wi-Fi problem, discovered the changing local IP, and recovered clean images
through the snapshot endpoint. When the first outdoor test exposed 19-second JPEG
latency, Codex replaced repeated requests with a continuously drained RTSP session.
It also mapped the diffuser from water-only observations and turned each red-team
question into a regression test.

The most important decisions were collaborative. I decided what was humane,
useful, and honest in a homestead context. Codex made those boundaries executable.
GPT-5.6 powers Luna's visual interpretation, while deterministic code keeps the
model outside the physical authorization boundary.

## Challenges

The camera was old, its original credential was missing, its Wi-Fi configuration
was temperamental, and DHCP changed its address. The first field event also proved
that a clean snapshot can still be too slow for a passing animal. The diffuser had
a consumer app but no project-specific API. Live wildlife refuses to respect
hackathon demo schedules. We answered those problems with authenticated discovery,
continuous low-latency capture, Tuya device mapping, synthetic judge fixtures, an
honest replay plan, and a plush false-positive test—without luring an animal.

## Accomplishments we are proud of

- A real five-frame indoor event was captured and classified in one GPT-5.6 call.
  A person appeared in four frames, and local policy correctly produced
  `DENY / HUMAN_VETO`.
- The final coop view produced a real outdoor event. Four frames were empty and
  the owner appeared in only the fifth; GPT-5.6 identified her, the single human
  observation vetoed action, Telegram delivered the evidence, and `correct`
  feedback was stored with the event trace.
- The physical diffuser completed bounded water-only tests and was verified off
  afterward. The finished configuration is full mist with a medium-blue status
  light, bounded to five minutes, and verified off afterward.
- The four-case judge demo runs with no camera, API key, network, or hardware.
- The controlled improvement gate moved from 3/4 to 4/4 by denying a plush decoy,
  with zero regressions. This proves the gate—not field accuracy.
- The reviewed July 16 hand event is the first protected real regression case;
  live candidate promotion awaits an honest owner-reviewed false alarm.
- A non-coder and Codex produced a public, documented, tested hardware prototype
  during a single build week.

## What we learned

The safest division of labor is also the most explainable one: the model handles
perception, ordinary code handles permission, and the owner sees the evidence.
Temporal context is more useful than a single dramatic frame. Improvement should
be gated, reversible, and measurable. And “no action” is a successful output when
the evidence is weak.

## What's next

Run a longer unattended field trial, collect owner-reviewed night events, and
expand the protected evaluation set. Later versions can vary the deterrent
pattern to reduce habituation while preserving the same authorization boundary.

## Built with

Python, OpenCV, OpenAI API, GPT-5.6, Codex, Foscam G4, Tuya/tinytuya, Telegram Bot
API, Next.js/vinext, OpenAI Sites, GitHub Actions.

## Submission links and required fields

- Public code: https://github.com/musecase/hati-spectral-hound
- Public judge site: https://hati-spectral-hound.amarygma.chatgpt.site
- Public YouTube video under three minutes: TODO
- Codex `/feedback` session ID: TODO
- Submitter type: Individual — confirm
- Country of residence: TODO for Robyn
- Optional judge/testing notes: See `README.md`, `docs/DEMO_PLAN.md`, and
  `docs/TELEGRAM_SETUP.md` in the repository.

## One-sentence honesty note for the video

“The outdoor camera event, GPT-5.6 human veto, Telegram review, and water-only
actuator are real; the wildlife scenarios are explicitly controlled because I
declined to bait a raccoon for a hackathon.”
