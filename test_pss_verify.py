"""RSA-PSS (PS256) verification, checked against signatures made by the `cryptography`
package. The verifier rejected every valid signature until 2026-10-16 (it checked the
leading bits the wrong way round), and the test that should have caught it accepted
either outcome. Valid signatures MUST verify; every kind of wrong one MUST NOT."""
import sys
import unittest

sys.path.insert(0, "/tmp/pycrypto")
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

import relayshield_tap_verifier as tap

PSS = padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32)


def sign(key, msg, salt=32):
    return key.sign(msg, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=salt),
                    hashes.SHA256())


class Pss(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 2048 is the real case. 2049 and 2055 make emBits a multiple of 8 or leave one
        # spare bit, which are the lengths where the leading-bit handling differs.
        cls.keys = [rsa.generate_private_key(public_exponent=65537, key_size=b)
                    for b in (2048, 2049, 2055, 3072)]

    def test_many_valid_signatures_verify_on_every_modulus_size(self):
        for key in self.keys:
            nums = key.public_key().public_numbers()
            for i in range(25):
                msg = f"message {i}".encode()
                self.assertTrue(tap._pss_verify(nums.n, nums.e, sign(key, msg), msg),
                                f"{nums.n.bit_length()}-bit key, message {i}")

    def test_wrong_message_wrong_key_and_flipped_bits_fail(self):
        k, other = self.keys[0], self.keys[3]
        nums = k.public_key().public_numbers()
        sig = sign(k, b"right")
        self.assertFalse(tap._pss_verify(nums.n, nums.e, sig, b"wrong"))
        on = other.public_key().public_numbers()
        self.assertFalse(tap._pss_verify(on.n, on.e, sig, b"right"))
        for pos in (0, 1, len(sig) // 2, len(sig) - 1):
            bad = bytearray(sig)
            bad[pos] ^= 0x01
            self.assertFalse(tap._pss_verify(nums.n, nums.e, bytes(bad), b"right"), pos)

    def test_a_different_salt_length_is_not_accepted_as_PS256(self):
        k = self.keys[0]
        nums = k.public_key().public_numbers()
        self.assertFalse(tap._pss_verify(nums.n, nums.e, sign(k, b"m", salt=20), b"m"))

    def test_bad_lengths_and_out_of_range_signatures_fail_without_raising(self):
        nums = self.keys[0].public_key().public_numbers()
        for sig in (b"", b"\\x00" * 10, b"\\xff" * 256, b"\\x00" * 256, b"\\xff" * 257):
            self.assertFalse(tap._pss_verify(nums.n, nums.e, sig, b"m"))


if __name__ == "__main__":
    unittest.main()
