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

    @patch('main.command')
    def test_queue_lists_active_jobs_for_selected_printer(self, command):
        command.side_effect = [
            'printer Brother_QL810W now printing Brother_QL810W-21.\n\tSending data to printer.',
            'Brother_QL810W-21 clee 207872 Wed Sep 23 08:12:43 2026\n'
            'Brother_QL810W-22 anotheruser 1024 Wed Sep 23 08:19:29 2026',
        ]
        response = self.client.get('/api/queue', params={'printer': 'Brother_QL810W'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        data = response.json()
        self.assertIn('Sending data', data['status'])
        self.assertEqual(data['jobs'][0], {
            'id': 'Brother_QL810W-21', 'owner': 'clee', 'bytes': 207872,
            'submitted': 'Wed Sep 23 08:12:43 2026',
        })
        self.assertEqual(len(data['jobs']), 2)
        self.assertEqual(command.call_args.args[0], ['lpstat', '-W', 'not-completed', '-o', 'Brother_QL810W'])

    @patch('main.command')
    def test_empty_queue_preserves_printer_status(self, command):
        command.side_effect = ['printer Brother_QL810W disabled since yesterday -\n\tPaper jam', '']
        response = self.client.get('/api/queue?printer=Brother_QL810W')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['jobs'], [])
        self.assertIn('Paper jam', response.json()['status'])

    @patch('main.command')
    def test_queue_requires_a_valid_destination(self, command):
        for params in [{}, {'printer': ''}, {'printer': '-a'}, {'printer': 'a b'}]:
            self.assertEqual(self.client.get('/api/queue', params=params).status_code, 422)
        command.assert_not_called()

    @patch('main.subprocess.run')
    def test_queue_error_is_not_an_empty_queue(self, run):
        run.return_value = subprocess.CompletedProcess(['lpstat'], 1, b'', b'Scheduler is not running')
        response = self.client.get('/api/queue?printer=Brother_QL810W')
        self.assertEqual(response.status_code, 503)
        self.assertIn('Scheduler', response.json()['detail'])

    @patch('main.command')
    def test_unexpected_queue_output_is_reported(self, command):
        for listing in ['unrecognized output', 'OtherPrinter-21 clee 1024 yesterday']:
            command.side_effect = ['printer Brother_QL810W is idle.', listing]
            response = self.client.get('/api/queue?printer=Brother_QL810W')
            self.assertEqual(response.status_code, 502)

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
    def test_default_four_inch_label_uses_monochrome_raster(self, command):
        command.side_effect = ['Brother_QL810W', 'request id is Brother_QL810W-44 (1 file(s))']
        response = self.client.post('/api/print', json={'text': 'Four inches', 'printer': 'Brother_QL810W'})
        self.assertEqual(response.status_code, 200, response.text)
        args, raster = command.call_args.args
        self.assertIn('raw', args)
        self.assertIn(b'\x1b\x69\x4b\x08', raster)  # Black-only mode, cut at end.
        self.assertIn(b'\x1b\x69\x64\x23\x00', raster)  # 35 feed dots at each end.
        frame = raster[raster.index(b'\x67\x00\x5a'):-1]
        self.assertEqual(len(frame), (1200 - 70) * 93)  # Four inches at 300 dpi.
        black = bytearray()
        for offset in range(0, len(frame), 93):
            self.assertEqual(frame[offset:offset+3], b'\x67\x00\x5a')
            black.extend(frame[offset+3:offset+93])
        self.assertTrue(any(black))
        self.assertEqual(raster[-1:], b'\x1a')

    @patch('main.command')
    def test_black_red_roll_uses_two_planes_and_raw_submission(self, command):
        command.side_effect = ['Brother_QL810W', 'request id is Brother_QL810W-43 (1 file(s))']
        response = self.client.post('/api/print', json={'text': 'USB cables', 'printer': 'Brother_QL810W', 'size': '62red'})
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

    @patch('main.getpass.getuser', return_value='labeluser')
    @patch('main.command')
    def test_cancel_is_scoped_to_current_user_and_selected_printer(self, command, user):
        command.side_effect = ['Brother_QL810W\nOtherPrinter', '']
        # Cancellation needs neither a label nor an in-browser remembered job ID.
        response = self.client.post('/api/cancel', json={'printer': 'Brother_QL810W'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn('Cancellation requested', response.json()['message'])
        self.assertEqual(command.call_args.args[0], ['cancel', '-a', '-u', 'labeluser', 'Brother_QL810W'])

    @patch('main.command')
    def test_cancel_rejects_invalid_or_missing_destination(self, command):
        for printer in ['', '-a', 'Brother;cancel -a']:
            response = self.client.post('/api/cancel', json={'printer': printer})
            self.assertEqual(response.status_code, 422)
        command.assert_not_called()
        command.return_value = 'OtherPrinter'
        response = self.client.post('/api/cancel', json={'printer': 'missing'})
        self.assertEqual(response.status_code, 422)
        command.assert_called_once_with(['lpstat', '-e'])

    @patch('main.command')
    def test_cross_site_cancel_is_rejected(self, command):
        response = self.client.post('/api/cancel', json={'printer': 'Brother'}, headers={'Origin': 'https://example.org'})
        self.assertEqual(response.status_code, 403)
        command.assert_not_called()

    @patch('main.subprocess.run')
    def test_cancel_failure_is_not_reported_as_success(self, run):
        run.side_effect = [
            subprocess.CompletedProcess(['lpstat'], 0, b'Brother_QL810W\n', b''),
            subprocess.CompletedProcess(['cancel'], 1, b'', b'cancel: Not authorized'),
        ]
        response = self.client.post('/api/cancel', json={'printer': 'Brother_QL810W'})
        self.assertEqual(response.status_code, 503)
        self.assertIn('Not authorized', response.json()['detail'])

    @patch('main.subprocess.run')
    def test_cups_failure_is_reported(self, run):
        run.return_value = subprocess.CompletedProcess(['lpstat'], 1, b'', b'Cannot connect to CUPS')
        response = self.client.get('/api/printers')
        self.assertEqual(response.status_code, 503)
        self.assertIn('Cannot connect', response.json()['detail'])


if __name__ == '__main__':
    unittest.main()
