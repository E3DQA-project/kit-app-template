#pragma once

#include <cstdint>
#include <filesystem>
#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace mos_nvrtc_cache {

struct ProgramDescription
{
    std::string source;
    std::string name;
    std::vector<std::pair<std::string, std::string>> headers;
    std::vector<std::string> options;
    std::string renderer_sha256;
    std::string nvrtc_version;
    std::string target_architecture;
};

std::string make_cache_key(const ProgramDescription& description);
std::string sha256_hex(const std::vector<std::uint8_t>& bytes);
std::optional<std::string> sha256_file(const std::filesystem::path& path);

} // namespace mos_nvrtc_cache
