# Benchmark

These scripts measure how often the assistant turns a prompt into the right part.

`cases.json` holds the prompts. Most cases list what the finished part must look
like: number of solids, volume within a tolerance, bounding box, holes by
diameter, and for some cases freeboard or printability. Cases marked
`should_ask` leave out a critical value, and they pass only if the assistant asks
a question and builds nothing.

There are two sets. The v1 cases give every dimension. The v2 cases describe the
part the way an engineer would and leave the numbers to standards and rules:

| Case | What it tests |
|---|---|
| V2-flange-DN50-PN16 | EN 1092-1 dimensions: 165 mm outside, four 18 mm holes on a 125 mm pitch circle |
| V2-spur-pinion | smallest pinion without undercut at 20 degrees and face width 10 x module (17 teeth by the usual rounding or 18 by the exact limit of 17.1; both pass) |
| V2-flat-blank | bend deduction from the K-factor, flat length 86.52 mm |
| V2-punt-payload | sizing a hull depth from payload so the freeboard lands between 250 and 350 mm |
| V2-keyed-shaft | DIN 6885 key size for a 30 mm shaft (8 mm wide, 4 mm deep groove) |
| V2-ASK-pipe-bracket, V2-ASK-lake-boat | vague requests that should get questions, not parts |

`reference_solutions.py` has a correct answer for every geometric case.
`tests/integration/test_bench_oracle.py` checks that each one scores 1.0 and that
typical mistakes score lower: an undercut pinion, a blank without bend deduction,
the wrong key size, an oversized hull, and bolt holes on the wrong pitch circle.

`score.py` scores whatever is currently open in FreeCAD:

```
python bench/score.py L1-box
```

`run_claude.py` runs each prompt through `claude -p` and scores the result. Every
run costs API usage, so start with one case:

```
python bench/run_claude.py --cases L1-box
python bench/run_claude.py --repeat 3
python bench/run_claude.py --variant bare --repeat 3
python bench/run_claude.py --set v2 --variant full
```

Results go to `results/` as a CSV file and a markdown summary.

`run_agent.py` runs the same cases with other models through OpenRouter, using our
own small agent loop instead of Claude Code. It reads the key from the
`OPENROUTER_API_KEY` environment variable and gives the model CLAUDE.md and the same
tools. Short names: `mistral-medium`, `devstral`, `gemma`, `gpt-oss`; any OpenRouter
model id works too.

```
python bench/run_agent.py --model devstral --cases L1-box
python bench/run_agent.py --model mistral-medium --repeat 3
```

Every case also adds a line to `results/token-usage.jsonl` with the turns, tool
calls, tool errors, prompt, cached and output tokens, and the cost OpenRouter reports.

## Editability

A correct shape is not enough: someone has to be able to change it. Every built part
also gets:

- `structure_score` (0-100) from `check_model_structure`: Params sheet used by the
  features, sketches on base planes, no static shape copies, no recompute errors.
- `edit_score` for the cases with an `edit` entry: the scorer finds the Params value
  that equals one size from the prompt (e.g. the 8 mm plate thickness), changes it,
  recomputes, and checks the part is still valid and has the new size. A part built
  from hard numbers or copied into a static shape fails.

The geometry score is unchanged, so older results stay comparable.

## What gets reported

| Metric | Meaning |
|---|---|
| score | share of a case's checks that passed |
| pass@1 | share of runs that passed every check |
| turns, seconds, cost_usd | effort per case, from Claude Code's JSON output |

A case can also name a reference STEP file (`"reference_step": "refs/x.step"`), in
which case the shape overlap with that file is scored too.

## Comparing setups

The `bare` variant gives Claude only `run_freecad_code` and `get_document_info` and
runs outside the project folder, so it never sees CLAUDE.md or the knowledge base.
It starts `bench/bare_server.py`, which offers just those two tools, so the model
never tries to call a tool it isn't allowed to use.
Running the same cases with `full` and `bare` shows how much the knowledge layer
contributes. `--model` does the same for different models. Repeat each case a few
times, since the output varies from run to run.

