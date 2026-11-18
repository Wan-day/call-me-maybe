# Project plan: call me maybe

Sources: `en.subject.pdf` (version 1.5) and `CLAUDE.md`. Where they differ, the subject wins.

Legend: `[x]` done, `[ ]` open. Every code step follows the spec-and-tests workflow: the student writes the signatures, docstrings, and tests; the agent implements them and explains the result (CLAUDE.md, "Working with the student"). Steps marked **[core]** follow it most strictly and get the most detailed review, because evaluators dig into them.

## Workflow rules

- One feature branch per part (current: `feature/parser`). The user makes the commits and opens the PRs. Nothing is pushed to `main`.
- A step is done only when `uv run pytest` and `make lint` pass.
- Ask first: new dependencies (including `regex`), CLI option changes (`--model`, `--trace`), output format changes, CI configuration changes, input schema changes (nested arguments), deleting files.
- Tests never call the real model unless marked `@pytest.mark.slow`. Slow tests are skipped by default and in CI.
- Nothing is hardcoded to the sample files: no function names, argument names, or prompt patterns.

## Open decisions

Each decision must be settled before the step it blocks.

1. **Adapter interface type.** `typing.Protocol` or a pydantic model holding callables? CLAUDE.md says every class uses pydantic, and a Protocol has no data to validate. Proposal: Protocol, documented as the one exception. Blocks 2.2.
2. **Failed prompts.** The output has exactly one object per prompt with exactly the keys `prompt`, `name`, `parameters`, so an error entry is not possible. Mandatory proposal: stop with a clean error and write nothing. Bonus 6.3 changes this to skip-and-report with a non-zero exit. Blocks 4.2.
3. **Required arguments.** The definition format has no optional marker, so every listed parameter is treated as required. Confirm with the student. Blocks 3.4.
4. **Selection rule.** Greedy argmax over masked logits: deterministic and repeatable. Sampling would change results between runs. Blocks 3.5.
5. **Number grammar.** Proposal: optional minus, digits, optional fraction, no exponent. Confirm against the large-number and float test cases. Blocks 3.1.
6. **Qwen pre-tokenization regex.** It uses `\p{L}`/`\p{N}`, which the stdlib `re` lacks. Options: (a) add the `regex` package (needs approval), (b) a hand-written splitter with `unicodedata` categories (harder to match exactly; oracle tests will show the gap). Blocks 6.5.
7. **Subject wording for the tokenizer bonus.** The subject names only the vocab file. BPE also needs the merges file via `get_path_to_merges_file()`, which is a public SDK method. Confirm this is acceptable. Blocks 6.5.
8. **Error catching.** The pipeline catches `DecodeError` per prompt (recovery). Everything else is caught once in `__main__`. Confirm this exception is acceptable. Blocks 6.3.
9. **Chat template.** Check whether `<|im_start|>` and `<|im_end|>` encode to single ids with the SDK `encode`. If not, a plain-text prompt is simpler. Blocks 2.3.
10. **CI install cost.** Decided (2026-11-17): acceptable, keep the full `uv sync --locked`. Measured on GitHub Actions: torch download 528.9 MiB in about 15 s, 72 packages prepared in 16.3 s, whole job 31–50 s. The limit is 1 minute per CI run; optimize the install (for example a lint-only dependency set) only if runs exceed it. Was blocking 0.5.

## Design rules for the mandatory phase

Build these in the mandatory phase so the bonuses need no rewrite:

- All model-specific code sits behind the adapter (2.2). The decoder never imports `llm_sdk`.
- A `FakeModel` in `tests/` implements the same interface, so decoder tests run without torch.
- Logits are numpy arrays. Each step builds one boolean mask and sets disallowed logits to `-inf`.
- Masks are precomputed once from the vocab, not rebuilt per step (3.2).
- A forced step (exactly one allowed token) is appended without a model call. The hook exists from 3.5 and is measured in 6.2.
- The state machine is written so a nesting stack can be added later (3.4).
- The error hierarchy starts with a `CallMeMaybeError` base class in `src/errors.py` (1.2). `InputFileError` derives from it.
- Ids with no vocab entry are always masked. The logits vector can be longer than the vocab file (3.2).

