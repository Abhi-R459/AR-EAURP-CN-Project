#ifndef AR_EAURP_CRYPTO_H
#define AR_EAURP_CRYPTO_H
#include <array>
#include <cstdint>
#include <vector>

namespace ns3::arEaurp
{
// Simulation-only provisioned X25519 keys. AES-GCM adds a 12-byte nonce and
// 16-byte tag to each UDP message. Distinct prefixes separate DATA and ACKs.
class CryptoBox
{
  public:
    using Key = std::array<uint8_t, 32>;
    static Key PublicKey(const Key& privateKey);
    static Key Agree(const Key& privateKey, const Key& publicKey);
    CryptoBox(const Key& key, uint32_t prefix) : m_key(key), m_prefix(prefix) {}
    std::vector<uint8_t> Seal(const std::vector<uint8_t>& clear, uint64_t sequence) const;
    bool Open(const std::vector<uint8_t>& wire, std::vector<uint8_t>& clear) const;
  private:
    Key m_key;
    uint32_t m_prefix;
};
}
#endif
