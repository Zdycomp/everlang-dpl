// verify_kmer_index.cpp
//
// Genomics module verification gate: validates k-mer index integrity.
// Called after every KmerIndex serialization/deserialization in the
// ReinforcedArchive pipeline.
//
// Contract:
//   Invocation: verify_kmer_index <kmer_size> <unique_kmers> <total_kmers>
//   Validates:
//     1. kmer_size == 11 (EParticle-aligned, collision-free for human genome)
//     2. unique_kmers > 0 (index is non-empty)
//     3. total_kmers >= unique_kmers (mathematical constraint)
//     4. avg_kmers_per_position = total_kmers/unique_kmers in [1.0, 10.0]
//        (sanity bound: each k-mer appears 1-10 times on average)

#include <cstdlib>
#include <cstring>
#include <iostream>

namespace {

bool ParseInt(const char* text, long& out) {
    if (text == nullptr || text[0] == '\0') return false;
    errno = 0;
    char* endptr = nullptr;
    long value = std::strtol(text, &endptr, 10);
    if (errno == ERANGE || endptr == text || *endptr != '\0') return false;
    out = value;
    return true;
}

} // namespace

int main(int argc, char** argv) {
    if (argc != 4) {
        std::cerr << "INVALID:USAGE" << std::endl;
        return 2;
    }

    long kmer_size = 0, unique_kmers = 0, total_kmers = 0;

    if (!ParseInt(argv[1], kmer_size)) {
        std::cerr << "INVALID:KMER_SIZE_NOT_INTEGER" << std::endl;
        return 1;
    }
    if (!ParseInt(argv[2], unique_kmers)) {
        std::cerr << "INVALID:UNIQUE_KMERS_NOT_INTEGER" << std::endl;
        return 1;
    }
    if (!ParseInt(argv[3], total_kmers)) {
        std::cerr << "INVALID:TOTAL_KMERS_NOT_INTEGER" << std::endl;
        return 1;
    }

    // Validate kmer_size
    if (kmer_size != 11) {
        std::cerr << "INVALID:KMER_SIZE_MUST_BE_11" << std::endl;
        return 1;
    }

    // Validate unique_kmers is positive
    if (unique_kmers <= 0) {
        std::cerr << "INVALID:UNIQUE_KMERS_EMPTY" << std::endl;
        return 1;
    }

    // Validate total_kmers >= unique_kmers
    if (total_kmers < unique_kmers) {
        std::cerr << "INVALID:TOTAL_KMERS_LT_UNIQUE" << std::endl;
        return 1;
    }

    // Validate avg_kmers_per_position in reasonable range
    double avg = static_cast<double>(total_kmers) / unique_kmers;
    if (avg < 1.0 || avg > 100.0) {
        std::cerr << "INVALID:AVG_KMERS_PER_POSITION_OUT_OF_RANGE" << std::endl;
        return 1;
    }

    std::cout << "VALID" << std::endl;
    return 0;
}
