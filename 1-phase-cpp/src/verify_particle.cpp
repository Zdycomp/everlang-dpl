// verify_particle.cpp
//
// Native CLI safety-verification gate for the Everlang/DPL self-healing
// Archive. The Python archive shells out to this binary before persisting
// a write, to verify a particle's confidence and value are well-formed.
//
// Contract (see 1-phase-cpp/README.md for the authoritative copy):
//   Invocation: verify_particle <confidence>
//     - exactly one argv (the confidence, as text)
//     - the particle's "value" is supplied entirely on stdin (read to EOF)
//
//   Validation, in order, first failure wins:
//     1. argc != 2                                -> INVALID:USAGE            exit 2
//     2. confidence not a full base-10 integer     -> INVALID:CONFIDENCE_NOT_INTEGER  exit 1
//     3. confidence not in [0, 256]                -> INVALID:CONFIDENCE_OUT_OF_RANGE exit 1
//     4. stdin empty (0 bytes read)                -> INVALID:VALUE_EMPTY      exit 1
//     5. stdin longer than 4096 bytes               -> INVALID:VALUE_TOO_LONG   exit 1
//     6. otherwise                                  -> VALID                    exit 0
//
// Memory safety: no dynamic allocation beyond a single fixed-size stack
// buffer of exactly 4097 bytes (4096 data bytes + 1 sentinel byte used to
// detect overflow). Every read() return value is checked explicitly. No
// sprintf/strcpy/gets. Integer parsing uses strtol with full-string
// validation via endptr.

#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <unistd.h>

namespace {

constexpr size_t kMaxValueBytes = 4096;
constexpr size_t kBufferSize = kMaxValueBytes + 1; // +1 sentinel byte

// Parses `text` as a base-10 integer using the entire string (no
// leading/trailing whitespace, no trailing garbage). Returns true and
// sets `out` on success.
bool ParseFullInteger(const char* text, long& out) {
    if (text == nullptr || text[0] == '\0') {
        return false;
    }

    errno = 0;
    char* endptr = nullptr;
    long value = std::strtol(text, &endptr, 10);

    if (errno == ERANGE) {
        return false;
    }
    if (endptr == text) {
        // No digits were consumed at all.
        return false;
    }
    if (*endptr != '\0') {
        // Trailing characters (including whitespace) after the number.
        return false;
    }

    out = value;
    return true;
}

// Reads from stdin into `buffer` (capacity `capacity`), stopping at EOF or
// once `capacity` bytes have been read. Every read() call's return value is
// checked explicitly; no unbounded loop (bounded by `capacity`).
// Returns the number of bytes read, or -1 on a read() error.
long ReadStdinBounded(char* buffer, size_t capacity) {
    size_t total = 0;
    while (total < capacity) {
        ssize_t n = read(STDIN_FILENO, buffer + total, capacity - total);
        if (n < 0) {
            if (errno == EINTR) {
                continue;
            }
            return -1;
        }
        if (n == 0) {
            // EOF.
            break;
        }
        total += static_cast<size_t>(n);
    }
    return static_cast<long>(total);
}

} // namespace

int main(int argc, char** argv) {
    // 1. Exactly one argument (the confidence).
    if (argc != 2) {
        std::cout << "INVALID:USAGE\n";
        return 2;
    }

    // 2. Confidence must parse as a full base-10 integer.
    long confidence = 0;
    if (!ParseFullInteger(argv[1], confidence)) {
        std::cout << "INVALID:CONFIDENCE_NOT_INTEGER\n";
        return 1;
    }

    // 3. Confidence must be in [0, 256].
    if (confidence < 0 || confidence > 256) {
        std::cout << "INVALID:CONFIDENCE_OUT_OF_RANGE\n";
        return 1;
    }

    // 4/5. Read stdin into a fixed 4097-byte stack buffer (4096 data +
    // 1 sentinel byte to detect overflow beyond the 4096-byte limit).
    char buffer[kBufferSize];
    std::memset(buffer, 0, sizeof(buffer));

    long bytesRead = ReadStdinBounded(buffer, kBufferSize);
    if (bytesRead < 0) {
        // A read() error occurred; treat conservatively as empty value.
        std::cout << "INVALID:VALUE_EMPTY\n";
        return 1;
    }

    if (bytesRead == 0) {
        std::cout << "INVALID:VALUE_EMPTY\n";
        return 1;
    }

    if (static_cast<size_t>(bytesRead) > kMaxValueBytes) {
        // Sentinel byte was filled: more than 4096 bytes were available.
        std::cout << "INVALID:VALUE_TOO_LONG\n";
        return 1;
    }

    std::cout << "VALID\n";
    return 0;
}
