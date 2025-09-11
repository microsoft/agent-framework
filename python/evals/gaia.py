#!/usr/bin/env python
import argparse, asyncio, os, re, string, json, orjson, random
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Iterable

from huggingface_hub import snapshot_download
from tqdm import tqdm
from tenacity import retry, stop_after_attempt, wait_exponential

from openai import AsyncOpenAI
from datasets import Dataset

# ---------------------------
# GAIA official-ish scoring (ported from HF leaderboard scorer.py)
# Source: https://huggingface.co/spaces/gaia-benchmark/leaderboard/blob/main/scorer.py
# ---------------------------
def _normalize_number_str(number_str: str) -> float:
    for ch in ["$", "%", ","]:
        number_str = number_str.replace(ch, "")
    try:
        return float(number_str)
    except ValueError:
        return float("inf")

def _split_string(s: str, chars: List[str] = [",", ";"]) -> List[str]:
    return re.split(f"[{''.join(chars)}]", s)

def _normalize_str(s: str, remove_punct: bool = True) -> str:
    no_spaces = re.sub(r"\s", "", s or "")
    if remove_punct:
        table = str.maketrans("", "", string.punctuation)
        return no_spaces.lower().translate(table)
    return no_spaces.lower()

def gaia_question_scorer(model_answer: str, ground_truth: str) -> bool:
    def is_float(x: Any) -> bool:
        try:
            float(x)
            return True
        except Exception:
            return False

    if model_answer is None:
        model_answer = "None"

    if is_float(ground_truth):
        # numeric exact match after normalization
        return _normalize_number_str(model_answer) == float(ground_truth)

    elif any(ch in ground_truth for ch in [",", ";"]):
        # list with per-element compare (number or string)
        gt_elems = _split_string(ground_truth)
        ma_elems = _split_string(model_answer)
        if len(gt_elems) != len(ma_elems):
            return False
        comparisons = []
        for ma, gt in zip(ma_elems, gt_elems):
            if is_float(gt):
                comparisons.append(_normalize_number_str(ma) == float(gt))
            else:
                comparisons.append(_normalize_str(ma, remove_punct=False) == _normalize_str(gt, remove_punct=False))
        return all(comparisons)

    else:
        # string normalize + exact
        return _normalize_str(model_answer) == _normalize_str(ground_truth)

# ---------------------------
# Dataset loading utilities
# Notes:
#  - GAIA lives in a gated HF dataset with JSONL metadata files.
#  - We download the full repo snapshot, then parse every metadata.jsonl we find.
#  - We ONLY evaluate items that include a public "answer" (dev/validation set).
#  - Fields vary slightly by release; we defensively probe typical keys.
# Docs: dataset & leaderboard page; validation set is public. 
# ---------------------------

@dataclass
class GaiaItem:
    id: str
    question: str
    level: Optional[int]
    answer: Optional[str]
    file_name: Optional[str]
    raw: Dict[str, Any]

def _read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("rb") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                yield orjson.loads(line)
            except Exception:
                yield json.loads(line)

def load_gaia_local(repo_dir: Path, wanted_levels: Optional[List[int]] = None, max_n: Optional[int] = None) -> List[GaiaItem]:
    items: List[GaiaItem] = []
    for p in repo_dir.rglob("metadata.jsonl"):
        for rec in _read_jsonl(p):
            # Robustly extract fields used across variants
            q = rec.get("Question") or rec.get("question") or rec.get("query") or rec.get("prompt")
            ans = rec.get("Final answer") or rec.get("answer") or rec.get("final_answer")  # dev/validation usually has this
            qid = str(rec.get("task_id") or rec.get("question_id") or rec.get("id") or rec.get("uuid") or f"{p.stem}:{len(items)}")
            lvl = rec.get("Level") or rec.get("level")
            fname = rec.get("file_name") or rec.get("filename") or None

            # Only evaluate examples with public answers (dev/validation split)
            if not q or ans is None:
                continue

            if wanted_levels and (lvl not in wanted_levels):
                continue

            items.append(GaiaItem(id=qid, question=q, level=lvl, answer=str(ans), file_name=fname, raw=rec))

    # Shuffle to help with rate-limits and fairness if max_n is provided
    random.shuffle(items)
    if max_n:
        items = items[:max_n]
    return items

# ---------------------------
# OpenAI agent call
# ---------------------------

def build_user_prompt(question: str) -> str:
    # GAIA expects a short, unambiguous final answer.
    # Keep the agent simple; no browsing/tools in this minimal baseline.
    return (
        "You will be given one real-world question.\n"
        "Think briefly if needed, then output ONLY the final answer. No steps. No extra text.\n\n"
        f"Question:\n{question}\n\n"
        "Final answer:"
    )

