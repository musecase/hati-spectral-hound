# Local Gemma shadow gate

HATI can ask a local multimodal model for cost triage before calling Luna. It
supports two bounded modes:

- Shadow mode records what it would skip, then still calls Luna.
- Enforcing mode may suppress a Luna call only for a clearly benign bird event.

The public example is disabled and configured for shadow mode. The owner
deployment explicitly opts into enforcing mode. In either mode, Gemma can never
authorize or operate the diffuser.

The local endpoint is restricted by configuration validation to loopback HTTP
addresses. Event images do not leave the laptop during local inference.

## Current flow

1. Local motion captures the normal five chronological frames.
2. HATI writes numbered full-frame and focus contact sheets for audit.
3. LM Studio receives the five original full-resolution frames in one local
   structured-output request.
4. Gemma gives each panel a label plus one bounded certainty: `clear`, `likely`,
   or `uncertain`. It does not report a pseudo-precise numerical confidence.
5. Code derives `would_skip_luna` in either of two cases:
   - At least one panel contains a `clear` chicken or goose, every other panel is
     clearly a resident bird or empty, and there is no contradiction.
   - At least one panel contains a `clear` or `likely` human. This is a local
     human veto, so both Luna and the deterrent are suppressed.
6. The recommendation is saved with latency, token counts, labels, bounded
   certainties, and errors.
7. Shadow mode always calls Luna afterward. In enforcing mode, an eligible
   result writes a durable `LOCAL_CLEAR_BIRD` suppression decision and does not
   call Luna. An ineligible result falls through to Luna.
8. The local result cannot authorize or operate hardware.

Any local timeout, malformed output, duplicate frame number, mammal, or unknown
produces `would_escalate_to_luna`. An uncertain human escalates. A `likely` answer
also escalates unless its label is human.

## July 18 shadow benchmark

The first three saved-event comparisons justify shadow mode:

| Event | Luna | Local Gemma | Shadow recommendation | Local latency |
| --- | --- | --- | --- | ---: |
| Real poultry-only coop event | chicken in 5/5 | chicken in 5/5 | would skip | 112 s |
| Real children-at-coop event | human in 5/5 | human in 5/5 | escalate | 110 s |
| Replayed raccoon event | raccoon in 5/5 | chicken in 5/5 | **would skip incorrectly** | 108 s |

The raccoon disagreement proves that a confident local answer is not calibrated
confidence. HATI therefore refuses to enable enforcement from these results.
This is exactly the failure that the shadow gate is designed to expose.

## July 19 neutral-prompt rerun

The poultry expectation was removed from the user prompt. The same three
protected events were then rerun with the bounded certainty schema:

| Event | Local Gemma labels | Bounded certainty | Current policy disposition | Local latency |
| --- | --- | --- | --- | ---: |
| Real poultry-only coop event | chicken in 5/5 | clear in 5/5 | would skip | 153 s |
| Real children-at-coop event | human in 5/5 | likely in 2/5, clear in 3/5 | suppress as human veto | 130 s |
| Replayed raccoon event | mammal in 5/5 | likely in 5/5 | escalate | 108 s |

This corrects the original protected raccoon case without hiding the miss that
motivated the change. Three events do not support general local classification,
so enforcement is restricted to the narrow, owner-selected benign suppression
rule. It cannot produce a predator authorization.

## Promotion requirements

Before local suppression can be broadened, HATI needs a larger owner-reviewed
set containing resident birds, people, dogs, cats, replayed and real predators,
night frames, weather, and empty motion. A candidate gate must produce zero
unsafe skips on protected human and predator cases.

An enforcing design would also capture a fresh verification frame after slow
local inference. Any scene change during inference would escalate rather than
suppress. Local inference would remain unable to authorize the diffuser.
