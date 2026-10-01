// test_verify_particle.cpp
//
// Standalone test harness (no external test framework) for the
// verify_particle CLI safety-verification gate. Invokes the built
// bin/verify_particle binary via popen() for each contract case,
// feeding stdin through popen's "w" pipe, and asserts stdout content
// and exit code.
//
// Run from the 1-phase-cpp/ directory (as `make test` does), so that
// the relative path to the binary resolves correctly.

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <sys/wait.h>

namespace {

const char* kBinaryPath = "./bin/verify_particle";

struct CaseResult {
    std::string stdoutText;
    int exitCode = -1;
    bool popenFailed = false;
};

// Runs the binary with the given argv suffix (appended after the binary
// path) and writes `stdinData` to its stdin. Captures stdout and the
// process exit code.
CaseResult RunCase(const std::string& argsSuffix, const std::string& stdinData) {
    CaseResult result;

    // popen() only gives us a single-direction pipe. To both feed stdin
    // (via popen's "w" mode) and capture stdout, redirect the child's
    // stdout to a temporary file from within the shell command.
    std::string tmpFile = "/tmp/verify_particle_test_out.XXXXXX";
    char tmpTemplate[256];
    std::snprintf(tmpTemplate, sizeof(tmpTemplate), "%s", tmpFile.c_str());
    int fd = mkstemp(tmpTemplate);
    if (fd < 0) {
        result.popenFailed = true;
        return result;
    }
    close(fd);

    std::string fullCommand =
        std::string(kBinaryPath) + " " + argsSuffix + " > " + tmpTemplate;
    FILE* writePipe = popen(fullCommand.c_str(), "w");
    if (writePipe == nullptr) {
        result.popenFailed = true;
        std::remove(tmpTemplate);
        return result;
    }

    if (!stdinData.empty()) {
        size_t written = std::fwrite(stdinData.data(), 1, stdinData.size(), writePipe);
        (void)written; // best-effort; pclose's exit status is authoritative
    }

    int status = pclose(writePipe);
    if (status == -1) {
        result.popenFailed = true;
        std::remove(tmpTemplate);
        return result;
    }

    if (WIFEXITED(status)) {
        result.exitCode = WEXITSTATUS(status);
    } else {
        result.exitCode = -1;
    }

    // Read captured stdout from the temp file.
    FILE* readFile = std::fopen(tmpTemplate, "rb");
    if (readFile != nullptr) {
        char readBuf[8192];
        size_t n;
        while ((n = std::fread(readBuf, 1, sizeof(readBuf), readFile)) > 0) {
            result.stdoutText.append(readBuf, n);
        }
        std::fclose(readFile);
    }
    std::remove(tmpTemplate);

    return result;
}

// Trims a single trailing newline, if present, for comparison purposes.
std::string TrimTrailingNewline(const std::string& s) {
    if (!s.empty() && s.back() == '\n') {
        return s.substr(0, s.size() - 1);
    }
    return s;
}

int gFailures = 0;
int gTotal = 0;

void ExpectCase(const std::string& name, const std::string& argsSuffix,
                 const std::string& stdinData, const std::string& expectedStdout,
                 int expectedExit) {
    gTotal++;
    CaseResult result = RunCase(argsSuffix, stdinData);

    bool pass = true;
    std::string reason;

    if (result.popenFailed) {
        pass = false;
        reason = "popen/pclose failed";
    } else {
        std::string actual = TrimTrailingNewline(result.stdoutText);
        if (actual != expectedStdout) {
            pass = false;
            reason += "stdout mismatch: expected '" + expectedStdout + "' got '" +
                      actual + "'; ";
        }
        if (result.exitCode != expectedExit) {
            pass = false;
            reason += "exit code mismatch: expected " + std::to_string(expectedExit) +
                      " got " + std::to_string(result.exitCode) + "; ";
        }
    }

    if (pass) {
        std::cout << "PASS: " << name << "\n";
    } else {
        std::cout << "FAIL: " << name << " (" << reason << ")\n";
        gFailures++;
    }
}

} // namespace

int main() {
    // confidence=200, stdin="Alpha" -> VALID, exit 0
    ExpectCase("valid_basic", "200", "Alpha", "VALID", 0);

    // confidence=-1, stdin="x" -> INVALID:CONFIDENCE_OUT_OF_RANGE, exit 1
    ExpectCase("confidence_negative", "-1", "x", "INVALID:CONFIDENCE_OUT_OF_RANGE", 1);

    // confidence=257, stdin="x" -> INVALID:CONFIDENCE_OUT_OF_RANGE, exit 1
    ExpectCase("confidence_too_high", "257", "x", "INVALID:CONFIDENCE_OUT_OF_RANGE", 1);

    // confidence="abc", stdin="x" -> INVALID:CONFIDENCE_NOT_INTEGER, exit 1
    ExpectCase("confidence_not_integer", "abc", "x", "INVALID:CONFIDENCE_NOT_INTEGER", 1);

    // confidence=100, stdin="" -> INVALID:VALUE_EMPTY, exit 1
    ExpectCase("value_empty", "100", "", "INVALID:VALUE_EMPTY", 1);

    // confidence=100, stdin exactly 4096 bytes -> VALID, exit 0 (boundary)
    {
        std::string data(4096, 'a');
        ExpectCase("value_exactly_4096", "100", data, "VALID", 0);
    }

    // confidence=100, stdin exactly 4097 bytes -> INVALID:VALUE_TOO_LONG, exit 1
    {
        std::string data(4097, 'a');
        ExpectCase("value_exactly_4097", "100", data, "INVALID:VALUE_TOO_LONG", 1);
    }

    // wrong argc: 0 extra args (binary alone, argc==1)
    ExpectCase("usage_no_args", "", "x", "INVALID:USAGE", 2);

    // wrong argc: 2+ extra args (argc==3)
    ExpectCase("usage_extra_args", "100 200", "x", "INVALID:USAGE", 2);

    std::cout << "\n" << (gTotal - gFailures) << "/" << gTotal << " cases passed.\n";

    return gFailures == 0 ? 0 : 1;
}
