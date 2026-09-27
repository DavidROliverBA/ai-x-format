#!/usr/bin/env python3
"""E4 question runner: drives the 20 federation questions (MyVault plan,
E4 section) through server.py's MCP tools in one of two modes.

    deterministic   No LLM. search(question, limit=1) -> get(top hit).
                    cites_correct = the top hit's ref is in `expected`.
                    This is a floor for retrieval + payload-contract
                    fidelity, NOT a measure of answer quality — it never
                    reads the answer text, only whether identity survived
                    the round trip through search() and get().

    llm             Claude Code as client (Anthropic API), the four MCP
                    tools translated to API tool definitions, looping
                    until the model stops calling tools (max 8 calls per
                    question). Scores cites_correct (every `expected` ref
                    appears in the model's final "CITES: ..." line) and
                    answer_correct (a second API call grades the answer
                    against the question's known answer).
                    Requires ANTHROPIC_API_KEY; if unset, prints exactly
                    "E4 llm mode: ANTHROPIC_API_KEY not set; skipped" and
                    exits 0 (no error) per the task's instruction.

Run (from this directory):
    uv run --with mcp --with pyyaml client_harness.py --mode deterministic
    uv run --with mcp --with pyyaml --with anthropic client_harness.py --mode llm

Writes results-<mode>.json and updates the "## <Mode> mode" section of
e4-results.md (idempotent: a rerun replaces its own section, it does not
grow the file).
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import importlib.metadata
import json
import os
import platform
import re
import sys
from pathlib import Path

import yaml
from mcp import Client, StdioServerParameters

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
SERVER_PATH = HERE / "server.py"
DEFAULT_FEDERATION = REPO_ROOT / "experiments" / "fixtures" / "federation.ai-xf.yaml"
DEFAULT_QUESTIONS = REPO_ROOT / "experiments" / "fixtures" / "questions.yaml"
RESULTS_MD = HERE / "e4-results.md"

MODEL_ID = "claude-sonnet-4-5"
MAX_TOOL_CALLS = 8

SYSTEM_PROMPT = """\
You are answering questions about a federation of AI-XF knowledge bundles, served to you
through four MCP tools: list_bundles, list_concepts, search, and get.

Two of the bundles deliberately share bare concept ids (e.g. both a "data-eng" bundle and
a "household" bundle have a concept called "customers", and both an "example-payments"
bundle and "data-eng" have one called "orders-table"). These are unrelated concepts that
happen to share an id — the namespace is what disambiguates them. Always resolve and cite
concepts as "namespace/id", never a bare id.

Use search() and get() (and list_bundles()/list_concepts() if useful) to find the concepts
that answer the question. Read enough concepts to answer accurately and to get the
namespace right, especially when the question mentions a shared id.

When you have a full answer, give it in prose, then end your response with exactly one
line in this form, listing every namespace/id you relied on to answer (comma-separated,
no other text on that line):

CITES: namespace/id, namespace/id
"""

GRADER_PROMPT_TEMPLATE = """\
You are grading a question-answering system. Compare the GIVEN ANSWER to the EXPECTED
ANSWER for the same question. Judge only whether the given answer conveys the same
substantive facts as the expected answer — wording may differ.

QUESTION: {question}

EXPECTED ANSWER: {expected}

GIVEN ANSWER: {given}

