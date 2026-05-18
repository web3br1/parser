from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]

DEFAULT_CLASSIFICATION_MODELS = [
    "gemma4:31b",
    "glm-4.7-flash:latest",
    "qwen3.6:27b",
]
DEFAULT_EXTRACTION_MODELS = [
    "kwangsuklee/Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-GGUF:latest",
    "hf.co/hesamation/Qwen3.6-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-GGUF:Q4_K_M",
    "qwen3.6:27b",
]


class OllamaClient:
    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def generate(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            data = json.loads(response.read().decode())
        if not isinstance(data, dict):
            raise RuntimeError("Ollama returned non-object response")
        return data


def default_cases() -> list[dict[str, str]]:
    return [
        {
            "task": "classification",
            "prompt": (
                "Classifique o texto em JSON estrito no formato "
                '{"classifications":[{"classification":"service_price","confidence":0.95,'
                '"reason":"preco explicito"}]}. Use apenas estes tipos: service_price, '
                "business_hours, payment_method, contact_info, faq_item, discount_rule, "
                "cancellation_policy, unknown. Texto: Corte feminino R$ 120."
            ),
            "expected_contains": "service_price",
        },
        {
            "task": "classification",
            "prompt": (
                "Classifique o texto em JSON estrito no formato "
                '{"classifications":[{"classification":"business_hours","confidence":0.95,'
                '"reason":"horario explicito"}]}. Use apenas estes tipos: service_price, '
                "business_hours, payment_method, contact_info, faq_item, discount_rule, "
                "cancellation_policy, unknown. Texto: Atendemos de segunda a sexta, das 9h as 18h."
            ),
            "expected_contains": "business_hours",
        },
        {
            "task": "extraction",
            "prompt": (
                "Extraia um service_price em JSON estrito no formato "
                '{"status":"ok","fact_type":"service_price","data":{"service_name":"Corte feminino",'
                '"price_amount":120,"currency":"BRL","price_type":"fixed"},'
                '"evidence_span":{"quote":"Corte feminino R$ 120","char_start":0,"char_end":23},'
                '"ambiguities":[]}. Texto: Corte feminino R$ 120.'
            ),
            "expected_contains": "price_amount",
        },
    ]


def run_benchmark_case(
    client: Any,
    *,
    model: str,
    task_name: str,
    prompt: str,
    expected_contains: str,
    keep_alive: str,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "keep_alive": keep_alive,
        "options": {"temperature": 0},
    }
    started = time.perf_counter()
    response = client.generate(payload)
    wall_seconds = round(time.perf_counter() - started, 4)
    raw = str(response.get("response") or "")
    parse_ok = _is_json(raw)
    prompt_eval_duration = _int(response.get("prompt_eval_duration"))
    eval_duration = _int(response.get("eval_duration"))
    prompt_tokens = _int(response.get("prompt_eval_count"))
    output_tokens = _int(response.get("eval_count"))
    return {
        "model": model,
        "task": task_name,
        "parse_ok": parse_ok,
        "expected_ok": expected_contains in raw,
        "expected_contains": expected_contains,
        "wall_seconds": wall_seconds,
        "total_seconds": _ns_to_seconds(response.get("total_duration")),
        "load_seconds": _ns_to_seconds(response.get("load_duration")),
        "prompt_eval_seconds": _ns_to_seconds(prompt_eval_duration),
        "eval_seconds": _ns_to_seconds(eval_duration),
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "prompt_tokens_per_second": _tokens_per_second(prompt_tokens, prompt_eval_duration),
        "output_tokens_per_second": _tokens_per_second(output_tokens, eval_duration),
        "response_preview": raw[:300],
    }


def run_benchmark(
    client: OllamaClient,
    *,
    classification_models: list[str],
    extraction_models: list[str],
    tasks: set[str],
    keep_alive: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in filter_cases(default_cases(), tasks):
        models = classification_models if case["task"] == "classification" else extraction_models
        for model in models:
            rows.append(
                run_benchmark_case(
                    client,
                    model=model,
                    task_name=case["task"],
                    prompt=case["prompt"],
                    expected_contains=case["expected_contains"],
                    keep_alive=keep_alive,
                )
            )
    return rows


def filter_cases(cases: list[dict[str, str]], tasks: set[str]) -> list[dict[str, str]]:
    return [case for case in cases if case["task"] in tasks]


def render_markdown_summary(rows: list[dict[str, Any]]) -> str:
    ordered = sorted(
        rows,
        key=lambda row: (
            row["task"],
            not row["expected_ok"],
            not row["parse_ok"],
            row["total_seconds"],
        ),
    )
    lines = [
        "# Ollama Benchmark",
        "",
        "| model | task | parse | expected | total s | load s | output tokens/s | tokens |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in ordered:
        lines.append(
            "| {model} | {task} | {parse_ok} | {expected_ok} | {total_seconds:.3f} | "
            "{load_seconds:.3f} | {output_tokens_per_second:.2f} | {prompt_tokens}/{output_tokens} |".format(
                **row
            )
        )
    lines.append("")
    lines.append("Ordenacao: por tarefa, resposta esperada, JSON parseavel e menor tempo total.")
    return "\n".join(lines)


def write_outputs(rows: list[dict[str, Any]], output_json: Path, output_md: Path) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
    output_md.write_text(render_markdown_summary(rows), encoding="utf-8")


def _is_json(raw: str) -> bool:
    try:
        json.loads(raw)
    except json.JSONDecodeError:
        return False
    return True


def _int(value: Any) -> int:
    return value if isinstance(value, int) else 0


def _ns_to_seconds(value: Any) -> float:
    return round(_int(value) / 1_000_000_000, 4)


def _tokens_per_second(tokens: int, duration_ns: int) -> float:
    if tokens <= 0 or duration_ns <= 0:
        return 0.0
    return round(tokens / duration_ns * 1_000_000_000, 4)


def _split_models(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark local Ollama models for pilot tasks.")
    parser.add_argument("--base-url", default=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    parser.add_argument("--timeout-seconds", type=float, default=900)
    parser.add_argument("--keep-alive", default="20m")
    parser.add_argument(
        "--tasks",
        default="classification,extraction",
        help="Comma-separated task names: classification, extraction.",
    )
    parser.add_argument(
        "--classification-models",
        default=",".join(DEFAULT_CLASSIFICATION_MODELS),
        help="Comma-separated model names.",
    )
    parser.add_argument(
        "--extraction-models",
        default=",".join(DEFAULT_EXTRACTION_MODELS),
        help="Comma-separated model names.",
    )
    parser.add_argument("--output-json", default=".run/ollama-benchmark.json")
    parser.add_argument("--output-md", default=".run/ollama-benchmark.md")
    args = parser.parse_args()

    client = OllamaClient(args.base_url, args.timeout_seconds)
    rows = run_benchmark(
        client,
        classification_models=_split_models(args.classification_models),
        extraction_models=_split_models(args.extraction_models),
        tasks=set(_split_models(args.tasks)),
        keep_alive=args.keep_alive,
    )
    write_outputs(rows, Path(args.output_json), Path(args.output_md))
    print(render_markdown_summary(rows))


if __name__ == "__main__":
    main()