## Phase 0: Foundation

- [x] **0.1 Input models.** `src/models.py`, `tests/test_models.py`. Pydantic models for functions, parameters, prompts, and parsed input. Done: tests pass.
- [x] **0.2 Parser.** `src/parser.py`, `src/errors.py`, `tests/test_parser.py`. Frozen pydantic `Parser` with `load()`. Failures raise `InputFileError` with one message per problem. Done: tests pass.
- [x] **0.3 Project config.** `pyproject.toml`: uv, dev group (pytest, flake8, mypy), flake8 and mypy exclude `llm_sdk/` and `.venv/`. Done: `uv sync` works.
- [x] **0.4 CI.** `.github/workflows/checks.yml`: flake8, mypy with the subject flags, and pytest on PRs to `main`. Done: workflow runs on PRs.
- [x] **0.5 Lock file.** Commit `uv.lock` (generated, never edited by hand). Change CI to `uv sync --locked` so it fails when the lock is stale. Record the CI install time (open decision 10). Done: CI is green on a PR with the lock committed.

## Phase 1: Skeleton (mandatory)

- [x] **1.1 Makefile.** `Makefile`. Rules:
  - `install`: `uv sync`
  - `run`: `uv run python -m src`
  - `debug`: `uv run python -m pdb -m src`
  - `clean`: remove `__pycache__`, `.mypy_cache`, `.pytest_cache`
  - `lint`: `flake8 .` and mypy with the exact subject flags
  - `lint-strict` (optional): `flake8 .` and `mypy . --strict`

  Done when: `make lint` passes on the current code and `make clean` removes the caches.

- [x] **1.2 CLI entry point.** `src/__main__.py`, `tests/test_main.py`. `argparse` with `--functions_definition`, `--input`, `--output`, using the subject defaults. `main()` catches `InputFileError`, prints it to stderr with `[CRITICAL ERROR] ` on every line, and returns 1. Non-critical errors (later, per prompt) use `[ERROR] ` and the run continues with status 0. argparse exits on its own for `--help` (0) and bad usage (2). The `CallMeMaybeError` base class was not added; decide in 6.3 whether later errors share one. Done when: `uv run python -m src --help` lists the options, and a missing file prints one line with no traceback (tested).

- [ ] **1.3 Input edge cases.** `tests/test_parser.py`. First check which cases already exist, then add the gaps: missing file, directory, empty file, invalid JSON, empty function list, empty prompt list, wrong types, duplicate names, non-UTF-8 bytes. Done when: each case has a test and the parser raises only `InputFileError`.

## Phase 2: Vocabulary and model adapter (mandatory)

- [ ] **2.1 Vocabulary.** `src/vocab.py`, `tests/test_vocab.py`. Get the path from `get_path_to_vocab_file()`. The file maps token string to id (confirm once with the real file), so invert it. Store each token as raw bytes, using the GPT-2 byte-level inverse map (`Ġ` is space, `Ċ` is newline). Store bytes, not text: a multi-byte character can be split across tokens. Add `VocabError` for duplicate ids and unreadable files. Done when: a small synthetic vocab test covers `Ġ`, `Ċ`, quotes, a UTF-8 character split across two tokens, and the bad-file cases.

- [ ] **2.2 Adapter interface.** `src/model.py`, `tests/fakes.py`, `tests/test_model.py`. Interface:
  - `logits(ids) -> numpy array`
  - `encode(text) -> list[int]`
  - the vocab from 2.1
  - `eos_id`
  - `wrap_prompt(text) -> str`

  `QwenAdapter` wraps `Small_LLM_Model` and uses only public methods. It converts the tensor from `encode` to `list[int]` immediately. `FakeModel` in `tests/fakes.py` returns scripted logits over a fixed vocab. Done when: a test asserts that importing the decoder does not import `llm_sdk` (`"llm_sdk" not in sys.modules`). Depends on 2.1 and decision 1.

- [ ] **2.3 Prompt builder.** `src/prompt.py`, `tests/test_prompt.py`. Build the text the model sees: the function list (name, description, parameters with types, return type) and the user prompt, ending where the JSON call starts. Model-specific wrapping goes in the adapter. Done when: a snapshot test on a small definition passes and the prompt contains no sample-specific text. Depends on decision 9.

