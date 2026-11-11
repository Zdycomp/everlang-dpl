"""Digest of one Gradle test run's outcome, for tools/determinism_check.sh.

The digest covers the exit code plus the sorted "suite|testcase|status" lines from
every module's build/test-results/test/*.xml. When no test XML exists (the build
failed before testing), it covers the sorted "Could not GET ... status code N"
lines from the build log instead, so resolution failures are still compared.

usage: python3 tools/outcome_digest.py <project-dir> <build-log> <exit-code>
prints: <sha256> exit=<n> basis=<xml|could_not_get> cases=<n>
"""
import glob
import hashlib
import os
import re
import sys
import xml.etree.ElementTree as ET


def main():
    proj, log_path, exit_code = sys.argv[1], sys.argv[2], sys.argv[3]

    cases = []
    pattern = os.path.join(proj, "*", "build", "test-results", "test", "*.xml")
    for path in sorted(glob.glob(pattern)):
        root = ET.parse(path).getroot()
        suite = root.get("name", os.path.basename(path))
        for tc in root.iter("testcase"):
            if tc.find("failure") is not None or tc.find("error") is not None:
                status = "fail"
            elif tc.find("skipped") is not None:
                status = "skip"
            else:
                status = "pass"
            cases.append(f"{suite}|{tc.get('name', '')}|{status}")
    cases.sort()

    with open(log_path, encoding="utf-8", errors="replace") as fh:
        log = fh.read()
    refusals = sorted(re.findall(r"Could not GET '[^']+'\. Received status code \d+", log))

    body = cases if cases else refusals
    payload = f"exit={exit_code}\n" + "\n".join(body) + "\n"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    basis = "xml" if cases else "could_not_get"
    print(f"{digest} exit={exit_code} basis={basis} cases={len(cases)}")


if __name__ == "__main__":
    main()