Reply with exactly one word: YES if the given answer is substantively correct and
complete relative to the expected answer, or NO otherwise.
"""

CITES_RE = re.compile(r"^CITES:\s*(.+)$", re.MULTILINE | re.IGNORECASE)


def load_questions(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data["questions"]


def pkg_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def make_server_params(federation: Path) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER_PATH), "--federation", str(federation)],
    )


def common_versions() -> dict:
    return {
        "date": datetime.date.today().isoformat(),
        "python": platform.python_version(),
        "mcp": pkg_version("mcp"),
        "pyyaml": pkg_version("pyyaml"),
        "platform": platform.platform(),
    }


def totals_for(records: list[dict], mode: str) -> dict:
    total = len(records)
    cites_correct = sum(1 for r in records if r["cites_correct"])
    cross = [r for r in records if r["kind"] == "cross"]
    cross_correct = sum(1 for r in cross if r["cites_correct"])
    collision = [r for r in records if r["collision"]]
    collision_correct = sum(1 for r in collision if r["cites_correct"])
    single = [r for r in records if r["kind"] == "single"]
    single_correct = sum(1 for r in single if r["cites_correct"])
    out = {
        "total": total,
        "cites_correct": cites_correct,
        "cross_bundle_total": len(cross),
        "cross_bundle_cites_correct": cross_correct,
        "collision_total": len(collision),
        "collision_cites_correct": collision_correct,
        "single_bundle_total": len(single),
        "single_bundle_cites_correct": single_correct,
        "avg_tool_calls": round(sum(r["tool_calls"] for r in records) / total, 2) if total else 0,
        "targets": {
            "answer_correct_target": "18/20",
            "cross_bundle_cites_target": f"{len(cross)}/{len(cross)}",
        },
    }
    if mode == "llm":
        out["answer_correct"] = sum(1 for r in records if r.get("answer_correct"))
    return out


# --- deterministic mode ------------------------------------------------

async def run_deterministic(client: Client, questions: list[dict]) -> list[dict]:
    records = []
    for q in questions:
        tool_calls = 0
        r = await client.call_tool("search", {"query": q["question"], "limit": 1})
        tool_calls += 1
        hits = (r.structured_content or {}).get("result", []) if not r.is_error else []
        top_ref = hits[0]["ref"] if hits else None
        top_score = hits[0]["score"] if hits else None

        got_ok = False
        if top_ref:
            ns, cid = top_ref.split("/", 1)
            r2 = await client.call_tool("get", {"namespace": ns, "id": cid})
            tool_calls += 1
            got_ok = not r2.is_error

        cites_correct = bool(top_ref) and top_ref in q["expected"]
        records.append({
            "id": q["id"],
            "kind": q["kind"],
            "collision": q["collision"],
            "tool_calls": tool_calls,
            "top_ref": top_ref,
            "top_score": top_score,
            "get_ok": got_ok,
            "expected": q["expected"],
            "cites_correct": cites_correct,
        })
        print(f"  {q['id']} [{q['kind']}{'*' if q['collision'] else ''}]: "
              f"top={top_ref} correct={cites_correct}")
    return records


# --- llm mode ------------------------------------------------------------

def mcp_tools_to_anthropic(tools) -> list[dict]:
    out = []
    for t in tools:
        out.append({
            "name": t.name,
            "description": t.description or "",
            "input_schema": t.input_schema,
        })
    return out


def mcp_result_to_tool_result_content(mcp_result) -> list[dict]:
    blocks = []
    for block in mcp_result.content:
        text = getattr(block, "text", None)
        if text is not None:
            blocks.append({"type": "text", "text": text})
    if not blocks:
        blocks.append({"type": "text", "text": ""})
    return blocks


async def answer_question(anthropic_client, mcp_client: Client, tool_defs: list[dict],
                           question: str) -> tuple[str, int]:
    """Run the tool-use loop for one question. Returns (final_text, tool_calls_used)."""
    messages = [{"role": "user", "content": question}]
    tool_calls_used = 0

    while True:
        active_tools = tool_defs if tool_calls_used < MAX_TOOL_CALLS else []
        response = anthropic_client.messages.create(
            model=MODEL_ID,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=active_tools,
            messages=messages,
        )

        if response.stop_reason == "refusal":
            return "(model refused to answer)\nCITES:", tool_calls_used

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        if not tool_use_blocks or tool_calls_used >= MAX_TOOL_CALLS:
            text = "".join(b.text for b in response.content if b.type == "text")
            return text, tool_calls_used

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for tu in tool_use_blocks:
            if tool_calls_used >= MAX_TOOL_CALLS:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": [{"type": "text", "text": "Tool call budget exhausted. Answer now."}],
                    "is_error": True,
                })
                continue
            mcp_result = await mcp_client.call_tool(tu.name, tu.input)
            tool_calls_used += 1
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": mcp_result_to_tool_result_content(mcp_result),
                "is_error": bool(mcp_result.is_error),
            })
        messages.append({"role": "user", "content": tool_results})


def grade_answer(anthropic_client, question: str, expected: str, given: str) -> bool:
    prompt = GRADER_PROMPT_TEMPLATE.format(question=question, expected=expected, given=given)
    response = anthropic_client.messages.create(
        model=MODEL_ID,
        max_tokens=8,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in response.content if b.type == "text").strip().upper()
    return text.startswith("YES")


def parse_cites(text: str) -> list[str]:
    m = CITES_RE.search(text)
    if not m:
        return []
    return [c.strip() for c in m.group(1).split(",") if c.strip()]


async def run_llm(client: Client, questions: list[dict]) -> list[dict]:
    import anthropic  # imported here so `deterministic` mode never needs the package

    anthropic_client = anthropic.Anthropic()
    tools = await client.list_tools()
    tool_defs = mcp_tools_to_anthropic(tools.tools)

    records = []
    for q in questions:
        try:
            final_text, tool_calls_used = await answer_question(
                anthropic_client, client, tool_defs, q["question"])
        except anthropic.APIError as e:  # noqa: BLE001 - record and continue
            final_text, tool_calls_used = f"(API error: {e})\nCITES:", 0

        cites = parse_cites(final_text)
        cites_correct = all(exp in cites for exp in q["expected"])
        try:
            answer_correct = grade_answer(anthropic_client, q["question"], q["answer"], final_text)
        except Exception as e:  # noqa: BLE001
            answer_correct = False
            final_text += f"\n(grading failed: {e})"

        records.append({
            "id": q["id"],
            "kind": q["kind"],
            "collision": q["collision"],
            "tool_calls": tool_calls_used,
            "cites": cites,
            "expected": q["expected"],
            "cites_correct": cites_correct,
            "answer_correct": answer_correct,
            "final_text": final_text,
        })
        print(f"  {q['id']} [{q['kind']}{'*' if q['collision'] else ''}]: "
              f"tool_calls={tool_calls_used} cites_correct={cites_correct} "
              f"answer_correct={answer_correct}")
    return records


# --- reporting -----------------------------------------------------------

def write_json(mode: str, records: list[dict], versions: dict, extra: dict) -> Path:
    out = {
        "mode": mode,
        "versions": versions,
        **extra,
        "questions": records,
        "totals": totals_for(records, mode),
    }
    path = HERE / f"results-{mode}.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return path


def render_table(records: list[dict], mode: str) -> str:
    if mode == "deterministic":
        header = "| id | kind | collision | tool calls | top ref | cites correct |"
        sep = "|---|---|---|---|---|---|"
        rows = [
            f"| {r['id']} | {r['kind']} | {'yes' if r['collision'] else 'no'} | "
            f"{r['tool_calls']} | {r['top_ref'] or '(none)'} | "
            f"{'**yes**' if r['cites_correct'] else 'no'} |"
            for r in records
        ]
    else:
        header = "| id | kind | collision | tool calls | cites correct | answer correct |"
        sep = "|---|---|---|---|---|---|"
        rows = [
            f"| {r['id']} | {r['kind']} | {'yes' if r['collision'] else 'no'} | "
            f"{r['tool_calls']} | {'**yes**' if r['cites_correct'] else 'no'} | "
            f"{'**yes**' if r.get('answer_correct') else 'no'} |"
            for r in records
        ]
    return "\n".join([header, sep, *rows])


def render_section(mode: str, records: list[dict], versions: dict, extra_lines: list[str]) -> str:
    totals = totals_for(records, mode)
    label = "Deterministic mode (floor, not an answer-quality measure)" if mode == "deterministic" \
        else "LLM mode (Claude Code as client)"
    lines = [f"## {label}", ""]
    lines += extra_lines
    lines.append("")
    lines.append(
        f"Versions: python {versions['python']}, mcp {versions['mcp']}, "
        + (f"anthropic {versions.get('anthropic')}, model `{MODEL_ID}`, " if mode == "llm" else "")
        + f"date {versions['date']}."
    )
    lines.append("")
    lines.append(render_table(records, mode))
    lines.append("")
    if mode == "deterministic":
        lines.append(
            f"**Totals:** {totals['cites_correct']}/{totals['total']} top-hit citations correct "
            f"(cross-bundle: {totals['cross_bundle_cites_correct']}/{totals['cross_bundle_total']}, "
            f"collision: {totals['collision_cites_correct']}/{totals['collision_total']}, "
            f"single-bundle: {totals['single_bundle_cites_correct']}/{totals['single_bundle_total']}). "
            "This measures whether the payload contract (namespace + id + ref, verbatim through "
            "search() -> get()) carries identity end to end, and gives a retrieval floor — it does "
            "not read or judge any answer text."
        )
    else:
        lines.append(
            f"**Totals:** {totals['answer_correct']}/{totals['total']} answers judged correct "
            f"(plan target ≥{totals['targets']['answer_correct_target']}); "
            f"{totals['cross_bundle_cites_correct']}/{totals['cross_bundle_total']} cross-bundle "
            f"questions cited correctly (plan target {totals['targets']['cross_bundle_cites_target']}); "
            f"average {totals['avg_tool_calls']} tool calls/question."
        )
    lines.append("")
    return "\n".join(lines)


def update_results_md(mode: str, section: str) -> None:
    marker_begin = f"<!-- BEGIN:{mode} -->"
    marker_end = f"<!-- END:{mode} -->"
    block = f"{marker_begin}\n{section}\n{marker_end}"

    if RESULTS_MD.exists():
        text = RESULTS_MD.read_text(encoding="utf-8")
    else:
        text = "# E4 results: serving via MCP tools\n\n" \
               "Generated by client_harness.py. Re-running a mode replaces its own section below.\n\n"

    pattern = re.compile(re.escape(marker_begin) + r".*?" + re.escape(marker_end), re.DOTALL)
    if pattern.search(text):
        text = pattern.sub(block, text)
    else:
        text = text.rstrip("\n") + "\n\n" + block + "\n"
    RESULTS_MD.write_text(text, encoding="utf-8")


# --- main ------------------------------------------------------------------

async def amain(args: argparse.Namespace) -> int:
    if args.mode == "llm" and not os.environ.get("ANTHROPIC_API_KEY"):
        print("E4 llm mode: ANTHROPIC_API_KEY not set; skipped")
        return 0

    questions = load_questions(args.questions)
    params = make_server_params(args.federation)
    versions = common_versions()

    async with Client(params) as client:
        if args.mode == "deterministic":
            print(f"Running {len(questions)} questions in deterministic mode "
                  f"(search(limit=1) -> get; no LLM)...")
            records = await run_deterministic(client, questions)
            extra = {"server": {"script": str(SERVER_PATH), "federation": str(args.federation)},
                     "note": "Deterministic mode is a retrieval/payload-contract floor, not an "
                              "answer-quality measure — it never reads the answer text."}
            write_json("deterministic", records, versions, extra)
            section = render_section("deterministic", records, versions, [
                "No LLM. For each question: `search(question, limit=1)` then `get(top hit)`. "
                "`cites_correct` = the top hit's `ref` appears in the question's `expected` list.",
            ])
        else:
            versions["anthropic"] = pkg_version("anthropic")
            print(f"Running {len(questions)} questions in llm mode "
                  f"(Claude Code as client, model {MODEL_ID}, max {MAX_TOOL_CALLS} tool calls/question)...")
            records = await run_llm(client, questions)
            extra = {"server": {"script": str(SERVER_PATH), "federation": str(args.federation)},
                     "model": MODEL_ID, "max_tool_calls": MAX_TOOL_CALLS}
            write_json("llm", records, versions, extra)
            section = render_section("llm", records, versions, [
                f"Claude Code as client, model `{MODEL_ID}`, the four MCP tools translated to API tool "
                f"definitions, looping until the model stops calling tools (max {MAX_TOOL_CALLS} tool "
                "calls/question). `cites_correct` = every `expected` ref appears in the model's `CITES:` "
                "line. `answer_correct` = a second API call grades the answer against the known answer.",
            ])

    update_results_md(args.mode, section)
    print(f"\nWrote results-{args.mode}.json and updated {RESULTS_MD.name}.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["llm", "deterministic"], required=True)
    ap.add_argument("--federation", type=Path, default=DEFAULT_FEDERATION)
    ap.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    args = ap.parse_args()
    return asyncio.run(amain(args))


if __name__ == "__main__":
    sys.exit(main())