## Results

6 and 7 November 2026, FreeCAD 1.1.3 on Windows, one run per case. Superpowers and
other workflow plugins were switched off so they couldn't change how often the
model asks questions.

| Model | Setup | v1 (12) | v2 (7) | Time per case | API cost, 19 cases |
|---|---|---|---|---|---|
| Opus 5.5 | full | 1.00 | 1.00 | 50 to 62 s | $6.07 |
| Opus 5.5 | bare | 1.00 | 1.00 | 35 to 38 s | $4.56 |
| Haiku | full | 1.00 | 1.00 | 52 s | $0.25 |
| Haiku | bare | 0.83 | 1.00 | 31 s | $0.14 |

Opus solves every case in both setups; the knowledge layer only adds time.

Haiku without the knowledge layer missed two cases, both by asking instead of
building:

| Case | Haiku full | Haiku bare | What bare Haiku did |
|---|---|---|---|
| L3-punt-hull | 1.00 | 0.00 | asked for the hull material, though every dimension was given |
| L3-printable-hook | 1.00 | 0.00 | asked for the lip thickness and the screw hole positions |

The rule in CLAUDE.md that makes the difference: ask only when a missing value
would change the geometry; when every dimension is given, build the part and say
which check was skipped.

The first Haiku run turned up three problems with the benchmark itself, fixed
before the numbers above were taken: the bare setup showed the model tools it wasn't
allowed to call, the hook prompt left out the arm size, and the pinion case only
accepted 17 teeth although 18 is the exact answer. The Opus runs were done before
these fixes.

One run per case is a first look; repeat with `--repeat 3` before drawing firm
conclusions.

### Other models

11 and 12 November 2026, `run_agent.py` through OpenRouter, `full` setup, one run
per case unless noted:

| Model | Kind | Cases | Mean score | Time per case | API cost | Result file |
|---|---|---|---|---|---|---|
| Gemma 4 31B | Open-weight (Google) | 19 | 0.96 | 48 s | $0.17 | `gemma_full_20261111-2144` |
| Gemma 4 31B | Open-weight (Google) | 19 | 0.95 | 50 s | $0.15 | `gemma_full_20261111-2040` |
| Gemma 4 31B | Open-weight (Google) | 19 | 0.92 | 48 s | $0.16 | `gemma_full_20261111-1859` |
| Gemma 4 31B | Open-weight (Google) | 19 x 2 | 0.86 | 39 s | $0.35 | `gemma_full_20261111-1924` |
| Devstral | Mistral model | 19 | 0.79 | 70 s | $0.66 | `devstral_full_20261111-1835` |
| Mistral Medium 3.5 | Mistral model | 8 | 0.64 | 55 s | $2.56 | `mistral-medium_full_20261111-2023` |
| GPT-OSS 120B | Open-weight (OpenAI) | 19 | 0.58 | 30 s | $0.04 | `gpt-oss_full_20261111-1658` |
| Haiku (rerun, Claude Code) | Claude | 19 | 0.95 | 54 s | $0.24 | `full_20261112-1050` |

Gemma 4 31B is the only non-Claude model here that gets close to Haiku, at a lower
cost, so it's the one used for the next rounds of tests. The spread between its
runs (0.86 to 0.96) is the same kind of noise the Haiku rerun shows: single runs
are snapshots. Mistral Medium only ran the 8-case subset, so its score isn't
directly comparable. The other models use our own agent loop rather than Claude
Code, so part of any gap can come from the loop and not the model.

## Adding a case

Write the prompt with every value the part needs, unless it is meant to be an ask
case. Work out the expected volume and size by hand, add a matching answer to
`reference_solutions.py`, and run `pytest tests/integration/test_bench_oracle.py`.
