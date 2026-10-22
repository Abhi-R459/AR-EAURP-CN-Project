#include "ar-eaurp-crypto.h"
#include <openssl/evp.h>
#include <openssl/kdf.h>
#include <memory>
#include <stdexcept>

namespace ns3::arEaurp
{
namespace
{
using Pkey = std::unique_ptr<EVP_PKEY, decltype(&EVP_PKEY_free)>;
using Pctx = std::unique_ptr<EVP_PKEY_CTX, decltype(&EVP_PKEY_CTX_free)>;
using Cctx = std::unique_ptr<EVP_CIPHER_CTX, decltype(&EVP_CIPHER_CTX_free)>;
void Require(bool ok) { if (!ok) throw std::runtime_error("OpenSSL crypto operation failed"); }
Pkey Private(const CryptoBox::Key& key)
{
    Pkey result(EVP_PKEY_new_raw_private_key(EVP_PKEY_X25519, nullptr, key.data(), key.size()), EVP_PKEY_free);
    Require(bool(result));
    return result;
}
}

CryptoBox::Key CryptoBox::PublicKey(const Key& privateKey)
{
    auto key = Private(privateKey);
    Key result{};
    size_t length = result.size();
    Require(EVP_PKEY_get_raw_public_key(key.get(), result.data(), &length) == 1);
    return result;
}

CryptoBox::Key CryptoBox::Agree(const Key& privateKey, const Key& publicKey)
{
    auto local = Private(privateKey);
    Pkey peer(EVP_PKEY_new_raw_public_key(EVP_PKEY_X25519, nullptr, publicKey.data(), publicKey.size()), EVP_PKEY_free);
    Pctx ctx(EVP_PKEY_CTX_new(local.get(), nullptr), EVP_PKEY_CTX_free);
    Require(bool(peer) && bool(ctx));
    Key shared{}, result{};
    size_t length = shared.size();
    Require(EVP_PKEY_derive_init(ctx.get()) == 1 && EVP_PKEY_derive_set_peer(ctx.get(), peer.get()) == 1);
    Require(EVP_PKEY_derive(ctx.get(), shared.data(), &length) == 1);
    Pctx hkdf(EVP_PKEY_CTX_new_id(EVP_PKEY_HKDF, nullptr), EVP_PKEY_CTX_free);
    static const uint8_t info[] = "AR-EAURP simulation payload";
    Require(bool(hkdf) && EVP_PKEY_derive_init(hkdf.get()) == 1);
    Require(EVP_PKEY_CTX_set_hkdf_md(hkdf.get(), EVP_sha256()) == 1 &&
            EVP_PKEY_CTX_set1_hkdf_key(hkdf.get(), shared.data(), shared.size()) == 1 &&
            EVP_PKEY_CTX_add1_hkdf_info(hkdf.get(), info, sizeof(info) - 1) == 1);
    length = result.size();
    Require(EVP_PKEY_derive(hkdf.get(), result.data(), &length) == 1);
    return result;
}

std::vector<uint8_t> CryptoBox::Seal(const std::vector<uint8_t>& clear, uint64_t sequence) const
{
    std::vector<uint8_t> wire(clear.size() + 28);
    for (uint32_t i = 0; i < 4; ++i) wire[i] = m_prefix >> (24 - 8 * i);
    for (uint32_t i = 0; i < 8; ++i) wire[4 + i] = sequence >> (56 - 8 * i);
    Cctx ctx(EVP_CIPHER_CTX_new(), EVP_CIPHER_CTX_free);
    Require(bool(ctx) && EVP_EncryptInit_ex(ctx.get(), EVP_aes_256_gcm(), nullptr, m_key.data(), wire.data()) == 1);
    int written = 0, final = 0;
    Require(EVP_EncryptUpdate(ctx.get(), wire.data() + 12, &written, clear.data(), clear.size()) == 1);
    Require(EVP_EncryptFinal_ex(ctx.get(), wire.data() + 12 + written, &final) == 1);
    Require(EVP_CIPHER_CTX_ctrl(ctx.get(), EVP_CTRL_GCM_GET_TAG, 16, wire.data() + wire.size() - 16) == 1);
    return wire;
}

bool CryptoBox::Open(const std::vector<uint8_t>& wire, std::vector<uint8_t>& clear) const
{
    clear.clear();
    if (wire.size() < 28) return false;
    Cctx ctx(EVP_CIPHER_CTX_new(), EVP_CIPHER_CTX_free);
    Require(bool(ctx) && EVP_DecryptInit_ex(ctx.get(), EVP_aes_256_gcm(), nullptr, m_key.data(), wire.data()) == 1);
    const size_t size = wire.size() - 28;
    // One extra byte keeps the empty-payload finalisation pointer valid.
    std::vector<uint8_t> decoded(size + 1);
    int written = 0, final = 0;
    Require(EVP_DecryptUpdate(ctx.get(), decoded.data(), &written, wire.data() + 12, size) == 1);
    Require(EVP_CIPHER_CTX_ctrl(ctx.get(), EVP_CTRL_GCM_SET_TAG, 16, const_cast<uint8_t*>(wire.data() + wire.size() - 16)) == 1);
    if (EVP_DecryptFinal_ex(ctx.get(), decoded.data() + written, &final) != 1) return false;
    decoded.resize(size);
    clear = std::move(decoded);
    return true;
}
}
