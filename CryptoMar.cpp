// Библиотека на C++ для максимально еффективной генерации ключей и адресов на MacM1

#include <pybind11/pybind11.h>
#include <openssl/rand.h>
#include <openssl/sha.h>
#include <openssl/ec.h>
#include <openssl/obj_mac.h>
#include <string>
#include <vector>
#include <sstream>
#include <iomanip>

namespace py = pybind11;
using namespace std;

std::string get_priv_key() {
    vector<unsigned char> priv_key(32);
    RAND_bytes(priv_key.data(), 32);
    string hex_key;
    for (unsigned char byte : priv_key) {
        hex_key += "0123456789abcdef"[byte >> 4];
        hex_key += "0123456789abcdef"[byte & 0xF];
    }
    return hex_key;
}

std::vector<unsigned char> double_sha256(const std::vector<unsigned char>& data) {
    unsigned char hash1[SHA256_DIGEST_LENGTH];
    SHA256(data.data(), data.size(), hash1);

    unsigned char hash2[SHA256_DIGEST_LENGTH];
    SHA256(hash1, SHA256_DIGEST_LENGTH, hash2);

    return std::vector<unsigned char>(hash2, hash2 + SHA256_DIGEST_LENGTH);
}

const char* BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";

std::string base58_encode(const std::vector<unsigned char>& data) {
    vector<unsigned char> temp(data);
    string result;

    int zero_count = 0;
    for (unsigned char byte : temp) {
        if (byte == 0x00) {
            zero_count++;
        } else {
            break;
        }
    }

    std::vector<unsigned char> b58;
    for (unsigned char byte : temp) {
        unsigned int carry = static_cast<unsigned int>(byte);
        for (size_t i = 0; i < b58.size(); ++i) {
            carry += (static_cast<unsigned int>(b58[i]) << 8);
            b58[i] = static_cast<unsigned char>(carry % 58);
            carry /= 58;
        }

        while (carry > 0) {
            b58.push_back(static_cast<unsigned char>(carry % 58));
            carry /= 58;
        }
    }

    for (auto it = b58.rbegin(); it != b58.rend(); ++it) {
        result += BASE58_ALPHABET[*it];
    }

    for (int i = 0; i < zero_count; i++) {
        result = "1" + result;
    }

    return result;
}

std::pair<std::string, std::string> get_wif(std::string priv_key_hex = "", bool compressed = true, bool mainnet = true) {
    if (priv_key_hex.empty()) {
        priv_key_hex = get_priv_key();
    }

    std::vector<unsigned char> priv_key_bytes;
    for (size_t i = 0; i < priv_key_hex.length(); i += 2) {
        std::string byte_string = priv_key_hex.substr(i, 2);
        unsigned char byte = static_cast<unsigned char>(strtol(byte_string.c_str(), nullptr, 16));
        priv_key_bytes.push_back(byte);
    }

    std::vector<unsigned char> extended_key;
    extended_key.push_back(mainnet ? 0x80 : 0xEF);

    extended_key.insert(extended_key.end(), priv_key_bytes.begin(), priv_key_bytes.end());

    if (compressed) {
        extended_key.push_back(0x01);
    }

    std::vector<unsigned char> checksum_full = double_sha256(extended_key);
    std::vector<unsigned char> checksum(checksum_full.begin(), checksum_full.begin() + 4);

    extended_key.insert(extended_key.end(), checksum.begin(), checksum.end());

    std::string wif = base58_encode(extended_key);

    return std::make_pair(wif, priv_key_hex);
}

std::vector<unsigned char> ripemd160(const std::vector<unsigned char>& data) {
    unsigned char hash[20];
    EVP_MD_CTX* ctx = EVP_MD_CTX_new();
    EVP_DigestInit_ex(ctx, EVP_ripemd160(), nullptr);
    EVP_DigestUpdate(ctx, data.data(), data.size());
    EVP_DigestFinal_ex(ctx, hash, nullptr);
    EVP_MD_CTX_free(ctx);
    return std::vector<unsigned char>(hash, hash + 20);
}

