"""Run the benchmark with any OpenAI-compatible model (OpenRouter by default).

Our own small agent loop replaces Claude Code: it starts server.py over MCP, gives the
model the working rules (skills/shapebert/SKILL.md) and the server's tools, runs the tool calls it asks for, and scores
the part in FreeCAD. The API key is read from OPENROUTER_API_KEY and never logged.

    python bench/run_agent.py --model devstral --cases L1-box
    python bench/run_agent.py --model mistral-medium --repeat 3
    python bench/run_agent.py --model gpt-oss --variant bare
"""

import argparse
import asyncio
import csv
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from run_claude import PROMPT_SUFFIX, count_objects, reset_freecad, summary  # noqa: E402
from score import CASES, score_ask, score_build_quality, score_case  # noqa: E402

API_URL = os.environ.get("FREECAD_MCP_BENCH_API", "https://openrouter.ai/api/v1/chat/completions")
KEY_VAR = "OPENROUTER_API_KEY"

# Short names for the models we compare; the flag says whether the model can read the
# screenshots get_view returns.
MODELS = {
    "mistral-medium": ("mistralai/mistral-medium-3-5", True),
    "devstral": ("mistralai/devstral-2512", False),
    "gemma": ("google/gemma-4-31b-it", True),
    "gpt-oss": ("openai/gpt-oss-120b", False),
}
BARE_TOOLS = {"run_freecad_code", "get_document_info"}
NON_INTERACTIVE = (
    "You run without a human in the loop: nobody will answer follow-up questions. "
    "If a critical value is missing, reply with your questions and build nothing."
)
CSV_FIELDS = [
    "case",
    "repeat",
    "variant",
    "model",
    "score",
    "seconds",
    "turns",
    "tool_calls",
    "tool_errors",
    "prompt_tokens",
    "cached_tokens",
    "completion_tokens",
    "cost_usd",
    "structure_score",
    "structure_issues",
    "edit_score",
    "error",
    "checks",
    "edit_checks",
    "final_text",
]


class ApiError(Exception):
    pass


def to_openai_tools(mcp_tools, only=None):
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": t.inputSchema or {"type": "object", "properties": {}},
            },
        }
        for t in mcp_tools
        if only is None or t.name in only
    ]


def chat(model, messages, tools, attempts=3):
    key = os.environ.get(KEY_VAR)
    if not key:
        raise ApiError(f"{KEY_VAR} is not set for this terminal")
    body = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "temperature": 0.2,
        "usage": {"include": True},
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "X-Title": "freecad-mcp-bench",
        },
    )
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # Only the response body is shown; it never contains the key.
            detail = e.read().decode("utf-8", "replace")[:400]
            if e.code in (429, 500, 502, 503) and attempt < attempts:
                time.sleep(5 * attempt)
                continue
            raise ApiError(f"HTTP {e.code}: {detail}") from None
        except urllib.error.URLError as e:
            if attempt < attempts:
                time.sleep(5 * attempt)
                continue
            raise ApiError(f"network error: {e.reason}") from None
    raise ApiError("no reply")


def tool_messages(call_id, result, vision):
    """Turn an MCP tool result into chat messages. Images go in a follow-up user
    message because tool messages can only hold text."""
    texts, images = [], []
    for part in result.content:
        if part.type == "text":
            texts.append(part.text)
        elif part.type == "image":
            images.append(part)
    if images and not vision:
        texts.append("[screenshot omitted: this model cannot read images]")
    messages = [{"role": "tool", "tool_call_id": call_id, "content": "\n".join(texts) or "(empty result)"}]
    if images and vision:
        content = [{"type": "text", "text": "Screenshot returned by the tool:"}]
        content += [
            {"type": "image_url", "image_url": {"url": f"data:{i.mimeType};base64,{i.data}"}} for i in images
        ]
        messages.append({"role": "user", "content": content})
    return messages


def parse_arguments(raw):
    try:
        args = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return None
    return args if isinstance(args, dict) else None


