from __future__ import annotations

import argparse

from app.examples import FREE_TEXT_SAMPLE, MESSY_SQL_SAMPLE
from app.pipeline import NormiePipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Normie's end-to-end demo pipeline.")
    parser.add_argument("--sample", choices=["free-text", "sql"], default="free-text")
    parser.add_argument("--bcnf", action="store_true", help="Use BCNF decomposition instead of 3NF synthesis.")
    parser.add_argument("--verify", action="store_true", help="Run the optional Groq semantic verifier.")
    args = parser.parse_args()
    source = FREE_TEXT_SAMPLE if args.sample == "free-text" else MESSY_SQL_SAMPLE
    result = NormiePipeline().run(
        source,
        target_normal_form="BCNF" if args.bcnf else "3NF",
        verify=args.verify,
        allow_demo_fallback=True,
    )
    print("INPUT")
    print(source)
    print("\nEXTRACTION")
    print(result.extraction.model_dump_json(indent=2))
    print("\nNORMALIZATION")
    print(result.normalization.model_dump_json(indent=2))
    print("\nCREATE TABLE OUTPUT")
    print(result.sql)
    print("\nREPORT")
    print(result.report)
    print("\nMERMAID ERD")
    print(result.erd)
    if result.verification:
        print("\nVERIFIER")
        print(result.verification.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
