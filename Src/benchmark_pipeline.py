#!/usr/bin/env python3
"""
Pipeline Performance Benchmark Script
======================================
Reports only metrics that are genuinely measured at runtime. Metrics that
would require an external ground truth (extraction accuracy) or a fixed
human-time assumption (manual-effort reduction) have been removed, because
they cannot be evaluated from a pipeline run alone.

Measured metrics:
  1. Processing time per dataset
  2. Number of files processed per second (throughput)
  3. Metadata completeness (top-field presence and null/NaN analysis)
  4. Failure rate across file types (derived from the pipeline return code,
     captured stderr, and matched-vs-input file counts)

Usage:
    python benchmark_pipeline.py \
        --input ./Input/ORID0087 \
        --output ./Output/Benchmark_ORID0087 \
        --pipeline ./Src/Main_Auto_Processor.py

    Or run all three datasets at once:
    python benchmark_pipeline.py --run-all

Author: Lesly Tsoptio Fougang
Date: June 2026
"""

import os
import sys
import json
import time
import math
import argparse
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
from collections import Counter


def count_files_recursive(directory):
    """Count all files in a directory tree."""
    total = 0
    for root, dirs, files in os.walk(directory):
        total += len(files)
    return total


def count_files_by_extension(directory):
    """Count files grouped by extension."""
    ext_counts = Counter()
    for root, dirs, files in os.walk(directory):
        for f in files:
            ext = Path(f).suffix.lower()
            if not ext:
                ext = "(no extension)"
            ext_counts[ext] += 1
    return dict(ext_counts)


def run_pipeline(pipeline_script, input_dir, output_dir):
    """
    Run the pipeline and capture timing + output.
    Returns (elapsed_seconds, stdout_text, stderr_text, return_code).
    """
    # Clean output directory
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    cmd = [
        sys.executable,
        pipeline_script,
        input_dir,
        output_dir,
        "--batch"
    ]

    print(f"  Running: {' '.join(cmd)}")
    start_time = time.perf_counter()

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=600  # 10-minute timeout
    )

    elapsed = time.perf_counter() - start_time

    return elapsed, result.stdout, result.stderr, result.returncode


