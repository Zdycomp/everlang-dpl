CXX := g++
CXXFLAGS := -std=c++17 -Wall -Wextra -Werror -O2
ASAN_CXXFLAGS := -std=c++17 -Wall -Wextra -g -O0 -fsanitize=address,undefined

SRC_DIR := src
TEST_DIR := tests
BIN_DIR := bin

TARGET := $(BIN_DIR)/verify_particle
ASAN_TARGET := $(BIN_DIR)/verify_particle_asan
KMER_TARGET := $(BIN_DIR)/verify_kmer_index
KMER_ASAN_TARGET := $(BIN_DIR)/verify_kmer_index_asan
TEST_TARGET := $(TEST_DIR)/test_verify_particle

.PHONY: all asan test clean

all: $(TARGET) $(KMER_TARGET)

$(BIN_DIR):
	mkdir -p $(BIN_DIR)

$(TARGET): $(SRC_DIR)/verify_particle.cpp | $(BIN_DIR)
	$(CXX) $(CXXFLAGS) -o $@ $<

$(KMER_TARGET): $(SRC_DIR)/verify_kmer_index.cpp | $(BIN_DIR)
	$(CXX) $(CXXFLAGS) -o $@ $<

asan: $(ASAN_TARGET) $(KMER_ASAN_TARGET)

$(ASAN_TARGET): $(SRC_DIR)/verify_particle.cpp | $(BIN_DIR)
	$(CXX) $(ASAN_CXXFLAGS) -o $@ $<

$(KMER_ASAN_TARGET): $(SRC_DIR)/verify_kmer_index.cpp | $(BIN_DIR)
	$(CXX) $(ASAN_CXXFLAGS) -o $@ $<

$(TEST_TARGET): $(TEST_DIR)/test_verify_particle.cpp
	$(CXX) -std=c++17 -Wall -Wextra -O2 -o $@ $<

test: $(TARGET) $(TEST_TARGET)
	./$(TEST_TARGET)

clean:
	rm -f $(TARGET) $(ASAN_TARGET) $(KMER_TARGET) $(KMER_ASAN_TARGET) $(TEST_TARGET)
