"""Regression checks for benchmark validity, accounting and failed-run reporting."""
import json
import io
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch, MagicMock
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmarks.benchmark_latency import fmt_stats, load_cases, run_cli, run_mcp
from benchmarks.benchmark_output import compare


class Gateway:
    def __init__(self, response):
        self.response = response

    def call_tool(self, *args):
        return self.response


class BenchmarkTests(unittest.TestCase):
    def test_cli_failure_is_not_timed(self):
        with self.assertRaises(RuntimeError):
            run_cli([sys.executable, '-c', 'raise SystemExit(1)'], ['expected'])

    def test_cli_wrong_resource_is_rejected(self):
        with self.assertRaises(ValueError):
            run_cli([sys.executable, '-c', 'print("wrong")'], ['expected'])

    def test_successful_cli(self):
        elapsed, text = run_cli([sys.executable, '-c', 'print("expected")'], ['expected'])
        self.assertGreater(elapsed, 0)
        self.assertEqual(text, 'expected\n')

    def test_mcp_errors_rejected(self):
        for response in [{'error': {'code': -1}}, {'result': {'isError': True}}, {}]:
            with self.subTest(response=response), self.assertRaises(RuntimeError):
                run_mcp(Gateway(response), 'test', {}, ['expected'])

    def test_mcp_empty_or_wrong_output_rejected(self):
        for content in [[], [{'type': 'text', 'text': 'wrong'}]]:
            with self.subTest(content=content), self.assertRaises(ValueError):
                run_mcp(Gateway({'result': {'content': content}}), 'test', {}, ['expected'])

    def test_mcp_text_and_structured_success(self):
        for result in [{'content': [{'type': 'text', 'text': 'expected'}]},
                       {'structuredContent': {'summary': 'expected'}}]:
            elapsed, text = run_mcp(Gateway({'result': result}), 'test', {}, ['expected'])
            self.assertGreaterEqual(elapsed, 0)
            self.assertIn('expected', text)

    def test_p95_nearest_rank(self):
        result = fmt_stats(list(range(1, 31)))
        self.assertEqual(result['n'], 30)
        self.assertEqual(result['median_ms'], 15.5)
        self.assertEqual(result['p95_ms'], 29)

    def test_case_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cases.json'
            for cases in [[], [{'name': 'x', 'cli': ['get']}]]:
                path.write_text(json.dumps(cases))
                with self.assertRaises(ValueError):
                    load_cases(path)

    def test_output_counts_unicode_and_negative_reduction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'atlas').write_bytes('測試更多'.encode())
            (root / 'mcp').write_bytes('測試'.encode())
            manifest = [{'name': 'unicode', 'expected': ['測試'], 'files': {'atlas': 'atlas', 'mcp': 'mcp'}}]
            result = compare(manifest, root)
            self.assertEqual(result['totals']['atlas'], {'chars': 4, 'utf8_bytes': 12})
            self.assertEqual(result['atlas_reduction_percent']['mcp']['utf8_bytes'], -100)
            (root / 'atlas').write_text('missing')
            with self.assertRaises(ValueError):
                compare(manifest, root)

    def test_output_baselines_must_cover_same_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'data').write_text('expected')
            cases = [{'name': 'a', 'expected': ['expected'], 'files': {'atlas': 'data', 'mcp': 'data', 'raw': 'data'}},
                     {'name': 'b', 'expected': ['expected'], 'files': {'atlas': 'data', 'mcp': 'data'}}]
            with self.assertRaises(ValueError):
                compare(cases, root)

    def test_methods_alternate_and_warmup_is_excluded(self):
        from benchmarks import benchmark_latency as runner
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = [{"name": "shared", "cli": ["jira", "get", "DEMO-1"],
                      "mcp_tool": "get", "mcp_args": {},
                      "expect_cli": ["expected"], "expect_mcp": ["expected"]}]
            path = root / 'cases.json'
            path.write_text(json.dumps(cases))
            output = root / 'result.json'
            order = []

            def cli(*args):
                order.append('cli')
                return 10, 'expected'

            def mcp(*args):
                order.append('mcp')
                return 20, 'expected'

            argv = ['runner', '--cases', str(path), '--server', 'test',
                    '--server-version', 'test-digest', '--runs', '2', '--warmup', '1',
                    '--output', str(output)]
            with patch.object(sys, 'argv', argv), patch.object(runner, 'McpGateway', return_value=MagicMock()), patch.object(runner, 'command_version', return_value='test'), patch.object(runner, 'run_cli', side_effect=cli), patch.object(runner, 'run_mcp', side_effect=mcp), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(runner.main(), 0)
            self.assertEqual(order, ['cli', 'mcp', 'mcp', 'cli', 'cli', 'mcp'])
            report = json.loads(output.read_text())
            self.assertEqual([row['n'] for row in report['summary']], [2, 2])
            self.assertEqual(len(report['samples']), 6)

    def test_cli_only_report_and_failure_exit(self):
        runner = Path(__file__).resolve().parents[1] / 'benchmarks' / 'benchmark_latency.py'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = [{'name': 'synthetic smoke', 'cli': ['-c', 'print("expected")'],
                      'mcp_tool': 'unused', 'mcp_args': {}, 'expect_cli': ['expected'], 'expect_mcp': ['expected']}]
            path = root / 'cases.json'
            for successful in [True, False]:
                if not successful:
                    cases[0]['cli'] = ['-c', 'raise SystemExit(1)']
                path.write_text(json.dumps(cases))
                output = root / f'{successful}.json'
                process = subprocess.run([sys.executable, str(runner), '--cases', str(path),
                    '--atlas', sys.executable, '--cli-only', '--runs', '2', '--warmup', '1',
                    '--output', str(output)], capture_output=True, text=True)
                report = json.loads(output.read_text())
                self.assertEqual(process.returncode, 0 if successful else 1)
                self.assertEqual(report['status'], 'complete' if successful else 'failed')
                if successful:
                    self.assertEqual(len(report['samples']), 3)
                    self.assertEqual(report['summary'][0]['n'], 2)
                else:
                    self.assertEqual(report['summary'], [])
                    self.assertNotIn('| Operation |', process.stdout)

    def test_two_clis_share_a_case_without_mcp_settings(self):
        runner = Path(__file__).resolve().parents[1] / 'benchmarks' / 'benchmark_latency.py'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'cases.json'
            path.write_text(json.dumps([{
                'name': 'shared case',
                'cli': ['-c', 'print("expected atlas")'],
                'expect_cli': ['expected atlas'],
                'compare_cli': ['-c', 'print("expected baseline")'],
                'expect_compare_cli': ['expected baseline'],
            }]))
            output = root / 'result.json'
            result = subprocess.run([
                sys.executable, str(runner), '--cases', str(path), '--atlas', sys.executable,
                '--compare-cli', sys.executable, '--cli-only', '--runs', '2', '--warmup', '0',
                '--output', str(output),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text())
            self.assertEqual([row['method'] for row in report['samples']],
                             ['cli', 'compare_cli', 'compare_cli', 'cli'])
            self.assertEqual([row['n'] for row in report['summary']], [2, 2])


if __name__ == '__main__':
    unittest.main()
