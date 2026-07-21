"use client";

import { useState } from "react";

type EvidenceCase = {
  id: string;
  eyebrow: string;
  title: string;
  note: string;
  frames: Array<{ label: string; confidence: number; human?: boolean }>;
  outcome: "DEPLOY" | "DENY";
  reason: string;
};

const cases: EvidenceCase[] = [
  {
    id: "raccoon",
    eyebrow: "Threat consensus",
    title: "A raccoon holds the frame",
    note: "Four of five frames agree on a configured predator. No person appears.",
    frames: [
      { label: "raccoon", confidence: 91 },
      { label: "raccoon", confidence: 94 },
      { label: "raccoon", confidence: 89 },
      { label: "raccoon", confidence: 92 },
      { label: "unknown", confidence: 54 },
    ],
    outcome: "DEPLOY",
    reason: "4-frame consensus · target configured · human veto clear",
  },
  {
    id: "human",
    eyebrow: "Hard safety veto",
    title: "A person enters late",
    note: "Even strong predator evidence cannot overrule a human in any frame.",
    frames: [
      { label: "raccoon", confidence: 90 },
      { label: "raccoon", confidence: 93 },
      { label: "raccoon", confidence: 89 },
      { label: "human", confidence: 98, human: true },
      { label: "human", confidence: 99, human: true },
    ],
    outcome: "DENY",
    reason: "HUMAN_VETO · deterministic · model cannot override",
  },
  {
    id: "chicken",
    eyebrow: "Resident animal",
    title: "The flock is being the flock",
    note: "A chicken near the boundary is expected, not a reason to intervene.",
    frames: [
      { label: "chicken", confidence: 97 },
      { label: "chicken", confidence: 95 },
      { label: "chicken", confidence: 96 },
      { label: "chicken", confidence: 98 },
      { label: "chicken", confidence: 94 },
    ],
    outcome: "DENY",
    reason: "NON_TARGET · no threat consensus",
  },
  {
    id: "uncertain",
    eyebrow: "Uncertain evidence",
    title: "The night makes no promises",
    note: "A single plausible frame is not enough. Ambiguity resolves to no action.",
    frames: [
      { label: "unknown", confidence: 44 },
      { label: "raccoon", confidence: 61 },
      { label: "unknown", confidence: 49 },
      { label: "cat", confidence: 58 },
      { label: "unknown", confidence: 42 },
    ],
    outcome: "DENY",
    reason: "INSUFFICIENT_CONSENSUS · fail closed",
  },
];

const loop = [
  ["01", "SEE", "Local motion opens a short event window."],
  ["02", "IDENTIFY", "Luna screens frames 2 and 4; uncertain events complete all five."],
  ["03", "VERIFY", "Local rules demand consensus and apply hard vetoes."],
  ["04", "ACT", "A bounded Tuya command deploys mist, then verifies off."],
  ["05", "REVIEW", "Telegram carries the evidence, outcome, and feedback."],
];

function EvidenceLab() {
  const [selected, setSelected] = useState(cases[0]);
  const [running, setRunning] = useState(false);

  const choose = (item: EvidenceCase) => {
    setRunning(true);
    window.setTimeout(() => {
      setSelected(item);
      setRunning(false);
    }, 240);
  };

  return (
    <section className="evidence-shell" id="evidence" aria-labelledby="evidence-title">
      <div className="section-lede inverse-lede">
        <div>
          <p className="kicker">THE FIVE-FRAME TEST</p>
          <h2 id="evidence-title">Don&apos;t trust a hunch.<br />Run the evidence.</h2>
        </div>
        <p>
          Luna describes what the camera saw. A separate, deterministic policy decides
          whether HATI may act. Try the four canonical cases.
        </p>
      </div>

      <div className="case-picker" role="tablist" aria-label="Evidence scenarios">
        {cases.map((item) => (
          <button
            key={item.id}
            type="button"
            className={selected.id === item.id ? "case-button active" : "case-button"}
            onClick={() => choose(item)}
            role="tab"
            aria-selected={selected.id === item.id}
          >
            <span>{item.eyebrow}</span>
            {item.title}
          </button>
        ))}
      </div>

      <div className={running ? "evidence-console loading" : "evidence-console"}>
        <div className="console-topline">
          <span>EVENT / DEMO-{selected.id.toUpperCase()}</span>
          <span className="live-dot">LOCAL POLICY ONLINE</span>
        </div>
        <div className="frames" aria-label="Five classified frames">
          {selected.frames.map((frame, index) => (
            <div className={frame.human ? "frame human-frame" : "frame"} key={`${selected.id}-${index}`}>
              <div className="frame-visual">
                <span className="scanline" />
                <b>0{index + 1}</b>
                <div className={`silhouette silhouette-${frame.label}`} aria-hidden="true" />
              </div>
              <span className="frame-label">{frame.label}</span>
              <strong>{frame.confidence}%</strong>
            </div>
          ))}
        </div>
        <div className="decision-row">
          <div>
            <p className="kicker">POLICY RESULT</p>
            <h3>{selected.title}</h3>
            <p>{selected.note}</p>
          </div>
          <div className={selected.outcome === "DEPLOY" ? "decision deploy" : "decision deny"}>
            <span>{selected.outcome === "DEPLOY" ? "AUTHORIZED" : "NO ACTION"}</span>
            <strong>{selected.outcome}</strong>
            <small>{selected.reason}</small>
          </div>
        </div>
      </div>
      <p className="lab-note">Interactive reconstruction from the repository&apos;s deterministic demo fixtures; not wildlife footage.</p>
    </section>
  );
}

