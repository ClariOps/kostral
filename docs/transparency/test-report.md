# KOSTRAL test report

Generated 2026-11-10 18:46 by `tests/report.py`. Do not edit by hand.

## Summary

| Outcome | Count |
| --- | --- |
| passed | 123 |
| total | 123 |

## Example files by use case

| Use case | Files | Passed | Not passed |
| --- | --- | --- | --- |
| degraded-json | 21 | 21 | 0 |
| explain-json | 28 | 28 | 0 |
| optimize-json | 28 | 28 | 0 |
| optimize-yaml | 28 | 28 | 0 |

## Other passing tests

| Test | Guarantee or purpose |
| --- | --- |
| `test_guarantees.test_directory_input_does_not_depend_on_file_order` | A folder of manifests must give identical output however the files were created. |
| `test_guarantees.test_same_output_twice_from_different_directories` | same manifest, same output, from any working directory. |
| `test_guarantees.test_exit_code_does_not_depend_on_dry_run_or_output_format` | same input, same decision, whatever the flags or renderer. |
| `test_guarantees.test_failed_status_exits_nonzero` | a failed check is reported by a non-zero exit code. |
| `test_guarantees.test_findings_and_crash_have_different_exit_codes` | CI can tell "the manifest failed" (1) from "koss broke" (3). |
| `test_guarantees.test_good_manifest_exits_zero` | test good manifest exits zero |
| `test_guarantees.test_invalid_output_format_is_an_error` | test invalid output format is an error |
| `test_guarantees.test_missing_file_is_a_clear_error` | test missing file is a clear error |
| `test_guarantees.test_no_command_is_an_error` | test no command is an error |
| `test_guarantees.test_version_flag` | test version flag |
| `test_guarantees.test_directory_input_reads_every_manifest` | test directory input reads every manifest |
| `test_guarantees.test_manifest_can_be_piped_through_stdin` | Helm-rendered YAML can be piped in. |
| `test_guarantees.test_explain_yaml_returns_the_manifest_unchanged` | analysis commands do not change the manifest. |
| `test_guarantees.test_source_files_are_never_modified` | koss never rewrites the user's files. |
| `test_matrix.test_examples_found` | test examples found |
| `test_remote.test_remote_run_with_servers_down_fails_loudly` | A missing engine must be an error, never an empty report. |
| `test_remote.test_remote_output_is_deterministic` | test remote output is deterministic |
| `test_remote.test_remote_result_matches_local_result` | test remote result matches local result |
