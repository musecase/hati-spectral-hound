# Telegram operator setup

Telegram is the owner console for event alerts, feedback, status checks, dry-run
tests, and optional bounded manual deployment. It is disabled in the public
configuration and never requires a secret in Git.

## What is already built

- one photo-and-summary alert per saved event;
- inline feedback for correct calls, false alarms, wrong animals, missed threats,
  inappropriate actuation, and expected actuation that did not happen;
- owner-chat enforcement for all commands and feedback;
- `/status` for the current camera/mode/actuation state;
- `/test` for an end-to-end dry-run that never operates the physical device;
- `/deploy` for an authenticated owner-requested bounded mist;
- feedback stored alongside the original event trace for later evaluation.

Autonomous actuation remains evidence-gated. Manual `/deploy` is a separate owner
path, but it uses the same hard duration cap and shutdown verification as an
autonomous deployment.

## One-time setup

1. In Telegram, open the verified **@BotFather** account.
2. Send `/newbot`, choose a display name and unique username, and copy the bot
   token. Do not paste the token into chat, documentation, screenshots, or Git.
3. Open the new bot and send it `/start`.
4. Find the numeric owner chat ID. A simple option is to send a message to the bot,
   then open `https://api.telegram.org/bot<TOKEN>/getUpdates` privately and read
   `message.chat.id`. Delete the token from browser history afterward.
5. In `config/hati.local.json`, set `telegram.enabled` to `true`. Keep the token
   and chat ID out of the file.
6. Save both values with Windows user-bound encryption:

   ```powershell
   .\scripts\save-telegram-credential.ps1
   ```

The encrypted credential is written to `config/telegram-credential.clixml`, stays
on D:, and is ignored by Git. Only the same Windows account on this computer can
decrypt it.

## Verify before operating hardware

Preview an alert locally with no network call:

```powershell
.\scripts\hati.ps1 telegram-preview --config config\hati.local.json --event data\events\EVENT_ID\event.json
```

Send one saved event to the owner:

```powershell
.\scripts\hati.ps1 telegram-notify --config config\hati.local.json --event data\events\EVENT_ID\event.json
```

Process one batch of replies or commands:

```powershell
.\scripts\hati.ps1 telegram-poll-once --config config\hati.local.json
```

Start with `runtime.test_mode: true` and `runtime.armed: false`. Send `/test`, then
tap a feedback button and confirm that the event JSON now contains the review.
Only enable manual deployment after the water-only setup is clear of electronics,
people, and animals.

## Command boundary

Messages from any chat other than the configured owner are rejected. `/deploy`
also requires `telegram.manual_deploy_enabled: true`, an armed runtime, and a real
actuator configuration. HATI still caps the command at five seconds, always
attempts shutdown, and verifies the device is off.