## Phase 3: Constrained decoding (mandatory, core)

The function list is only prompt context. The mask is the guarantee, so a prompt that works badly still yields valid JSON.

- [ ] **3.1 Value grammars.** `src/grammar.py`, `tests/test_grammar.py`. **[core]** Pure functions over text, for `number`, `integer`, `string`, and `boolean`: `is_prefix(text)` and `is_complete(text)`. Follow JSON rules (so `01` is rejected). Strings allow escapes and reject raw `"` and control characters. Done when: tests cover negatives, floats, large numbers, `0`, empty strings, quotes and backslashes inside strings, and a check that every prefix of a valid value is accepted.

- [ ] **3.2 Token masks.** `src/masks.py`, `tests/test_masks.py`. **[core]** Precompute once with numpy, from the vocab. Categories: digits, sign, decimal point, string-safe, token contains `"`, boolean prefixes. Rules:
  - Mask every id without a vocab entry.
  - Mask special tokens in string states. Their text (for example `<|im_end|>`) contains characters that a string would accept.
  - In v1, exclude tokens that end in the middle of a UTF-8 character from strings.
  - Tokens containing `"` are few; the state machine checks them one by one.

  Done when: a synthetic-vocab test checks each category, and the build time is measured and recorded.

- [ ] **3.3 Function-name trie.** `src/trie.py`, `tests/test_trie.py`. Build a trie over function names. Names may share prefixes (for example `fn_add` and `fn_add_numbers`). Allowed next tokens: tokens whose text continues a name, plus the closing `"` at a node that is a full name. Done when: a test with one name that is a prefix of another always selects an exact definition name, and no output name falls outside the list.

- [ ] **3.4 Object state machine.** `src/state_machine.py`, `tests/test_state_machine.py`. **[core]** States: start, then the name (trie), then each parameter key in definition order (forced text), then the value (grammar of its type), then the separators, then the closing `}`. Each state knows its allowed tokens and when the object is complete. Keep it stack-ready for nested arguments (7.3). Done when: a scripted walk produces the expected JSON text, and a wrong character is rejected. Depends on 3.1 and 3.3; decision 3.

- [ ] **3.5 Decoding loop.** `src/decoder.py`, `tests/test_decoder.py`. **[core]** Each step:
  1. Get logits from the model (skipped on forced steps).
  2. Apply the state's mask and set disallowed logits to `-inf`.
  3. Pick the argmax (decision 4).
  4. Append the token id and update the state.

  Forced text (keys, punctuation) is encoded with `adapter.encode` and appended without a model call. When no token is allowed, raise `DecodeError`. Count the model calls per run. Done when: a fake model that prefers invalid tokens still yields a valid call, a dead end raises `DecodeError`, and the call count is recorded. Note for the README: encoding a forced fragment alone can differ from the model's own tokenization.

- [ ] **3.6 Property tests.** `tests/test_decoder.py`. Run the decoder with random logits over many seeds and several definitions: zero parameters, one, three, and mixed types. Done when: every output parses with `json.loads`, has a definition name, and has every parameter with the right type (int for `integer`, bool for `boolean`, number-like for `number`, str for `string`) for all seeds.

## Phase 4: Output and end-to-end (mandatory)

- [ ] **4.1 Output writer.** `src/output.py`, `tests/test_output.py`. Pydantic `FunctionCall` with exactly `prompt`, `name`, `parameters`. `number` values are written as float (`2.0`), `integer` as int. Write inside a `with` block and create the output directory if needed. Done when: a round-trip test shows exactly three keys, `2.0` for numbers, and a clean reload with `json.loads`.

- [ ] **4.2 Pipeline.** `src/pipeline.py`, `src/__main__.py`, `tests/test_pipeline.py`. Parse the input, build the adapter, decode each prompt, build a `FunctionCall`, and write once at the end. A `DecodeError` or model error stops the run with a clean message and writes nothing (decision 2). Done when: an end-to-end test with `FakeModel` writes the expected file, and a model-load failure exits cleanly. Depends on 1.2, 2.2, 3.5, 4.1.

