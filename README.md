# Jev Wall

A live, visual test of [TypeSafe AI's Jev](https://typesafe.ai) as a prompt-injection guardrail.

Jev is a "System One" model: it does not generate text. You hand it some state and a set of typed
questions, and it returns typed answers with calibrated probabilities, in a few hundred
milliseconds, for a fraction of a cent. That makes it a natural fit for a guardrail that sits in
front of an LLM and has to decide, fast, whether a prompt is an attack.

Jev Wall puts that claim on screen. Labelled prompts fly into a guardrail, Jev answers three
questions about each one in a single call, and three buckets light up:

- **Verdict** — is this an injection or jailbreak attempt? (BLOCKED or ALLOWED)
- **Technique** — which of 28 techniques is it, across six tactics?
- **Severity** — how bad would it be if the assistant complied, from 0 to 3?

Because the prompts come with human labels, the wall also scores Jev as it goes: accuracy,
precision, recall, a ROC curve, and a calibration plot that checks whether "90% confident" really
means right nine times in ten. Latency and cost tick up alongside.

<!-- Add a screenshot or GIF of a run here. -->

## What it measures, and what it does not

Only the attack-or-benign verdict has ground truth, so that is the only thing scored. Technique and
severity are Jev's own judgement and are shown, not graded.

The two datasets define "attack" differently (one collects prompt injections, the other
jailbreaks), so accuracy is also shown per dataset. Public labels are never perfect: some of what
counts as a Jev error is an arguable label.

By default a run samples 300 prompts, split evenly between the two datasets. That sample does not
have the same attack-to-benign ratio as the full corpus, so precision and accuracy from a default
run are not directly comparable with a `--full` run.

In one 50-prompt sample during development, Jev scored 94% accuracy at a 0.5 threshold (precision
100%, recall 85%, AUC 0.997), with a median latency around 360 ms, for $0.003. Treat that as a
smoke test, not a benchmark; run it yourself.

## Setup

You need [uv](https://docs.astral.sh/uv/) and a Jev API key.

```bash
git clone <this repo> && cd jev
uv sync
echo "JEV_API_KEY=your-key-here" > .env
```

`.env` is git-ignored. The key is read by the Python process only; it is never sent to the browser
and never written to a run file or an exported page.

## Use

**Live wall**

```bash
uv run jevwall serve
```

Open http://127.0.0.1:8000, choose how many prompts to run, and press **Start run**. Drag the
threshold slider to see precision and recall trade off; nothing is re-sent to Jev when you do. The
box at the bottom scores any prompt you type.

**Headless run**

```bash
uv run jevwall run --limit 100     # 50 prompts from each dataset
uv run jevwall run --full          # all 1,968 prompts
```

Every run, live or headless, is saved to `runs/<timestamp>.json`.

**Shareable replay**

```bash
uv run jevwall export              # newest run -> dist/replay.html
```

`dist/replay.html` is one self-contained file that replays the run with no server and no key. It
makes no network requests apart from web fonts. Note that it contains the dataset prompts
themselves, which include offensive jailbreak text.

## Cost

Jev charges $0.042 per million input tokens; output is free. Each call here is about 1,300 tokens
of questions plus the prompt.

| Run | Prompts | Approximate cost |
|---|---|---|
| Default | 300 | $0.02 |
| Full corpus | 1,968 | $0.15 |

Every run has a cost ceiling of $0.50. A run that would exceed it is refused before any call is
made, and a run that crosses it part-way stops early. A headless run can change the ceiling with
`--max-cost`; the live wall uses the same default and the browser cannot raise it. The server also
allows only one run at a time, so a second **Start run** cannot double the bill.

## How it works

```
datasets -> runner -> judge -> Jev API
               |
               +-> one JSON event per prompt -> SSE -> the page
               +-> runs/<timestamp>.json -> export -> dist/replay.html
```

| Module | Job |
|---|---|
| `taxonomy.py` | The technique matrix and the criteria text Jev reads |
| `judge.py` | One Jev call, three typed questions, one typed `Verdict`. The only module that touches the SDK or the key |
| `corpus.py` | Loads both datasets into one record shape; balanced sampling |
| `runner.py` | Concurrent run, rate spacing, cost ceiling, event stream, run file |
| `server.py` | FastAPI: the page, the SSE stream, and the try-your-own endpoint |
| `export.py` | Inlines a run into the page, escaping it for safe embedding |
| `web/index.html` | The wall. The same file serves live mode and replay |

The live server binds to 127.0.0.1 only, and its paid endpoints require a per-session token, so
another site open in your browser cannot start a run.

## Development

```bash
uv run pytest
uv run ruff check src tests scripts
```

The tests use a fake judge and never call the API. `scripts/smoke.py` sends five prompts to the
real API (well under a cent) to confirm your key and the SDK work.

## Data

- [`deepset/prompt-injections`](https://huggingface.co/datasets/deepset/prompt-injections) — Apache 2.0
- [`jackhhao/jailbreak-classification`](https://huggingface.co/datasets/jackhhao/jailbreak-classification) — Apache 2.0

The technique matrix is loosely informed by [MITRE ATLAS](https://atlas.mitre.org/) and the
[OWASP Top 10 for LLM Applications](https://owasp.org/www-project-top-10-for-large-language-model-applications/).
This project is independent and is not affiliated with TypeSafe AI.