std::vector<unsigned char> convert_bits(const std::vector<unsigned char>& data, int from_bits, int to_bits) {
    int acc = 0;
    int bits = 0;
    std::vector<unsigned char> ret;
    int maxv = (1 << to_bits) - 1;
    for (auto value : data) {
        acc = (acc << from_bits) | value;
        bits += from_bits;
        while (bits >= to_bits) {
            bits -= to_bits;
            ret.push_back((acc >> bits) & maxv);
        }
    }
    if (bits > 0) {
        ret.push_back((acc << (to_bits - bits)) & maxv);
    }
    return ret;
}

std::vector<unsigned char> bech32_create_checksum(const std::string& hrp, const std::vector<unsigned char>& data) {
    std::vector<unsigned char> values;
    for (auto c : hrp) {
        values.push_back(c >> 5);
    }
    values.push_back(0);
    for (auto c : hrp) {
        values.push_back(c & 31);
    }
    values.insert(values.end(), data.begin(), data.end());
    values.insert(values.end(), {0, 0, 0, 0, 0, 0});

    uint32_t polymod = 1;
    const uint32_t GENERATOR[] = {0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3};
    for (auto v : values) {
        uint8_t top = polymod >> 25;
        polymod = ((polymod & 0x1ffffff) << 5) ^ v;
        for (int i = 0; i < 5; ++i) {
            if ((top >> i) & 1) {
                polymod ^= GENERATOR[i];
            }
        }
    }
    polymod ^= 1;
    std::vector<unsigned char> checksum(6);
    for (int i = 0; i < 6; ++i) {
        checksum[i] = (polymod >> (5 * (5 - i))) & 31;
    }
    return checksum;
}

std::string generate_bech32_address(const std::string& priv_key_hex) {
    if (priv_key_hex.empty()) {
        throw std::runtime_error("Private key must be provided to generate Bech32 address.");
    }

    std::vector<unsigned char> priv_key_bytes;
    for (size_t i = 0; i < priv_key_hex.length(); i += 2) {
        priv_key_bytes.push_back(static_cast<unsigned char>(strtol(priv_key_hex.substr(i, 2).c_str(), nullptr, 16)));
    }

    EC_KEY* ec_key = EC_KEY_new_by_curve_name(NID_secp256k1);
    BIGNUM* priv_bn = BN_bin2bn(priv_key_bytes.data(), priv_key_bytes.size(), NULL);
    EC_KEY_set_private_key(ec_key, priv_bn);

    const EC_GROUP* group = EC_KEY_get0_group(ec_key);
    EC_POINT* pub_key_point = EC_POINT_new(group);
    EC_POINT_mul(group, pub_key_point, priv_bn, NULL, NULL, NULL);

    unsigned char pub_key[33];
    size_t pub_key_len = EC_POINT_point2oct(group, pub_key_point, POINT_CONVERSION_COMPRESSED, pub_key, sizeof(pub_key), NULL);

    std::vector<unsigned char> sha256_hash(SHA256_DIGEST_LENGTH);
    SHA256(pub_key, pub_key_len, sha256_hash.data());
    std::vector<unsigned char> hash160 = ripemd160(sha256_hash);

    std::vector<unsigned char> witness_program = hash160; 

    auto converted = convert_bits(witness_program, 8, 5);
  
    converted.insert(converted.begin(), 0x00); 

    std::string hrp = "bc";
    std::vector<unsigned char> checksum = bech32_create_checksum(hrp, converted);
    converted.insert(converted.end(), checksum.begin(), checksum.end());

    const std::string CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l";
    std::string address = hrp + "1";
    for (auto val : converted) {
        address += CHARSET[val];
    }

    EC_KEY_free(ec_key);
    EC_POINT_free(pub_key_point);
    BN_free(priv_bn);

    return address;

}

PYBIND11_MODULE(CryptoMar, m) {
    m.def("get_priv_key", &get_priv_key, "Generate a random 32-byte private key");
    m.def("get_wif", [](std::string priv_key_hex = "", bool compressed = true, bool mainnet = true) {
        auto result = get_wif(priv_key_hex, compressed, mainnet);
        return py::make_tuple(result.first, result.second);
    }, "Generate WIF from private key, or generate a new one",
    py::arg("priv_key_hex") = "", py::arg("compressed") = true, py::arg("mainnet") = true);
    m.def("get_bech32", &generate_bech32_address, "Generate Bech32 address from private key");
}
