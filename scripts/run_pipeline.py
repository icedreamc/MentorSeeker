import argparse

from backend.app.pipeline.true_mentor_search import curiosity_driven_search
from backend.app.pipeline.mentor_enrichment import run_enrichment


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full MentorSeeker pipeline")
    parser.add_argument("--school", required=True, help="School name")
    parser.add_argument("--direction", required=True, help="Research direction")
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--target-mentors", type=int, default=40)
    parser.add_argument("--enrich-limit", type=int, default=5)
    parser.add_argument("--output-dir", default="data")
    args = parser.parse_args()

    raw_path = curiosity_driven_search(
        args.school,
        args.direction,
        max_steps=args.max_steps,
        target_mentor_count=args.target_mentors,
        output_dir=args.output_dir,
    )
    _, enriched_path = run_enrichment(input_file=raw_path, enrich_limit=args.enrich_limit)
    print(f"Pipeline completed. Raw: {raw_path}; Enriched: {enriched_path}")


if __name__ == "__main__":
    main()
