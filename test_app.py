from io import BytesIO
import subprocess
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image, ImageChops

from main import app, DPI, SIZES


class LabelTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_preview_geometry_and_margins(self):
        for size, (width, length) in SIZES.items():
            response = self.client.post('/api/preview', json={'text': 'Storage\nCable adapters', 'size': size})
            self.assertEqual(response.status_code, 200)
            image = Image.open(BytesIO(response.content)).convert('L')
            self.assertEqual(image.size, (round(length * DPI / 25.4), round(width * DPI / 25.4)))
            bbox = ImageChops.invert(image).getbbox()
            self.assertIsNotNone(bbox)
            margin = round(4 * DPI / 25.4)
            self.assertGreaterEqual(bbox[0], margin)
            self.assertGreaterEqual(bbox[1], margin)
            self.assertLessEqual(bbox[2], image.width - margin)
            self.assertLessEqual(bbox[3], image.height - margin)

    @patch('main.command')
    def test_print_submits_pdf_with_correct_media_and_copies(self, command):
        command.side_effect = ['Brother_QL810W', 'request id is Brother_QL810W-42 (1 file(s))']
        response = self.client.post('/api/print', json={
            'text': 'USB cables', 'printer': 'Brother_QL810W', 'copies': 2, 'size': '62X1',
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['job_id'], 'Brother_QL810W-42')
        args, pdf = command.call_args.args
        self.assertEqual(args[:5], ['lp', '-d', 'Brother_QL810W', '-n', '2'])
        self.assertIn('PageSize=62X1', args)
        self.assertTrue(pdf.startswith(b'%PDF-'))
        # Check the actual encoded page size: width of roll by feed length.
        self.assertRegex(pdf, rb'/MediaBox\s*\[\s*0\s+0\s+175\.\d+\s+283\.\d+\s*\]')

    @patch('main.command')
    def test_black_red_roll_uses_two_planes_and_raw_submission(self, command):
        command.side_effect = ['Brother_QL810W', 'request id is Brother_QL810W-43 (1 file(s))']
        response = self.client.post('/api/print', json={'text': 'USB cables', 'printer': 'Brother_QL810W'})
        self.assertEqual(response.status_code, 200, response.text)
        args, raster = command.call_args.args
        self.assertIn('raw', args)
        self.assertIn(b'\x1b\x69\x4b\x09', raster)  # Two-color mode + cut at end.
        start = raster.index(b'\x77\x01\x5a')
        rows = round(100 * DPI / 25.4) - 70
        frame = raster[start:-1]
        self.assertEqual(len(frame), rows * 186)
        black = bytearray()
        for offset in range(0, len(frame), 186):
            self.assertEqual(frame[offset:offset+3], b'\x77\x01\x5a')
            black.extend(frame[offset+3:offset+93])
            self.assertEqual(frame[offset+93:offset+96], b'\x77\x02\x5a')
            self.assertEqual(frame[offset+96:offset+186], bytes(90))
        self.assertTrue(any(black))
        self.assertEqual(raster[-1:], b'\x1a')

    @patch('main.command', return_value='')
    def test_missing_printer_never_submits(self, command):
        response = self.client.post('/api/print', json={'text': 'Test', 'printer': 'missing'})
        self.assertEqual(response.status_code, 422)
        command.assert_called_once_with(['lpstat', '-e'])

    @patch('main.command')
    def test_invalid_inputs_never_reach_cups(self, command):
        for changes in [{'text': '   '}, {'size': 'A4'}, {'copies': 0}, {'copies': 21}, {'printer': '-dother'}, {'text': 'a\n' * 12}]:
            response = self.client.post('/api/print', json={'text': 'Label', 'printer': 'Brother', **changes})
            self.assertEqual(response.status_code, 422, changes)
        command.assert_not_called()

    @patch('main.command')
    def test_cross_site_print_is_rejected(self, command):
        response = self.client.post('/api/print', json={'text': 'Label', 'printer': 'Brother'}, headers={'Origin': 'https://example.org'})
        self.assertEqual(response.status_code, 403)
        command.assert_not_called()

    @patch('main.subprocess.run')
    def test_cups_failure_is_reported(self, run):
        run.return_value = subprocess.CompletedProcess(['lpstat'], 1, b'', b'Cannot connect to CUPS')
        response = self.client.get('/api/printers')
        self.assertEqual(response.status_code, 503)
        self.assertIn('Cannot connect', response.json()['detail'])


if __name__ == '__main__':
    unittest.main()