- [ ] **4.3 Real-model run.** `tests/test_real_model.py`, marked `@pytest.mark.slow`. Run the pipeline on `data/input/` with `Qwen/Qwen3-0.6B`, validate the output with a schema-checker helper, and record the runtime. Done when: `uv run python -m src` writes a valid file for the sample inputs and the slow test passes locally (not in CI).

## Phase 5: Accuracy and reliability (mandatory)

- [ ] **5.1 Labelled set.** `tests/eval/cases.json` (location to confirm). Hand-written prompts, not copies of the sample prompts, each with the expected function and arguments. Cover: empty strings, large and negative numbers, floats, special characters and quotes, ambiguous prompts, functions with several parameters, and wrong-type phrasing. Proposal: 50 or more cases, so 90% is a clear threshold. Done when: the file loads and every expected call matches its definition.

- [ ] **5.2 Evaluation script.** `tests/eval/run_eval.py`, slow, not run in CI. Runs the pipeline on the labelled set and reports function accuracy, argument accuracy, schema validity, and time per prompt. Done when: it prints a table, and the numbers are saved for the README.

- [ ] **5.3 Reach the targets.** Adjust within the rules: prompt wording, grammar choices, function descriptions in the prompt. Never special-case a prompt or a function name. Done when: 90%+ function and argument accuracy, 100% schema-valid output, and all sample prompts finish in under 5 minutes.

## Phase 6: Targeted bonuses

Start only after phases 1 to 5 work. Each bonus needs a working demo.

- [ ] **6.1 Test suite.** `pyproject.toml` (register the `slow` marker, default `-m "not slow"`), `tests/`. Add tests for every edge case in CLAUDE.md. Done when: `uv run pytest` passes without the model and `uv run pytest -m slow` passes with it. A coverage tool would be a new dependency and needs approval.

- [ ] **6.2 Performance.** `src/decoder.py`, `src/trie.py`, `src/masks.py`.
  - Forced steps skip the model (hook from 3.5).
  - When one function name is left in the trie, finish it without the model.
  - Encode the shared prompt prefix once and reuse the ids. The SDK recomputes the whole sequence on every call, so this saves tokenization work and some calls, not attention work.
  - Use the numpy masks from 3.2 directly.

  Not possible through the public SDK, to state in the README: batching across prompts (one sequence per call) and reusing the attention cache.

  Done when: time per prompt and model calls per prompt are measured before and after, and outputs on the labelled set are identical.

- [ ] **6.3 Error handling and recovery.** `src/errors.py`, `src/decoder.py`, `src/pipeline.py`, `src/output.py`, `src/__main__.py`, tests.
  - Full hierarchy under `CallMeMaybeError`: `InputFileError`, `VocabError`, `ModelLoadError`, `DecodeError`, `OutputError`.
  - Dead-end recovery: backtrack one step and ban that token, or take the next most likely function name. Use a fixed retry budget.
  - One failing prompt does not stop the run. Failures go to stderr, and the exit status is non-zero if any prompt failed (decisions 2 and 8).
  - A model-load failure gives a message naming the model and the cause.
  - Atomic write: temp file in the same directory, then `os.replace`.
  - Ctrl+C: caught in `main()`, message printed, exit status 130, no partial output.

  Done when: tests cover a forced dead end, a fake model that raises on one prompt, a read-only output directory, and a `KeyboardInterrupt` raised from the fake model.

- [ ] **6.4 Other models.** `src/model.py`, `src/vocab.py`, `src/__main__.py`, tests. Add `--model` (default `Qwen/Qwen3-0.6B`; ask first). Select the adapter by name. Handle byte-level BPE and SentencePiece (`▁` becomes space, byte-fallback tokens `<0xNN>`). Each model has its own EOS and prompt wrapping. Some models keep the vocab in `tokenizer.json` instead of `vocab.json`; read it through `get_path_to_tokenizer_file()`. Done when: the Qwen default still works, a synthetic SentencePiece vocab test passes, and one non-Qwen model runs end to end (slow test, model chosen by the student).

