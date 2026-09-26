# E4 manual side-tests: Claude Code and VS Code

`client_harness.py` drives the 20 questions programmatically against the
Anthropic API. The plan's measures 1–2 (correct answers, tool calls, correct
`namespace/id` citations) are what that script scores. This file is for the
two side-tests the plan calls out that **cannot** be driven from here because
they depend on a live client UI: **measure 3** (VS Code, resources only) and
a manual spot-check of the same questions in **Claude Code** (tools). Record
whatever you observe back into `e4-results.md` by hand, under a `## Manual
side-tests` heading — `client_harness.py` never touches that heading, so it's
safe from being overwritten by a rerun.

Questions: `../fixtures/questions.yaml` (20 total — read `question`, note the
`expected` `namespace/id` refs, don't read `answer` until you've tried to
answer it yourself, the way the LLM mode's grader would).

## A. Claude Code (tools) — sanity spot-check

This is not the scored measure (that's `client_harness.py --mode llm`); it's
a human sanity check that a real Claude Code session, not just the
programmatic loop, gets the same behaviour.

1. Register the server (once):

   ```bash
   claude mcp add aix-federation -- uv run --with mcp --with pyyaml \
     /ABS/PATH/TO/aix-format/experiments/e4-mcp/server.py --federation \
     /ABS/PATH/TO/aix-format/experiments/fixtures/federation.aix.yaml
   ```

   (See `mcp-config.example.json` for the equivalent raw JSON if you'd
   rather edit `.mcp.json` / `.claude.json` directly.)

2. Start a **fresh** Claude Code session (no other context — this is testing
   the tools alone, not vault knowledge) and confirm the server connected:
   `/mcp` should list `aix-federation` with 4 tools.

3. Pick 4–6 questions from `questions.yaml` — include at least one of the 4
   collision questions (`q01`–`q04`, ids `collision: true`) and one
   single-bundle question. Paste each question's `question` text verbatim,
   nothing else added.

4. For each, record:
   - Which tools it called, in what order, and how many calls total.
   - Whether its answer names the right `namespace/id` for a collision
     question (e.g. correctly distinguishing `data-eng/customers` from
     `household/customers`) — this is the thing most likely to go wrong
     without the qualifier.
   - Whether the answer matches the question's `answer` field in substance.

5. Append a short table to `e4-results.md` under `## Manual side-tests` →
   `### Claude Code spot-check`: question id, tool calls, correct namespace
   (yes/no), matches expected answer (yes/no), plus the Claude Code version
   (`claude --version`) and today's date.

## B. VS Code (resources only) — measure 3

The plan expects this to score **worse** than the tools path — VS Code's
MCP resource UI has no search, so the model (or a person) is limited to
whatever resources are listed or whatever URI they think to type. That gap
is itself the finding; don't be surprised by it.

1. Open the `aix-format` repo as a VS Code workspace.
2. Copy `mcp-config.example.json`'s `_vscode_dot_vscode_mcp_json.servers`
   block into `.vscode/mcp.json` (create the file/folder if needed) — just
   the `{"servers": {...}}` shape, not the `_comment`/`_vscode_dot_vscode…`
   wrapper keys.
3. Start the server from VS Code's MCP panel (or reload the window so it
   autostarts) and confirm `aix-federation` shows as running with resources
   listed under `aix://<namespace>/<id>` — note there is no bulk "list all"
   without paging through `list_resources`/templates in the panel, since
   this server exposes concepts as a template (`aix://{namespace}/{id}`),
   not one fixed resource per concept.
4. Open Copilot Chat in **agent mode** with only resources available (no
   tools) — attach the resource(s) you believe answer a question, the same
   way a person would browse and pick a file, then ask the question.
5. Try the same 4–6 questions as the Claude Code spot-check (section A).
   For each, record:
   - Whether you could find the right resource(s) at all without already
     knowing the `namespace/id` (this is the crux of the plan's "expected
     worse" prediction — resources have no search).
   - Whether, once attached, the model's answer is correct.
   - How many resource reads / how much manual browsing it took, as the
     closest analogue to "tool calls".
6. Append the same shape of table to `e4-results.md` under
   `## Manual side-tests` → `### VS Code (resources only)`, plus the VS
   Code version (`code --version`) and today's date.

## Recording results

Both sub-sections go in `e4-results.md`, appended once under a
`## Manual side-tests` heading you add by hand (outside the
`<!-- BEGIN:deterministic -->` / `<!-- BEGIN:llm -->` markers that
`client_harness.py` owns and will overwrite on a rerun). Include:

- Date, Claude Code version, VS Code version.
- The per-question table for each client.
- One line of judgement: did VS Code (resources only) in fact score worse
  than Claude Code (tools), and by how much — this is what closes out the
  plan's measure 3.