def analyse_json_outputs(output_dir):
    """
    Analyse all JSON files in the output directory.
    Returns metrics on completeness, field presence, and null values.
    """
    json_files = list(Path(output_dir).rglob("*.json"))

    results = {
        "total_json_files": len(json_files),
        "files_with_all_top_fields": 0,
        "files_missing_top_fields": 0,
        "missing_fields_detail": [],
        "parse_errors": 0,
        "parse_error_detail": [],
        "null_nan_count": 0,
        "null_nan_fields": [],
        "total_fields_checked": 0,
        "total_samples_extracted": 0,
        "files_analysed": [],
    }

    # The five universal top-level fields
    top_level_fields = [
        "file_name",
        "file_path",
        "file_description",
        "instrument_type",
        "phase_workflow",
    ]

    for jf in json_files:
        try:
            with open(jf, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            results["parse_errors"] += 1
            results["parse_error_detail"].append({
                "file": str(jf.name),
                "error": str(e)
            })
            results["files_analysed"].append({
                "file": str(jf.name),
                "status": "parse_error",
                "error": str(e)
            })
            continue

        # Handle both single dict and list of dicts
        records = data if isinstance(data, list) else [data]

        for record in records:
            if not isinstance(record, dict):
                continue

            file_info = {
                "file": str(jf.name),
                "status": "ok",
                "top_fields_present": [],
                "top_fields_missing": [],
                "null_fields": [],
                "sample_count": 0,
            }

            # Check top-level fields
            for field in top_level_fields:
                results["total_fields_checked"] += 1
                if field in record:
                    value = record[field]
                    file_info["top_fields_present"].append(field)

                    # Check for null/NaN
                    if value is None:
                        results["null_nan_count"] += 1
                        file_info["null_fields"].append(field)
                    elif isinstance(value, float) and math.isnan(value):
                        results["null_nan_count"] += 1
                        file_info["null_fields"].append(field)
                    elif isinstance(value, str) and value.strip().lower() in ("nan", "null", "none", ""):
                        results["null_nan_count"] += 1
                        file_info["null_fields"].append(field)
                else:
                    file_info["top_fields_missing"].append(field)

            # Check for NaN in all nested fields
            null_count_nested = count_nulls_recursive(record)
            results["null_nan_count"] += null_count_nested

            # Count samples
            if "samples" in record and isinstance(record["samples"], list):
                file_info["sample_count"] = len(record["samples"])
                results["total_samples_extracted"] += len(record["samples"])

            # Classify
            if not file_info["top_fields_missing"]:
                results["files_with_all_top_fields"] += 1
            else:
                results["files_missing_top_fields"] += 1
                results["missing_fields_detail"].append({
                    "file": str(jf.name),
                    "missing": file_info["top_fields_missing"]
                })

            if file_info["null_fields"]:
                results["null_nan_fields"].append({
                    "file": str(jf.name),
                    "fields": file_info["null_fields"]
                })

            results["files_analysed"].append(file_info)

    return results


def count_nulls_recursive(obj, path=""):
    """Count null/NaN values in a nested structure."""
    count = 0
    if isinstance(obj, dict):
        for key, value in obj.items():
            count += count_nulls_recursive(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            count += count_nulls_recursive(item, f"{path}[{i}]")
    elif obj is None:
        count += 1
    elif isinstance(obj, float) and math.isnan(obj):
        count += 1
    elif isinstance(obj, str) and obj.strip().lower() in ("nan",):
        count += 1
    return count


def generate_report(dataset_name, input_dir, output_dir,
                    elapsed, total_input_files, ext_counts,
                    json_analysis, stderr_text, return_code):
    """Generate a structured benchmark report for one dataset."""
    matched = json_analysis["total_json_files"]
    skipped = total_input_files - matched
    files_per_second = total_input_files / elapsed if elapsed > 0 else 0

    completeness_pct = 0
    if json_analysis["total_fields_checked"] > 0:
        non_null = json_analysis["total_fields_checked"] - json_analysis["null_nan_count"]
        completeness_pct = (non_null / json_analysis["total_fields_checked"]) * 100

    # Failure rate is derived from real signals captured during the run:
    #   - a non-zero pipeline return code,
    #   - non-empty stderr,
    #   - JSON outputs that failed to parse.
    # A run is counted as failed if the process did not exit cleanly.
    pipeline_failed = (return_code != 0)
    parse_errors = json_analysis["parse_errors"]
    stderr_lines = [ln for ln in (stderr_text or "").splitlines() if ln.strip()]

    report = {
        "dataset": dataset_name,
        "input_directory": str(input_dir),
        "output_directory": str(output_dir),
        "timestamp": datetime.now().isoformat(),
        "pipeline_return_code": return_code,
        "metrics": {
            "1_processing_time": {
                "elapsed_seconds": round(elapsed, 3),
                "elapsed_formatted": f"{int(elapsed // 60)}m {elapsed % 60:.1f}s",
            },
            "2_throughput": {
                "total_input_files": total_input_files,
                "files_matched": matched,
                "files_skipped": skipped,
                "files_per_second": round(files_per_second, 2),
            },
            "3_metadata_completeness": {
                "json_files_produced": json_analysis["total_json_files"],
                "files_with_all_5_top_fields": json_analysis["files_with_all_top_fields"],
                "files_missing_top_fields": json_analysis["files_missing_top_fields"],
                "total_fields_checked": json_analysis["total_fields_checked"],
                "null_or_nan_values": json_analysis["null_nan_count"],
                "completeness_pct": round(completeness_pct, 2),
                "total_samples_extracted": json_analysis["total_samples_extracted"],
                "missing_fields_detail": json_analysis["missing_fields_detail"][:10],
                "null_fields_detail": json_analysis["null_nan_fields"][:10],
            },
            "4_failure_rate": {
                "input_file_types": ext_counts,
                "total_input_files": total_input_files,
                "pipeline_return_code": return_code,
                "pipeline_failed": pipeline_failed,
                "json_parse_errors": parse_errors,
                "stderr_line_count": len(stderr_lines),
                "stderr_sample": stderr_lines[:10],
            },
        }
    }

    return report


def print_summary(report):
    """Print a human-readable summary of one dataset's benchmarks."""
    m = report["metrics"]
    d = report["dataset"]

    print(f"\n{'='*60}")
    print(f"  BENCHMARK RESULTS: {d}")
    print(f"{'='*60}")

    t = m["1_processing_time"]
    print(f"\n  1. Processing time:       {t['elapsed_formatted']} ({t['elapsed_seconds']}s)")

    tp = m["2_throughput"]
    print(f"  2. Throughput:            {tp['files_per_second']} files/sec")
    print(f"     Total files:           {tp['total_input_files']}")
    print(f"     Matched:               {tp['files_matched']}")
    print(f"     Skipped:               {tp['files_skipped']}")

    comp = m["3_metadata_completeness"]
    print(f"  3. Metadata completeness: {comp['completeness_pct']}%")
    print(f"     JSON files produced:   {comp['json_files_produced']}")
    print(f"     All 5 top fields:      {comp['files_with_all_5_top_fields']}")
    print(f"     Null/NaN values:       {comp['null_or_nan_values']}")
    print(f"     Samples extracted:     {comp['total_samples_extracted']}")

    fr = m["4_failure_rate"]
    print(f"  4. Failure signals:       return code {fr['pipeline_return_code']}, "
          f"{fr['json_parse_errors']} parse error(s), "
          f"{fr['stderr_line_count']} stderr line(s)")
    print(f"     Pipeline failed:       {fr['pipeline_failed']}")

    print(f"{'='*60}\n")


def run_benchmark(pipeline_script, input_dir, output_dir, dataset_name):
    """Run a full benchmark for one dataset."""
    print(f"\n--- Benchmarking {dataset_name} ---")
    print(f"  Input:  {input_dir}")
    print(f"  Output: {output_dir}")

    # Count input files
    total_files = count_files_recursive(input_dir)
    ext_counts = count_files_by_extension(input_dir)
    print(f"  Input files: {total_files}")
    print(f"  File types:  {ext_counts}")

    # Run pipeline
    elapsed, stdout, stderr, rc = run_pipeline(
        pipeline_script, input_dir, output_dir
    )
    print(f"  Elapsed: {elapsed:.2f}s (return code: {rc})")

    # Analyse outputs
    print(f"  Analysing JSON outputs...")
    json_analysis = analyse_json_outputs(output_dir)

    # Generate report
    report = generate_report(
        dataset_name, input_dir, output_dir,
        elapsed, total_files, ext_counts,
        json_analysis, stderr, rc
    )

    # Print summary
    print_summary(report)

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Pipeline Performance Benchmark"
    )
    parser.add_argument(
        "--pipeline", default="./Src/Main_Auto_Processor.py",
        help="Path to Main_Auto_Processor.py"
    )
    parser.add_argument(
        "--input", default=None,
        help="Input directory for a single dataset"
    )
    parser.add_argument(
        "--output", default=None,
        help="Output directory for a single dataset"
    )
    parser.add_argument(
        "--name", default="Dataset",
        help="Name for this benchmark run"
    )
    parser.add_argument(
        "--run-all", action="store_true",
        help="Run benchmarks on all three standard datasets"
    )
    parser.add_argument(
        "--report-dir", default="./Benchmark_Reports",
        help="Directory to save JSON benchmark reports"
    )

    args = parser.parse_args()

    os.makedirs(args.report_dir, exist_ok=True)
    all_reports = []

    if args.run_all:
        # Standard LAGE datasets
        datasets = [
            ("ORID0087", "./Input/ORID0087",
             "./Output/Benchmark_ORID0087"),
            ("ORID0085", "./Input/ORID0085",
             "./Output/Benchmark_ORID0085"),
            ("ORID0036", "./Input/ORID0036",
             "./Output/Benchmark_ORID0036"),
        ]
        for name, inp, out in datasets:
            if os.path.exists(inp):
                report = run_benchmark(
                    args.pipeline, inp, out, name
                )
                all_reports.append(report)
            else:
                print(f"\n  WARNING: {inp} not found, skipping.")

    elif args.input and args.output:
        report = run_benchmark(
            args.pipeline, args.input, args.output, args.name
        )
        all_reports.append(report)

    else:
        parser.print_help()
        sys.exit(1)

    # Save combined report
    if all_reports:
        report_path = os.path.join(
            args.report_dir,
            f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(all_reports, f, indent=2, ensure_ascii=False)
        print(f"\nBenchmark report saved to: {report_path}")

        # Print combined summary table
        print(f"\n{'='*70}")
        print(f"  COMBINED SUMMARY")
        print(f"{'='*70}")
        print(f"  {'Dataset':<12} {'Files':>6} {'Time':>8} "
              f"{'Files/s':>8} {'Complete':>9} {'Failed':>7}")
        print(f"  {'-'*12} {'-'*6} {'-'*8} "
              f"{'-'*8} {'-'*9} {'-'*7}")
        for r in all_reports:
            m = r["metrics"]
            print(f"  {r['dataset']:<12} "
                  f"{m['2_throughput']['total_input_files']:>6} "
                  f"{m['1_processing_time']['elapsed_formatted']:>8} "
                  f"{m['2_throughput']['files_per_second']:>8.1f} "
                  f"{m['3_metadata_completeness']['completeness_pct']:>8.1f}% "
                  f"{str(m['4_failure_rate']['pipeline_failed']):>7}")
        print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