- [ ] **6.5 Own tokenizer.** `src/tokenizer.py`, `tests/test_tokenizer.py`. **[core]** Build from the vocab (2.1) and the merges file (`get_path_to_merges_file()`):
  - byte-level map to and from bytes
  - pre-tokenization with the Qwen pattern (decision 6)
  - BPE: repeatedly merge the adjacent pair with the lowest rank until no ranked pair remains
  - public `encode(text) -> list[int]` and `decode(ids) -> str`

  The adapter's `encode` switches to this class. Fast tests use a tiny merges fixture. Slow oracle tests compare against the SDK `encode`/`decode` on a corpus: quotes, unicode, emoji, repeated spaces, newlines, digits, empty string, special tokens. Done when: agreement is 100% on the corpus, or each difference is listed and explained. A grep check confirms `src/` never calls the SDK's `encode` or `decode` (`str.encode` and `bytes.decode` are fine).

## Phase 7: Stretch (subject bonuses not targeted)

Optional. The design above leaves room for them.

- [ ] **7.1 Public encode/decode and demo.** Almost free after 6.5, since the methods are already public. Demo: prints prompt, then token ids from our `encode`, then the constrained output ids, then the decoded text, with the number of allowed tokens per step. Done when: the demo runs for one prompt. A `--demo` flag needs approval.

- [ ] **7.2 Visualization of generation.** Almost free if 3.5 records one entry per step: step number, token text, number of allowed tokens, chosen token. Print it as a plain text table behind a `--trace` option (ask first). Done when: one prompt prints a trace.

- [ ] **7.3 Nested arguments.** Not free. Needs an input schema that accepts object and array types (input format change, ask first), the stack-ready state machine from 3.4, and nested output models. Done when: a nested definition produces valid nested JSON that passes the schema checker.

## Phase 8: README and evaluation prep (mandatory)

- [ ] **8.1 README skeleton.** `README.md` (exists; not yet reviewed against this list). First line in italics: `*This project has been created as part of the 42 curriculum by <login>.*` (the student supplies the login). Sections, in English: Description, Instructions, Resources (references, and how AI was used per task and per part), Algorithm explanation, Design decisions, Performance analysis, Challenges faced, Testing strategy, Example usage. Keep a running AI-usage log from now on. Done when: every section exists, even if partial.

- [ ] **8.2 Fill the analysis sections.** Performance analysis uses the numbers from 5.2 and 6.2. Challenges uses the real problems met (tokenization mismatch, dead ends, mask construction). The algorithm section explains the masking with a small diagram of the states. Done when: no placeholder text is left and a peer can follow the explanation.

- [ ] **8.3 Clean clone and drills.** Clone into an empty directory, run `uv sync`, `make lint`, and the sample run. Check that `data/output/` is not tracked. Practice the drills below. Done when: every item in the checklist passes.

## Evaluation readiness checklist

- [ ] Clean clone: `uv sync` works. `uv.lock` and `llm_sdk/` are committed. No `data/output/`, `.venv/`, or caches are tracked.
- [ ] `make lint` passes (flake8 and mypy with the subject flags). `make lint-strict` is attempted (optional).
- [ ] `uv run pytest` passes without the model. `uv run pytest -m slow` passes locally.
- [ ] No forbidden imports in `src/` (`torch`, `transformers`, `huggingface`, `outlines`, `dspy`, and similar).
- [ ] No private `llm_sdk` members used (no `._` access on the SDK object).
- [ ] Sample run finishes in under 5 minutes. Output has exactly `prompt`, `name`, `parameters`. Numbers are written as floats.
- [ ] Measured: 90%+ function and argument accuracy, 100% schema-valid output.
- [ ] Missing file, invalid JSON, empty file, and a bad model name each give a clear message and no traceback.
- [ ] README: italic first line, all sections present, in English, AI-usage section accurate.
- [ ] Every claimed bonus has a working demo.
- [ ] The student can explain every line. Practice these live changes, each of which should take minutes:
  - add a `boolean` parameter type to a definition and handle it
  - change the number format (for example, disallow negatives)
  - add a new function to the definition file and run it with no code change
  - change a function description and show the effect on the choice
  - add two function names where one is a prefix of the other, and show the trie handles it
