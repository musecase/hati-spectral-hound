# Sample data

`eval_cases.json` contains synthetic observations for the judge-runnable demo.
They exercise deterministic authorization and the dry-run actuator without a
camera, OpenAI API key, local network, or physical hardware.

These cases are explicitly synthetic. They are not presented as model accuracy
evidence. Real camera media remains private and is excluded from the repository.

`improvement_cases.json` demonstrates the offline promotion gate. It compares a
controlled baseline and candidate on reviewed cases, corrects a plush-decoy false
positive, and proves that a candidate is promoted only when it fixes a failure
without regressing raccoon consensus, the human veto, or resident-animal safety.
It demonstrates evaluation mechanics, not live-model accuracy.