export function HatiExperience() {
  return (
    <main>
      <nav className="site-nav" aria-label="Primary navigation">
        <a className="wordmark" href="#top" aria-label="HATI home">
          <span className="hound-mark" aria-hidden="true">H</span>
          <span>HATI <small>SPECTRAL HOUND</small></span>
        </a>
        <div className="nav-links">
          <a href="#evidence">Evidence</a>
          <a href="#system">System</a>
          <a href="#build">Build story</a>
          <a className="nav-github" href="https://github.com/musecase/hati-spectral-hound" target="_blank" rel="noreferrer">View code ↗</a>
        </div>
      </nav>

      <header className="hero" id="top">
        <div className="hero-art" role="img" aria-label="Concept illustration of a raccoon at a protected moonlit poultry coop" />
        <div className="hero-wash" />
        <div className="hero-copy">
          <p className="kicker hero-kicker"><span /> HOMESTEAD AUTONOMOUS THREAT INTERVENTION</p>
          <h1>An AI farm bouncer<br />that knows when <em>not</em> to act.</h1>
          <p className="hero-summary">
            HATI watches a poultry boundary, asks GPT-5.6 what five frames actually show,
            and lets hard local rules decide whether a brief, humane scent mist is warranted.
          </p>
          <div className="hero-actions">
            <a className="button primary" href="#evidence">Run the evidence <span>↓</span></a>
            <a className="button ghost" href="#demo">Watch the demo <span>▶</span></a>
          </div>
          <p className="illustration-label">Concept illustration · outdoor safety loop verified</p>
        </div>
        <div className="field-stamp" aria-label="Project status">
          <span>BUILD WEEK</span>
          <b>WORKING<br />PROTOTYPE</b>
          <small>JULY 2026</small>
        </div>
      </header>

      <section className="proof-strip" aria-label="Verified project status">
        <div><b>01</b><span>Foscam G4</span><small>live snapshot verified</small></div>
        <div><b>05</b><span>frame evidence</span><small>one vision request</small></div>
        <div><b>01</b><span>human veto</span><small>real field event denied</small></div>
        <div><b>≤5m</b><span>bounded actuation</span><small>water-tested + verified off</small></div>
      </section>

      <section className="problem-section">
        <div className="section-number">01 / THE PROBLEM</div>
        <div className="problem-grid">
          <h2>Predators learn.<br />Static deterrents<br /><em>become scenery.</em></h2>
          <div className="problem-copy">
            <p className="large-copy">
              Backyard keepers need something between passive fencing and lethal control:
              a response that is selective, surprising, and only present when it matters.
            </p>
            <p>
              HATI combines ordinary homestead hardware with temporal visual reasoning.
              It does not need a raccoon to appear on demo day, and it does not pretend every
              moving shadow is one. Uncertainty means no autonomous action.
            </p>
          </div>
          <aside className="ethic-card">
            <p className="kicker">THE DESIGN ETHIC</p>
            <blockquote>Protect the flock.<br />Teach the boundary.<br />Harm neither.</blockquote>
            <span>targeted deterrence over habituation</span>
          </aside>
        </div>
      </section>

      <EvidenceLab />

      <section className="system-section" id="system">
        <div className="section-lede">
          <div>
            <p className="kicker">FROM PIXEL TO PUMP</p>
            <h2>One event.<br />Five accountable steps.</h2>
          </div>
          <p>
            The language model never touches the actuator. Each handoff is logged, replayable,
            and narrow enough to test in isolation.
          </p>
        </div>
        <div className="loop-list">
          {loop.map(([number, title, description]) => (
            <div className="loop-item" key={number}>
              <span>{number}</span>
              <b>{title}</b>
              <p>{description}</p>
              <i aria-hidden="true">→</i>
            </div>
          ))}
        </div>

        <div className="hardware-grid">
          <article>
            <p className="kicker">EYES</p>
            <h3>Foscam G4</h3>
            <p>Continuous low-latency RTSP, authenticated fallback, dynamic-address discovery.</p>
            <span className="status-tag good">FIELD TESTED</span>
          </article>
          <article>
            <p className="kicker">REASONING</p>
            <h3>Luna / GPT-5.6</h3>
            <p>Two-frame screening, conditional five-frame completion, structured JSON.</p>
            <span className="status-tag good">LIVE TESTED</span>
          </article>
          <article>
            <p className="kicker">LOCAL SCOUT</p>
            <h3>Gemma 4 E4B</h3>
            <p>Loopback-only benign triage. May suppress Luna for a clear resident bird or human veto; never authorizes action.</p>
            <span className="status-tag">MISS CAUGHT · RULE NARROWED</span>
          </article>
          <article>
            <p className="kicker">MUSCLE</p>
            <h3>Tuya diffuser</h3>
            <p>Full mist, medium-blue status light, five-minute maximum, state verified on and off.</p>
            <span className="status-tag good">WATER TESTED</span>
          </article>
          <article>
            <p className="kicker">OPERATOR</p>
            <h3>Telegram</h3>
            <p>Evidence alerts, owner feedback, status, testing, and bounded manual deploy.</p>
            <span className="status-tag good">LIVE VERIFIED</span>
          </article>
        </div>
      </section>

      <section className="improvement-section">
        <div className="improvement-copy">
          <p className="kicker">PROVE THE LOOP</p>
          <h2>Improvement must<br />earn promotion.</h2>
          <p>
            Correct feedback protects known-good behavior. A false-alarm tap queues a conservative
            classifier safeguard in the background, but it cannot quietly loosen the live system.
            The candidate must correct the miss and introduce zero regressions across protected cases.
          </p>
          <div className="truth-note">
            <b>Important honesty label</b>
            <span>This proves the promotion mechanism, not field accuracy. Wildlife evaluation grows with reviewed events.</span>
          </div>
          <div className="truth-note">
            <b>Local gate evidence</b>
            <span>Gemma first misread a replayed raccoon as chicken. Shadow mode caught it; a neutral prompt then labeled the same five frames as likely mammal. Enforcement remains limited to benign suppression and cannot authorize action.</span>
          </div>
        </div>
        <div className="score-card">
          <div className="score-top"><span>CONTROLLED EVALUATION</span><b>GATE PASSED</b></div>
          <div className="score-comparison">
            <div><small>BASELINE</small><strong>3<span>/4</span></strong><p>plush decoy misread</p></div>
            <div className="score-arrow">→</div>
            <div className="candidate"><small>CANDIDATE</small><strong>4<span>/4</span></strong><p>decoy now denied</p></div>
          </div>
          <dl>
            <div><dt>Corrected cases</dt><dd>1</dd></div>
            <div><dt>Regressions</dt><dd>0</dd></div>
            <div><dt>Promotion</dt><dd className="promote">AUTHORIZED</dd></div>
          </dl>
          <code>scripts\learn-from-latest-event.ps1</code>
        </div>
      </section>

      <section className="telegram-section">
        <div className="telegram-phone" aria-label="Example Telegram alert">
          <div className="phone-bar"><span>←</span><b>HATI Spectral Hound</b><i>•••</i></div>
          <div className="chat-day">TONIGHT</div>
          <div className="bot-bubble">
            <small>HATI · real outdoor event</small>
            <b>HUMAN · FRAME 5</b>
            <p>0/5 predator votes<br />Decision: DENY · HUMAN_VETO<br />No deterrent authorized</p>
            <time>2:17 PM</time>
          </div>
          <div className="feedback-buttons">
            <span>✓ Correct</span><span>False alarm</span><span>Wrong animal</span>
          </div>
          <div className="owner-bubble">✓ Correct <time>2:25 PM ✓✓</time></div>
          <div className="bot-bubble compact">Feedback recorded · Test mode<br />Manual deployment disabled</div>
        </div>
        <div className="telegram-copy">
          <p className="kicker">HUMAN IN THE LEARNING LOOP</p>
          <h2>Evidence comes to you.<br />Control stays with you.</h2>
          <p>
            Every event becomes a reviewable record. One tap marks a correct call, false alarm,
            wrong animal, missed threat, or inappropriate actuation. Only the configured owner
            chat may issue commands.
          </p>
          <ul>
            <li><b>/status</b><span>See the camera, mode, and last actuation state.</span></li>
            <li><b>/test</b><span>Exercise the full path without operating the mister.</span></li>
            <li><b>/deploy</b><span>Owner-authorized, bounded manual mist when wanted.</span></li>
          </ul>
        </div>
      </section>

      <section className="demo-section" id="demo">
        <div className="video-frame">
          <div className="video-placeholder">
            <span className="play-button">▶</span>
            <p>3-MINUTE DEMO</p>
            <small>YouTube premiere slot reserved</small>
          </div>
        </div>
        <div className="demo-copy">
          <p className="kicker">THE FIELD NOTE, ON FILM</p>
          <h2>See the whole handoff.</h2>
          <p>
            Camera to Luna. Luna to policy. Policy to water mist. Evidence to owner. The public
            Build Week demo will live here as soon as the final cut is uploaded.
          </p>
          <span className="status-tag pending">VIDEO IN PRODUCTION</span>
        </div>
      </section>

      <section className="build-section" id="build">
        <div className="build-quote">
          <p className="kicker">BUILT WITH CODEX + GPT-5.6</p>
          <blockquote>
            “I&apos;ve never done a hackathon.<br />I can&apos;t code. <em>Let&apos;s build it anyway.</em>”
          </blockquote>
          <p className="attribution">— Robyn, homesteader, first-time hacker, keeper of the actual hardware</p>
        </div>
        <div className="roles-card">
          <h3>A collaboration with clear jobs</h3>
          <div><span>ROBYN</span><p>Problem expertise, animal welfare, hardware, red-teaming, and final judgment.</p></div>
          <div><span>CODEX</span><p>Architecture, implementation, tests, debugging, documentation, and deployment.</p></div>
          <div><span>GPT-5.6</span><p>Temporal visual classification inside Luna&apos;s tightly constrained event contract.</p></div>
          <a href="https://github.com/musecase/hati-spectral-hound/blob/main/docs/BUILT_WITH_CODEX.md" target="_blank" rel="noreferrer">Read the build record ↗</a>
        </div>
      </section>

      <section className="honesty-section">
        <p className="kicker">CURRENT FIELD NOTES</p>
        <h2>Working prototype.<br />No hand-waving.</h2>
        <div className="honesty-grid">
          <div><b>✓ VERIFIED</b><p>Outdoor motion event, five-frame GPT-5.6 classification, deterministic human veto, Telegram owner feedback, 100+ passing tests, and water-only actuation.</p></div>
          <div className="observed"><b>◎ OBSERVED</b><p>During field testing, the camera&apos;s bundled trial AI issued three car alerts irrelevant to the protected coop zone. HATI produced substantially less operator noise in the same period. Anecdotal field observation, not an accuracy benchmark.</p></div>
          <div className="next"><b>◌ NEXT</b><p>Run a longer unattended field trial, collect reviewed night events, and replace this site&apos;s video placeholder.</p></div>
          <div className="not-claimed"><b>× NOT CLAIMED</b><p>No live raccoon encounter yet. No model weights retrain themselves. No scent has been loaded for indoor testing.</p></div>
        </div>
      </section>

      <footer>
        <div className="footer-mark">HATI <span>— SPECTRAL HOUND</span></div>
        <p>Humane intervention. Accountable evidence. Just a little piss ambiance.</p>
        <div><a href="https://github.com/musecase/hati-spectral-hound" target="_blank" rel="noreferrer">GitHub ↗</a><a href="#top">Back to top ↑</a></div>
      </footer>
    </main>
  );
}
