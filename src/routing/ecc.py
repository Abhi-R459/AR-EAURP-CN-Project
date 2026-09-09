"""ECC payload protection -- base.pdf 3.9.

The paper's construction is

    Encryption:  pick random r, C = M XOR (r * G)
    Decryption:  M = C XOR (r * P)     with P the receiver's public key

which is ElGamal-style elliptic-curve key agreement followed by an XOR with a
curve-point-derived keystream. We implement exactly that shape using real
elliptic-curve Diffie-Hellman (X25519) for the ``r * G`` / ``r * P`` agreement
and HKDF-SHA256 to stretch the agreed point into a keystream of the payload's
length.

Two engineering points worth stating at the review:

* The ECDH agreement is done **once per node pair and cached**, and only the
  keystream XOR runs per packet. That is how real protocols work, and it keeps
  the cost honest: the expensive asymmetric operation is amortised over a
  session rather than charged to every packet.
* base.pdf claims ECC adds security "without introducing any overhead". It is
  not free, so :func:`benchmark` measures it and the report quotes the number.

If ``cryptography`` is unavailable the module degrades to a clearly-labelled
hash-based stand-in so a simulation never fails for want of a crypto library.
"""

import hashlib
import os
import time

try:  # pragma: no cover - exercised by whichever environment runs this
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric.x25519 import (
        X25519PrivateKey,
    )
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    CRYPTO_AVAILABLE = True
except Exception:  # pragma: no cover
    CRYPTO_AVAILABLE = False

KEYSTREAM_INFO = b"EAURP-ECC-keystream"


def _hkdf(shared_secret, length, salt):
    if CRYPTO_AVAILABLE:
        return HKDF(
            algorithm=hashes.SHA256(),
            length=length,
            salt=salt,
            info=KEYSTREAM_INFO,
        ).derive(shared_secret)
    # Fallback: counter-mode SHA256. Labelled as such in `backend`.
    out = bytearray()
    counter = 0
    while len(out) < length:
        digest = hashlib.sha256(
            shared_secret + salt + KEYSTREAM_INFO + counter.to_bytes(4, "big")
        ).digest()
        out.extend(digest)
        counter += 1
    return bytes(out[:length])


class ECCKeyring(object):
    """Per-node ECC key pairs with cached pairwise shared secrets."""

    def __init__(self, n_nodes, enabled=True):
        self.n = int(n_nodes)
        self.enabled = bool(enabled)
        self.backend = "x25519" if CRYPTO_AVAILABLE else "sha256-fallback"

        self._private = {}
        self._public = {}
        self._shared = {}

        self.keygen_seconds = 0.0
        self.agreement_seconds = 0.0
        self.encrypt_seconds = 0.0
        self.encrypt_calls = 0
        self.agreements = 0

    # -- key management ----------------------------------------------------

    def _private_key(self, node_id):
        node_id = int(node_id)
        if node_id not in self._private:
            start = time.perf_counter()
            if CRYPTO_AVAILABLE:
                key = X25519PrivateKey.generate()
                self._private[node_id] = key
                self._public[node_id] = key.public_key()
            else:
                secret = os.urandom(32)
                self._private[node_id] = secret
                self._public[node_id] = hashlib.sha256(secret).digest()
            self.keygen_seconds += time.perf_counter() - start
        return self._private[node_id]

    def public_key_bytes(self, node_id):
        self._private_key(node_id)
        public = self._public[int(node_id)]
        if CRYPTO_AVAILABLE:
            return public.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
        return public

    def shared_secret(self, sender, receiver):
        """ECDH agreement between two nodes, computed once and cached."""
        key = (int(sender), int(receiver)) if sender <= receiver else (int(receiver), int(sender))
        if key in self._shared:
            return self._shared[key]

        start = time.perf_counter()
        private = self._private_key(key[0])
        self._private_key(key[1])
        if CRYPTO_AVAILABLE:
            secret = private.exchange(self._public[key[1]])
        else:
            secret = hashlib.sha256(private + self._public[key[1]]).digest()
        self.agreement_seconds += time.perf_counter() - start
        self.agreements += 1

        self._shared[key] = secret
        return secret

    # -- payload protection ------------------------------------------------

    def encrypt(self, sender, receiver, payload):
        """C = M XOR keystream(r * P). Returns the ciphertext."""
        if not self.enabled:
            return payload

        start = time.perf_counter()
        secret = self.shared_secret(sender, receiver)
        salt = os.urandom(8)
        keystream = _hkdf(secret, len(payload), salt)
        cipher = bytes(a ^ b for a, b in zip(payload, keystream))
        self.encrypt_seconds += time.perf_counter() - start
        self.encrypt_calls += 1
        return salt + cipher

    def decrypt(self, sender, receiver, blob):
        """M = C XOR keystream(r * G). Inverse of :meth:`encrypt`."""
        if not self.enabled:
            return blob
        salt, cipher = blob[:8], blob[8:]
        secret = self.shared_secret(sender, receiver)
        keystream = _hkdf(secret, len(cipher), salt)
        return bytes(a ^ b for a, b in zip(cipher, keystream))

    def cost_summary(self):
        """Numbers quoted in the overhead experiment (E6)."""
        per_packet = (
            self.encrypt_seconds / self.encrypt_calls if self.encrypt_calls else 0.0
        )
        per_agreement = (
            self.agreement_seconds / self.agreements if self.agreements else 0.0
        )
        return {
            "ecc_backend": self.backend,
            "ecc_keygen_seconds": self.keygen_seconds,
            "ecc_agreement_seconds": self.agreement_seconds,
            "ecc_agreements": self.agreements,
            "ecc_seconds_per_agreement": per_agreement,
            "ecc_encrypt_seconds": self.encrypt_seconds,
            "ecc_encrypt_calls": self.encrypt_calls,
            "ecc_seconds_per_packet": per_packet,
        }


def benchmark(n_pairs=32, payload_size=1024, repeats=200):
    """Standalone measurement of the real cost of the ECC layer."""
    keyring = ECCKeyring(max(2, n_pairs * 2), enabled=True)
    payload = os.urandom(int(payload_size))

    for index in range(int(n_pairs)):
        keyring.shared_secret(2 * index, 2 * index + 1)

    start = time.perf_counter()
    for index in range(int(repeats)):
        pair = index % max(1, int(n_pairs))
        keyring.encrypt(2 * pair, 2 * pair + 1, payload)
    elapsed = time.perf_counter() - start

    summary = keyring.cost_summary()
    summary["bench_payload_bytes"] = int(payload_size)
    summary["bench_repeats"] = int(repeats)
    summary["bench_total_seconds"] = elapsed
    summary["bench_seconds_per_packet"] = elapsed / max(1, int(repeats))
    return summary


def verify_roundtrip():
    """Sanity check used by the unit tests and by the notebook."""
    keyring = ECCKeyring(4, enabled=True)
    message = b"EAURP payload under test" * 8
    blob = keyring.encrypt(0, 1, message)
    return keyring.decrypt(0, 1, blob) == message
