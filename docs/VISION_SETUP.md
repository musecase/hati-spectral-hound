# Vision setup and verified run

HATI uses the OpenAI Responses API to classify exactly five chronological camera
frames in one request. The model proposes visual observations; deterministic HATI
code derives predator status and authorizes or denies any later action.

## Configuration

- Model: `gpt-5.6-luna`
- API: Responses
- Image transport: Base64 JPEG data URLs; no Files API permission required
- Image detail: `high`, selected explicitly to bound image-token cost
- Reasoning effort: `low`
- Structured output: Pydantic schema with exactly five numbered observations
- API response storage: disabled with `store=false`
- Duplicate protection: events not in `captured` state are refused before an API call
- Key storage: Windows-user-bound encrypted CLIXML on D, ignored by Git

The model choice follows OpenAI's current guidance: GPT-5.6 Luna targets efficient,
high-volume workloads. The vision guide supports several Base64 images in one
Responses request and notes that GPT-5.6 defaults to original-resolution processing;
HATI instead requests `high` detail deliberately.

- https://developers.openai.com/api/docs/guides/latest-model
- https://developers.openai.com/api/docs/guides/images-vision
- https://developers.openai.com/api/docs/guides/structured-outputs

## First verified real event

On 2026-07-14, HATI classified a genuine five-frame motion event captured by the
Foscam G4. The sequence contained an empty first frame followed by the operator
standing and waving in the doorway.

- Request count: 1
- Input tokens: 12,684
- Output tokens: 268
- Total tokens: 12,952
- Frame 1: `unknown`, no person or animal visible
- Frames 2 through 5: `human`, confidence 0.99
- Every `safe_to_deter` result: false
- Deterministic outcome: `DENY`
- Reason code: `HUMAN_VETO`
- Physical actuator calls: 0

The private frames and runtime event trace remain excluded from Git. A sanitized
sample trace will be created separately for the public judge-runnable demo.