SYSTEM_PROMPT = (
    "You are a concise assistant. Provide a single, exact answer. "
    "If the question is ambiguous, answer with your best single guess."
)

@retry(wait=wait_exponential(min=1, max=10), stop=stop_after_attempt(3))
async def run_one(client: AsyncOpenAI, model: str, item: GaiaItem, temperature: float = 0.0, timeout: int = 120) -> Tuple[str, GaiaItem]:
    user_msg = build_user_prompt(item.question)
    resp = await client.responses.create(
        model=model,
        timeout=timeout,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        # For determinism in baseline
        temperature=temperature,
        max_output_tokens=256,
    )
    # Extract top-level text (Responses API)
    out = ""
    if resp.output and len(resp.output) > 0:
        # Concatenate all text segments
        parts = []
        for block in resp.output:
            if block.type == "message":
                for c in block.content or []:
                    if c.type == "output_text" and c.text:
                        parts.append(c.text)
            elif block.type == "output_text" and getattr(block, "content", None):
                parts.append(block.content)
        out = "".join(parts).strip()
    elif getattr(resp, "output_text", None):
        out = resp.output_text.strip()
    return out, item

async def run_all(
    items: List[GaiaItem],
    model: str,
    parallel: int = 8,
    temperature: float = 0.0,
) -> List[Tuple[str, GaiaItem]]:
    client = AsyncOpenAI()
    sem = asyncio.Semaphore(parallel)

    async def _wrapped(item: GaiaItem):
        async with sem:
            return await run_one(client, model, item, temperature=temperature)

    results = []
    for fut in tqdm(asyncio.as_completed([_wrapped(it) for it in items]), total=len(items), desc="Evaluating"):
        try:
            results.append(await fut)
        except Exception as e:
            results.append(("", it))  # best-effort; mark empty output
    return results

# ---------------------------
# Aggregate + report
# ---------------------------

def evaluate(results: List[Tuple[str, GaiaItem]]) -> Dict[str, Any]:
    rows = []
    correct = 0
    for pred, item in results:
        gt = item.answer
        is_correct = gaia_question_scorer(pred, gt)
        correct += 1 if is_correct else 0
        rows.append({
            "id": item.id,
            "level": item.level,
            "prediction": pred,
            "answer": gt,
            "correct": bool(is_correct),
        })
    acc = correct / max(1, len(results))
    return {"accuracy": acc, "n": len(results), "rows": rows}

# ---------------------------
# Main
# ---------------------------

def main():
    ap = argparse.ArgumentParser(description="Run a basic OpenAI Responses API baseline on GAIA.")
    ap.add_argument("--levels", nargs="+", type=int, default=[1], help="Which GAIA levels to include (e.g., 1 2 3).")
    ap.add_argument("--max-n", type=int, default=None, help="Optional cap on number of examples.")
    ap.add_argument("--parallel", type=int, default=8, help="Parallel async concurrency.")
    ap.add_argument("--model", type=str, default="gpt-4.1-mini", help="OpenAI model for Responses API.")
    ap.add_argument("--out", type=str, default="gaia_results.jsonl", help="Where to save detailed per-item results.")
    ap.add_argument("--data-dir", type=str, default="data_gaia_hub", help="Where to cache the HF snapshot.")
    args = ap.parse_args()

    # 1) Download gated dataset snapshot (requires HF_TOKEN + access grant)
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise RuntimeError("HF_TOKEN is not set. Please export your Hugging Face access token with GAIA access.")
    local_dir = snapshot_download(
        repo_id="gaia-benchmark/GAIA",
        repo_type="dataset",
        token=token,
        local_dir=args.data_dir,
        local_dir_use_symlinks=False,
        force_download=False,
        tqdm_class=tqdm,
    )

    # 2) Parse metadata.jsonl entries with public answers (dev/validation)
    items = load_gaia_local(Path(local_dir), wanted_levels=args.levels, max_n=args.max_n)
    if not items:
        raise RuntimeError(
            "No GAIA items with public answers were found. "
            "Make sure you have dataset access and you accepted the terms. "
            "Also ensure you selected a level that exists in the dev/validation split."
        )

    print(f"Loaded {len(items)} GAIA items (levels={args.levels}). Running {args.model} ...")

    # 3) Run the basic agent in parallel
    results = asyncio.run(run_all(items, model=args.model, parallel=args.parallel))

    # 4) Grade with GAIA scorer and report accuracy
    report = evaluate(results)
    print(f"\nAccuracy: {report['accuracy']:.3f} over n={report['n']} items")

    # 5) Save detailed rows
    out_path = Path(args.out)
    with out_path.open("w", encoding="utf-8") as f:
        for row in report["rows"]:
            f.write(orjson.dumps(row).decode("utf-8") + "\n")
    print(f"Saved per-item results to {out_path.resolve()}")

if __name__ == "__main__":
    main()
