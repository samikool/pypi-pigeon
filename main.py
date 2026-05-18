#!/usr/bin/env python3
"""
pymirror — airgapped PyPI mirror toolkit

Commands:
  generate-conf   Generate bandersnatch.conf from config.py
  download        Download supplement packages to supplement/dist/
  merge           Merge supplement/dist/ into the served mirror
"""
import runpy
import sys


def usage():
    print(__doc__)
    sys.exit(0)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        usage()

    match sys.argv[1]:
        case "generate-conf":
            import generate_conf
            generate_conf.main() if hasattr(generate_conf, "main") else None
            # generate_conf uses __main__ block, so run it directly
            runpy.run_path("generate_conf.py", run_name="__main__")
        case "download":
            runpy.run_path("supplement/download.py", run_name="__main__")
        case "merge":
            from merge import merge
            merge()
        case _:
            print(f"Unknown command: {sys.argv[1]}")
            usage()