async def solve(prompt, model, vision, variant, max_turns, max_tokens):
    # The server only needs FreeCAD settings, so the API key is kept out of its environment.
    env = {k: v for k, v in os.environ.items() if k != KEY_VAR}
    env["FREECAD_MCP_ALLOW_CODE"] = "1"
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "server.py")], env=env)
    stats = {"turns": 0, "tool_calls": 0, "tool_errors": 0, "prompt_tokens": 0, "cached_tokens": 0}
    stats.update({"completion_tokens": 0, "cost_usd": 0.0, "tools_used": {}})

    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        listed = await session.list_tools()
        tools = to_openai_tools(listed.tools, BARE_TOOLS if variant == "bare" else None)
        system = NON_INTERACTIVE
        if variant == "full":
            # Same working rules the plugin skill gives Claude; kept first so providers can cache them.
            rules = (ROOT / "skills" / "shapebert" / "SKILL.md").read_text(encoding="utf-8")
            system = rules.split("---", 2)[2].lstrip() + "\n\n" + NON_INTERACTIVE
        messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        stats["transcript"] = messages

        for _ in range(max_turns):
            reply = chat(model, messages, tools)
            stats["turns"] += 1
            usage = reply.get("usage") or {}
            stats["prompt_tokens"] += usage.get("prompt_tokens") or 0
            stats["completion_tokens"] += usage.get("completion_tokens") or 0
            stats["cached_tokens"] += (usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
            stats["cost_usd"] += usage.get("cost") or 0.0

            if stats["prompt_tokens"] + stats["completion_tokens"] > max_tokens:
                return "(stopped: token budget reached)", stats

            message = reply["choices"][0]["message"]
            calls = message.get("tool_calls") or []
            messages.append(
                {
                    "role": "assistant",
                    "content": message.get("content"),
                    **({"tool_calls": calls} if calls else {}),
                }
            )
            if not calls:
                return message.get("content") or "", stats

            for call in calls:
                stats["tool_calls"] += 1
                name = call["function"]["name"]
                stats["tools_used"][name] = stats["tools_used"].get(name, 0) + 1
                args = parse_arguments(call["function"].get("arguments"))
                if args is None:
                    stats["tool_errors"] += 1
                    messages.append(
                        {"role": "tool", "tool_call_id": call["id"], "content": "Invalid JSON arguments."}
                    )
                    continue
                result = await session.call_tool(call["function"]["name"], args)
                if result.isError:
                    stats["tool_errors"] += 1
                messages.extend(tool_messages(call["id"], result, vision))
    return "(stopped: turn limit reached)", stats


def run_case(case, model, vision, variant, max_turns, max_tokens):
    reset_freecad()
    started = time.time()
    error = False
    try:
        prompt = case["prompt"] + PROMPT_SUFFIX
        text, stats = asyncio.run(solve(prompt, model, vision, variant, max_turns, max_tokens))
    except ApiError as e:
        text, stats, error = f"API error: {e}", {}, True
    seconds = time.time() - started

    try:
        if case.get("should_ask"):
            result = score_ask(case, text, count_objects())
        else:
            result = score_case(case, "Result")
            result.update(score_build_quality(case))
    except Exception as e:  # noqa: BLE001 - one broken case must not end a paid run
        result = {
            "case": case["id"],
            "score": 0.0,
            "checks": [{"check": "scoring", "pass": False, "detail": repr(e)}],
        }
    result.update(stats)
    result.update(
        {
            "variant": variant,
            "model": model,
            "seconds": round(seconds, 1),
            "cost_usd": round(stats.get("cost_usd", 0.0), 5),
            "error": error,
            "final_text": text[:500],
        }
    )
    return result


def write_rows(rows, path):
    # Rewritten after every case, so a crash or Ctrl+C keeps what was already paid for.
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **row,
                    "checks": json.dumps(row.get("checks")),
                    "edit_checks": json.dumps(row.get("edit_checks")),
                    "structure_issues": json.dumps(row.get("structure_issues")),
                }
            )


def save_transcript(row, path):
    """The whole conversation of one case, to see where a model went wrong. Screenshots
    are replaced by a marker and the long system prompt is cut, to keep the file small."""
    messages = []
    for message in row.get("transcript") or []:
        message = dict(message)
        if message["role"] == "system":
            message["content"] = message["content"][:300] + " [...]"
        elif isinstance(message.get("content"), list):
            message["content"] = [
                {"type": "image_url", "image_url": "[screenshot]"}
                if part.get("type") == "image_url"
                else part
                for part in message["content"]
            ]
        messages.append(message)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(messages, indent=1, ensure_ascii=False), encoding="utf-8")


def log_usage(row, path):
    keys = ("case", "repeat", "model", "variant", "turns", "tool_calls", "tool_errors")
    keys += (
        "prompt_tokens",
        "cached_tokens",
        "completion_tokens",
        "cost_usd",
        "score",
        "structure_score",
        "edit_score",
        "tools_used",
    )
    record = {"time": dt.datetime.now().isoformat(timespec="seconds"), **{k: row.get(k) for k in keys}}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--model", required=True, help=f"short name ({', '.join(MODELS)}) or an OpenRouter id"
    )
    parser.add_argument("--vision", action="store_true", help="the model reads images (for raw ids)")
    parser.add_argument("--variant", default="full", choices=["full", "bare"])
    parser.add_argument("--cases", nargs="*")
    parser.add_argument("--set", default="all", choices=["all", "v1", "v2"])
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--max-turns", type=int, default=40)
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=600_000,
        help="stop a case once its prompt and output tokens pass this (protects the budget)",
    )
    args = parser.parse_args()

    model, vision = MODELS.get(args.model, (args.model, args.vision))
    selected = args.cases or [cid for cid, c in CASES.items() if args.set in ("all", c.get("set", "v1"))]
    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    label = args.model.replace("/", "_")

    csv_path = out_dir / f"{label}_{args.variant}_{stamp}.csv"
    rows = []
    for case_id in selected:
        for repeat in range(1, args.repeat + 1):
            row = run_case(CASES[case_id], model, vision, args.variant, args.max_turns, args.max_tokens)
            row["repeat"] = repeat
            rows.append(row)
            log_usage(row, out_dir / "token-usage.jsonl")
            save_transcript(row, out_dir / "transcripts" / f"{label}_{stamp}_{case_id}_r{repeat}.json")
            write_rows(rows, csv_path)
            tokens = row.get("prompt_tokens", 0) + row.get("completion_tokens", 0)
            print(
                f"{case_id:<24} run {repeat}  score {row['score']:.2f}  {row['seconds']}s  "
                f"{tokens} tok  ${row['cost_usd']:.4f}" + ("  API ERROR" if row["error"] else "")
            )
            if row["error"]:
                print(f"  {row['final_text']}")

    report = summary(rows, f"Benchmark {stamp} ({args.variant}, model {model})")
    (out_dir / f"{label}_{args.variant}_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"\nWrote {csv_path}")


if __name__ == "__main__":
    main()
