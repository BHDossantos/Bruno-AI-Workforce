"""Synthetic parser tests. No database, credentials or dispatch path."""

import csv
import unittest

from app.csv_upload import csv_rows


class CsvUploadTest(unittest.TestCase):
    def test_keeps_linkedin_preamble_and_quoted_multiline_columns(self):
        rows = csv_rows('Notes:\r\nExport checklist\r\nFirst Name,Email,Company\r\nSample,person@example.test,"Line one\r\nLine two, LLC"\r\n')
        self.assertEqual(rows, [{"First Name": "Sample", "Email": "person@example.test", "Company": "Line one\r\nLine two, LLC"}])

    def test_rejects_overflow_and_malformed_quotes(self):
        with self.assertRaisesRegex(csv.Error, "line 2 has extra columns"):
            csv_rows("email,company\ncontact@example.test,Unquoted, Inc\n")
        with self.assertRaises(csv.Error):
            csv_rows('email,company\ncontact@example.test,"Unclosed\n')

    def test_rejects_duplicate_columns_and_accepts_header_only(self):
        with self.assertRaisesRegex(csv.Error, "duplicate column names"):
            csv_rows("Email,email\na@example.test,b@example.test\n")
        self.assertEqual(csv_rows("email,name\n"), [])
