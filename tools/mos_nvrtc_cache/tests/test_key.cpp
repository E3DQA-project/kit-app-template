#include "mos_nvrtc_cache/key.h"

#include <cassert>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <string>
#include <unistd.h>
#include <vector>

int main()
{
    assert(mos_nvrtc_cache::sha256_hex(std::vector<std::uint8_t>{'a', 'b', 'c'}) ==
           "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    const auto digestFile = std::filesystem::temp_directory_path() / ("mos-nvrtc-sha-" + std::to_string(getpid()));
    {
        std::ofstream output(digestFile, std::ios::binary);
        output << "abc";
    }
    assert(mos_nvrtc_cache::sha256_file(digestFile).value() ==
           "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    std::filesystem::remove(digestFile);

    mos_nvrtc_cache::ProgramDescription description{
        "extern \"C\" __global__ void generated() {}",
        "generated.cu",
        {{"common.cuh", "#define SCALE 1"}},
        {"--gpu-architecture=compute_90", "--std=c++17"},
        "renderer-sha256",
        "nvrtc-11.8",
        "compute_90",
    };

    const auto first = mos_nvrtc_cache::make_cache_key(description);
    assert(first.size() == 64);
    assert(first == mos_nvrtc_cache::make_cache_key(description));

    auto changed = description;
    changed.options.push_back("--use_fast_math");
    assert(first != mos_nvrtc_cache::make_cache_key(changed));

    changed = description;
    changed.headers[0].second = "#define SCALE 2";
    assert(first != mos_nvrtc_cache::make_cache_key(changed));
}
