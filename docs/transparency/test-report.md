# KOSTRAL test report

Generated 2026-11-17 15:36 by `tests/report.py`. Do not edit by hand.

## Summary

| Outcome | Count |
| --- | --- |
| passed | 147 |
| total | 147 |

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
| `test_contract.test_a_typo_in_metadata_is_an_error_not_silently_ignored` | test a typo in metadata is an error not silently ignored |
| `test_contract.test_bus_rejects_an_engine_with_unknown_metadata` | test bus rejects an engine with unknown metadata |
| `test_contract.test_checks_phase_refuses_a_mutating_engine` | test checks phase refuses a mutating engine |
| `test_contract.test_engine_cannot_delete_earlier_findings` | test engine cannot delete earlier findings |
| `test_contract.test_engine_cannot_edit_its_metadata_in_place` | test engine cannot edit its metadata in place |
| `test_contract.test_engine_cannot_grant_itself_mutation_during_a_run` | test engine cannot grant itself mutation during a run |
| `test_contract.test_engine_metadata_is_per_instance` | test engine metadata is per instance |
| `test_contract.test_engine_that_changes_manifests_without_declaring_it_is_rejected` | test engine that changes manifests without declaring it is rejected |
| `test_contract.test_mutating_engine_must_report_what_it_changed` | test mutating engine must report what it changed |
| `test_contract.test_mutating_engine_that_reports_is_accepted` | test mutating engine that reports is accepted |
| `test_contract.test_parallel_checks_run_in_list_order` | test parallel checks run in list order |
| `test_contract.test_workflow_can_grant_mutation_to_a_local_engine` | test workflow can grant mutation to a local engine |
| `test_contract.test_workflow_cannot_put_a_mutating_engine_in_parallel_checks` | test workflow cannot put a mutating engine in parallel checks |
| `test_contract.test_directory_input_is_read_in_sorted_filename_order` | test directory input is read in sorted filename order |
| `test_contract.test_approved_remote_mutation_is_accepted_when_reported` | test approved remote mutation is accepted when reported |
| `test_contract.test_constructor_is_not_a_way_around_the_registry` | One obvious way: the plain constructor takes no permissions at all. |
| `test_contract.test_malformed_finding_is_an_error` | test malformed finding is an error |
| `test_contract.test_registry_approval_alone_does_not_make_an_engine_mutating` | test registry approval alone does not make an engine mutating |
| `test_contract.test_registry_with_unknown_metadata_is_an_error` | test registry with unknown metadata is an error |
| `test_contract.test_remote_engine_cannot_erase_findings` | Old behavior: an empty 'report' in the reply turned FAILED into PASSED. |
| `test_contract.test_remote_findings_are_appended` | test remote findings are appended |
| `test_contract.test_remote_mutation_needs_workflow_request_and_registry_approval` | test remote mutation needs workflow request and registry approval |
| `test_contract.test_remote_that_changes_manifests_without_permission_is_rejected` | test remote that changes manifests without permission is rejected |
| `test_contract.test_reply_without_findings_is_an_error_not_an_empty_result` | test reply without findings is an error not an empty result |
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
