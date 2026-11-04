import base64
import hashlib
import os
import unittest
from urllib.parse import urlparse

# Set test environment before importing server.app
os.environ["HLS_SEGMENT_SIGNING_SECRET"] = "test_signing_secret_12345"
os.environ["HLS_SEGMENT_TTL_SECONDS"] = "21600"
os.environ["HLS_PROXY_ALLOWED_HOSTS"] = "ydc1wes.me,vsyshost.com,watchkar.com,mishai.ydc1wes.me"

from fastapi import HTTPException
from server.app import _signed_segment_url, _evaluate_upstream_expiry, _segment_is_allowed


class TestHLSSegmentSigning(unittest.TestCase):
    def setUp(self):
        self.secret = "test_signing_secret_12345"
        self.now = 1793730000  # fixed reference timestamp

    def test_01_both_s_and_e_valid(self):
        """1. Both s and e present and valid -> sets expiry to s + e."""
        s = 1793730000
        e = 7200  # 2 hours
        url = f"https://mishai.ydc1wes.me/hls/seg-1.ts?t=token123&s={s}&e={e}&sp=0"
        signed = _signed_segment_url(url, now=self.now)
        
        parts = signed.split("/")
        token, expires = parts[2], parts[3]
        self.assertEqual(int(expires), s + e)
        self.assertLessEqual(int(expires), s + e)

    def test_02_upstream_expiry_earlier_than_configured_ttl(self):
        """2. Upstream expiry earlier than configured TTL -> capped at upstream expiry."""
        s = self.now - 1000
        e = 3600  # upstream expires in 2600s (< 21600s TTL)
        url = f"https://mishai.ydc1wes.me/hls/seg-2.ts?t=abc&s={s}&e={e}"
        signed = _signed_segment_url(url, now=self.now)
        expires = int(signed.split("/")[3])
        self.assertEqual(expires, s + e)
        self.assertEqual(expires, self.now + 2600)
        self.assertLess(expires, self.now + 21600)

    def test_03_upstream_expiry_later_than_configured_ttl(self):
        """3. Upstream expiry later than configured TTL -> capped at local TTL."""
        s = self.now
        e = 86400  # 24 hours (> 21600s TTL)
        url = f"https://mishai.ydc1wes.me/hls/seg-3.ts?t=abc&s={s}&e={e}"
        signed = _signed_segment_url(url, now=self.now)
        expires = int(signed.split("/")[3])
        self.assertEqual(expires, self.now + 21600)
        self.assertLess(expires, s + e)

    def test_04_already_expired_upstream_authorization(self):
        """4. Upstream expiry already in past -> raises controlled HTTP 410."""
        s = self.now - 10000
        e = 3600  # expired: s + e = now - 6400
        url = f"https://mishai.ydc1wes.me/hls/seg-4.ts?t=abc&s={s}&e={e}"
        with self.assertRaises(HTTPException) as ctx:
            _signed_segment_url(url, now=self.now)
        self.assertEqual(ctx.exception.status_code, 410)
        self.assertIn("expired", ctx.exception.detail.lower())

    def test_05_both_s_and_e_absent(self):
        """5. Both s and e absent -> uses configured fallback TTL."""
        url = "https://mishai.ydc1wes.me/hls/seg-5.ts?t=xyz"
        status, exp, err = _evaluate_upstream_expiry("t=xyz", self.now)
        self.assertEqual(status, "absent")
        self.assertIsNone(exp)
        
        signed = _signed_segment_url(url, now=self.now)
        expires = int(signed.split("/")[3])
        self.assertEqual(expires, self.now + 21600)

    def test_06_partial_parameters_fail_closed(self):
        """6. Only one parameter present (partial) -> FAIL CLOSED with HTTP 403."""
        # s present, e absent
        status, exp, err = _evaluate_upstream_expiry("s=1793730000", self.now)
        self.assertEqual(status, "partial")
        self.assertIn("missing required parameter 'e'", err)
        with self.assertRaises(HTTPException) as ctx:
            _signed_segment_url("https://mishai.ydc1wes.me/hls/seg-6.ts?s=1793730000", now=self.now)
        self.assertEqual(ctx.exception.status_code, 403)

        # e present, s absent
        status, exp, err = _evaluate_upstream_expiry("e=21600", self.now)
        self.assertEqual(status, "partial")
        self.assertIn("missing required parameter 's'", err)
        with self.assertRaises(HTTPException) as ctx:
            _signed_segment_url("https://mishai.ydc1wes.me/hls/seg-6.ts?e=21600", now=self.now)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_07_duplicated_parameters_fail_closed(self):
        """7. Duplicated s or e parameters -> FAIL CLOSED with HTTP 403."""
        # Duplicated s
        status, exp, err = _evaluate_upstream_expiry("s=1793730000&s=1793730500&e=21600", self.now)
        self.assertEqual(status, "duplicated")
        with self.assertRaises(HTTPException) as ctx:
            _signed_segment_url("https://mishai.ydc1wes.me/hls/seg-7.ts?s=1793730000&s=1793730500&e=21600", now=self.now)
        self.assertEqual(ctx.exception.status_code, 403)

        # Duplicated e
        status, exp, err = _evaluate_upstream_expiry("s=1793730000&e=21600&e=10800", self.now)
        self.assertEqual(status, "duplicated")
        with self.assertRaises(HTTPException) as ctx:
            _signed_segment_url("https://mishai.ydc1wes.me/hls/seg-7.ts?s=1793730000&e=21600&e=10800", now=self.now)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_08_malformed_values_fail_closed(self):
        """8. Malformed or out-of-range values -> FAIL CLOSED with HTTP 403."""
        # Non-integer s
        status, exp, err = _evaluate_upstream_expiry("s=abc&e=21600", self.now)
        self.assertEqual(status, "malformed")
        with self.assertRaises(HTTPException) as ctx:
            _signed_segment_url("https://mishai.ydc1wes.me/hls/seg-8.ts?s=abc&e=21600", now=self.now)
        self.assertEqual(ctx.exception.status_code, 403)

        # Non-integer e
        status, exp, err = _evaluate_upstream_expiry("s=1793730000&e=xyz", self.now)
        self.assertEqual(status, "malformed")
        with self.assertRaises(HTTPException) as ctx:
            _signed_segment_url("https://mishai.ydc1wes.me/hls/seg-8.ts?s=1793730000&e=xyz", now=self.now)
        self.assertEqual(ctx.exception.status_code, 403)

        # Negative e
        status, exp, err = _evaluate_upstream_expiry("s=1793730000&e=-100", self.now)
        self.assertEqual(status, "malformed")
        with self.assertRaises(HTTPException) as ctx:
            _signed_segment_url("https://mishai.ydc1wes.me/hls/seg-8.ts?s=1793730000&e=-100", now=self.now)
        self.assertEqual(ctx.exception.status_code, 403)

        # Non-epoch s (out of range, e.g. sequence number s=12)
        status, exp, err = _evaluate_upstream_expiry("s=12&e=21600", self.now)
        self.assertEqual(status, "malformed")
        with self.assertRaises(HTTPException) as ctx:
            _signed_segment_url("https://mishai.ydc1wes.me/hls/seg-8.ts?s=12&e=21600", now=self.now)
        self.assertEqual(ctx.exception.status_code, 403)

        # Out-of-range duration e (> 86400)
        status, exp, err = _evaluate_upstream_expiry("s=1793730000&e=999999", self.now)
        self.assertEqual(status, "malformed")
        with self.assertRaises(HTTPException) as ctx:
            _signed_segment_url("https://mishai.ydc1wes.me/hls/seg-8.ts?s=1793730000&e=999999", now=self.now)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_09_tampered_signature(self):
        """9. Tampered signature -> fails Nginx-compatible MD5 verification."""
        url = "https://mishai.ydc1wes.me/hls/seg-9.ts?t=abc&s=1793730000&e=21600"
        signed = _signed_segment_url(url, now=self.now)
        parts = signed.split("/")
        token, expires = parts[2], parts[3]
        raw_path = "/".join(parts[4:])

        expected_digest = hashlib.md5(f"{expires}{raw_path} {self.secret}".encode('utf-8')).digest()
        expected_token = base64.urlsafe_b64encode(expected_digest).decode('ascii').rstrip('=')
        self.assertEqual(token, expected_token)

        tampered_raw_path = raw_path + "&tampered=1"
        tampered_digest = hashlib.md5(f"{expires}{tampered_raw_path} {self.secret}".encode('utf-8')).digest()
        tampered_token = base64.urlsafe_b64encode(tampered_digest).decode('ascii').rstrip('=')
        self.assertNotEqual(token, tampered_token)

    def test_10_query_string_integrity(self):
        """10. Query-string integrity -> query is preserved in full."""
        upstream_query = "t=QsnSH0MblhHyvAvE4YW2k7qIT90BVTMjNfKEidI0Sc8&s=1793736376&e=21600&f=55742&i=0.0&sp=0"
        url = f"https://mishai.ydc1wes.me/hls2/01/00011/y4rxawofp00b_h/seg-415-v1-a1.ts?{upstream_query}"
        signed = _signed_segment_url(url, now=self.now)
        
        parsed_signed = urlparse(signed)
        self.assertEqual(parsed_signed.query, upstream_query)
        self.assertIn("mishai.ydc1wes.me", parsed_signed.path)

    def test_11_invalid_host_rejection(self):
        """11. Invalid host rejection -> raises HTTP 502 for unallowed host."""
        bad_url = "https://evil-attacker.com/hls/seg-1.ts?t=abc"
        with self.assertRaises(HTTPException) as ctx:
            _signed_segment_url(bad_url, now=self.now)
        self.assertEqual(ctx.exception.status_code, 502)
        self.assertIn("not allow-listed", ctx.exception.detail)

    def test_12_nginx_compatibility_formula(self):
        """12. Nginx secure_link formula matching."""
        target_host = "mishai.ydc1wes.me"
        target_path = "hls2/01/00011/y4rxawofp00b_h/seg-1.ts"
        args = "t=token&s=1793730000&e=21600"
        url = f"https://{target_host}/{target_path}?{args}"

        signed = _signed_segment_url(url, now=self.now)
        parts = signed.split("/")
        token, expires = parts[2], parts[3]

        nginx_md5_input = f"{expires}{target_host}/{target_path}?{args} {self.secret}"
        nginx_digest = hashlib.md5(nginx_md5_input.encode('utf-8')).digest()
        nginx_token = base64.urlsafe_b64encode(nginx_digest).decode('ascii').rstrip('=')

        self.assertEqual(token, nginx_token)


if __name__ == "__main__":
    unittest.main()
