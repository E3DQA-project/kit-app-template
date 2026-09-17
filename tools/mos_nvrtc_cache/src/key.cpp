#include "mos_nvrtc_cache/key.h"

#include <array>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <vector>

namespace mos_nvrtc_cache {
namespace {

constexpr std::array<std::uint32_t, 64> kRoundConstants = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
};

std::uint32_t rotateRight(std::uint32_t value, unsigned int count)
{
    return (value >> count) | (value << (32U - count));
}

class Sha256
{
public:
    void update(const std::uint8_t* data, std::size_t size)
    {
        totalBytes_ += size;
        while (size > 0)
        {
            const auto available = block_.size() - blockSize_;
            const auto take = size < available ? size : available;
            for (std::size_t index = 0; index < take; ++index)
                block_[blockSize_ + index] = data[index];
            blockSize_ += take;
            data += take;
            size -= take;
            if (blockSize_ == block_.size())
            {
                processBlock();
                blockSize_ = 0;
            }
        }
    }

    std::array<std::uint8_t, 32> finish()
    {
        const auto bitLength = static_cast<std::uint64_t>(totalBytes_) * 8U;
        const std::uint8_t one = 0x80;
        update(&one, 1);
        const std::uint8_t zero = 0;
        while (blockSize_ != 56)
            update(&zero, 1);
        std::array<std::uint8_t, 8> lengthBytes{};
        for (std::size_t index = 0; index < lengthBytes.size(); ++index)
            lengthBytes[index] = static_cast<std::uint8_t>(bitLength >> ((lengthBytes.size() - 1 - index) * 8));
        update(lengthBytes.data(), lengthBytes.size());

        std::array<std::uint8_t, 32> digest{};
        for (std::size_t index = 0; index < state_.size(); ++index)
            for (std::size_t byte = 0; byte < 4; ++byte)
                digest[index * 4 + byte] = static_cast<std::uint8_t>(state_[index] >> ((3 - byte) * 8));
        return digest;
    }

private:
    void processBlock()
    {
        std::array<std::uint32_t, 64> words{};
        for (std::size_t index = 0; index < 16; ++index)
        {
            words[index] = (static_cast<std::uint32_t>(block_[index * 4]) << 24) |
                           (static_cast<std::uint32_t>(block_[index * 4 + 1]) << 16) |
                           (static_cast<std::uint32_t>(block_[index * 4 + 2]) << 8) |
                           static_cast<std::uint32_t>(block_[index * 4 + 3]);
        }
        for (std::size_t index = 16; index < words.size(); ++index)
        {
            const auto sigma0 = rotateRight(words[index - 15], 7) ^ rotateRight(words[index - 15], 18) ^ (words[index - 15] >> 3);
            const auto sigma1 = rotateRight(words[index - 2], 17) ^ rotateRight(words[index - 2], 19) ^ (words[index - 2] >> 10);
            words[index] = words[index - 16] + sigma0 + words[index - 7] + sigma1;
        }

        auto a = state_[0]; auto b = state_[1]; auto c = state_[2]; auto d = state_[3];
        auto e = state_[4]; auto f = state_[5]; auto g = state_[6]; auto h = state_[7];
        for (std::size_t index = 0; index < words.size(); ++index)
        {
            const auto sigma1 = rotateRight(e, 6) ^ rotateRight(e, 11) ^ rotateRight(e, 25);
            const auto choose = (e & f) ^ (~e & g);
            const auto temporary1 = h + sigma1 + choose + kRoundConstants[index] + words[index];
            const auto sigma0 = rotateRight(a, 2) ^ rotateRight(a, 13) ^ rotateRight(a, 22);
            const auto majority = (a & b) ^ (a & c) ^ (b & c);
            const auto temporary2 = sigma0 + majority;
            h = g; g = f; f = e; e = d + temporary1; d = c; c = b; b = a; a = temporary1 + temporary2;
        }
        state_[0] += a; state_[1] += b; state_[2] += c; state_[3] += d;
        state_[4] += e; state_[5] += f; state_[6] += g; state_[7] += h;
    }

    std::array<std::uint32_t, 8> state_ = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
    std::array<std::uint8_t, 64> block_{};
    std::size_t blockSize_ = 0;
    std::size_t totalBytes_ = 0;
};

void appendUint64(std::vector<std::uint8_t>& bytes, std::uint64_t value)
{
    for (unsigned int shift = 56; shift > 0; shift -= 8)
        bytes.push_back(static_cast<std::uint8_t>(value >> shift));
    bytes.push_back(static_cast<std::uint8_t>(value));
}

void appendString(std::vector<std::uint8_t>& bytes, const std::string& value)
{
    appendUint64(bytes, value.size());
    bytes.insert(bytes.end(), value.begin(), value.end());
}

void appendStringList(std::vector<std::uint8_t>& bytes, const std::vector<std::string>& values)
{
    appendUint64(bytes, values.size());
    for (const auto& value : values)
        appendString(bytes, value);
}

std::string hexDigest(const std::array<std::uint8_t, 32>& digest)
{
    std::ostringstream output;
    output << std::hex << std::setfill('0');
    for (const auto byte : digest)
        output << std::setw(2) << static_cast<unsigned int>(byte);
    return output.str();
}

} // namespace

std::string sha256_hex(const std::vector<std::uint8_t>& bytes)
{
    Sha256 hash;
    hash.update(bytes.data(), bytes.size());
    return hexDigest(hash.finish());
}

std::optional<std::string> sha256_file(const std::filesystem::path& path)
{
    std::ifstream input(path, std::ios::binary);
    if (!input)
        return std::nullopt;

    Sha256 hash;
    std::array<std::uint8_t, 64 * 1024> buffer{};
    while (input.read(reinterpret_cast<char*>(buffer.data()), static_cast<std::streamsize>(buffer.size())) || input.gcount() > 0)
        hash.update(buffer.data(), static_cast<std::size_t>(input.gcount()));
    if (!input.eof())
        return std::nullopt;
    return hexDigest(hash.finish());
}

std::string make_cache_key(const ProgramDescription& description)
{
    std::vector<std::uint8_t> bytes;
    appendString(bytes, description.source);
    appendString(bytes, description.name);
    appendUint64(bytes, description.headers.size());
    for (const auto& [name, source] : description.headers)
    {
        appendString(bytes, name);
        appendString(bytes, source);
    }
    appendStringList(bytes, description.options);
    appendString(bytes, description.renderer_sha256);
    appendString(bytes, description.nvrtc_version);
    appendString(bytes, description.target_architecture);

    return sha256_hex(bytes);
}

} // namespace mos_nvrtc_cache
