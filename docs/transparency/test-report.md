# KOSTRAL test report

Generated 2026-11-20 18:48 by `tests/report.py`. Do not edit by hand.

## Summary

| Outcome | Count |
| --- | --- |
| passed | 226 |
| known failure | 1 |
| total | 227 |

## Known failures (code breaks a guarantee today)

| Test | Guarantee | Reason |
| --- | --- | --- |
| `test_runner.test_adding_a_typed_document_is_not_touching_the_opaque_ones` | not tagged | KNOWN LIMITATION, DECISION NEEDED. The opaque snapshot records each document's absolute position, so a mutating engine that inserts a typed document ahead of them shifts every index and is rejected as if it had reordered them. Comparing the opaque documents as an ordered list (without the index) keeps the 'modified, removed or reordered' guarantee and avoids the false alarm. Remove the marker once you decide. |

## Example files by use case

| Use case | Files | Passed | Not passed |
| --- | --- | --- | --- |
| degraded-json | 22 | 22 | 0 |
| explain-json | 29 | 29 | 0 |
| optimize-json | 29 | 29 | 0 |
| optimize-yaml | 29 | 29 | 0 |

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
| `test_coverage.test_a_document_without_a_name_does_not_break_the_run` | test a document without a name does not break the run |
| `test_coverage.test_an_unmodeled_document_loads_and_renders_back_verbatim` | test an unmodeled document loads and renders back verbatim |
| `test_coverage.test_documents_that_are_not_kubernetes_resources_are_still_skipped` | test documents that are not kubernetes resources are still skipped |
| `test_coverage.test_unmodeled_documents_are_rendered_unchanged_and_in_order` | test unmodeled documents are rendered unchanged and in order |
| `test_coverage.test_every_unmodeled_document_is_reported` | test every unmodeled document is reported |
| `test_coverage.test_modeled_kinds_are_not_reported_as_unanalyzed` | test modeled kinds are not reported as unanalyzed |
| `test_coverage.test_the_gap_is_visible_for_piped_input_too` | test the gap is visible for piped input too |
| `test_coverage.test_the_text_report_names_the_unanalyzed_kind` | test the text report names the unanalyzed kind |
| `test_coverage.test_unanalyzed_kind_is_a_warning_so_ci_still_passes` | test unanalyzed kind is a warning so ci still passes |
| `test_descriptor.test_a_valid_descriptor_is_accepted` | test a valid descriptor is accepted |
| `test_descriptor.test_missing_and_unknown_fields_are_errors` | test missing and unknown fields are errors |
| `test_descriptor.test_registry_pins_need_both_fields_and_nothing_else` | test registry pins need both fields and nothing else |
| `test_descriptor.test_wrong_types_are_errors` | test wrong types are errors |
| `test_descriptor.test_a_malformed_descriptor_is_a_remote_engine_error` | test a malformed descriptor is a remote engine error |
| `test_descriptor.test_a_mismatch_means_no_document_is_ever_sent` | test a mismatch means no document is ever sent |
| `test_descriptor.test_an_unreachable_descriptor_is_an_error_not_an_empty_result` | test an unreachable descriptor is an error not an empty result |
| `test_descriptor.test_the_descriptor_is_read_before_any_document_and_only_once` | test the descriptor is read before any document and only once |
| `test_descriptor.test_workflow_allowing_mutation_must_match_what_the_engine_declares` | test workflow allowing mutation must match what the engine declares |
| `test_descriptor.test_a_typo_in_an_entry_is_an_error` | test a typo in an entry is an error |
| `test_descriptor.test_an_entry_must_pin_the_version_and_kinds` | test an entry must pin the version and kinds |
| `test_descriptor.test_every_entry_in_the_shipped_example_registry_loads` | test every entry in the shipped example registry loads |
| `test_descriptor.test_the_pins_are_kept_on_the_client` | test the pins are kept on the client |
| `test_descriptor.test_a_server_with_a_bad_declaration_refuses_to_start` | test a server with a bad declaration refuses to start |
| `test_descriptor.test_describe_is_served_over_http_and_process_still_works` | test describe is served over http and process still works |
| `test_descriptor.test_the_descriptor_is_built_from_the_engine_and_the_operators_declaration` | test the descriptor is built from the engine and the operators declaration |
| `test_descriptor.test_there_are_no_defaults_for_version_and_kinds` | test there are no defaults for version and kinds |
| `test_descriptor.test_a_matching_engine_passes` | test a matching engine passes |
| `test_descriptor.test_each_mismatch_is_refused_with_its_own_reason` | test each mismatch is refused with its own reason |
| `test_descriptor.test_the_order_of_input_kinds_does_not_matter` | test the order of input kinds does not matter |
| `test_descriptor.test_without_pins_identity_contract_and_mutation_are_still_verified` | test without pins identity contract and mutation are still verified |
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
| `test_hold_back.test_a_document_that_came_back_as_another_kind` | test a document that came back as another kind |
| `test_hold_back.test_an_extra_document_such_as_an_injected_secret` | test an extra document such as an injected secret |
| `test_hold_back.test_documents_in_a_different_order` | test documents in a different order |
| `test_hold_back.test_fewer_documents_than_were_sent` | test fewer documents than were sent |
| `test_hold_back.test_a_mutating_engine_changes_its_documents_and_the_rest_stays_put` | test a mutating engine changes its documents and the rest stays put |
| `test_hold_back.test_a_secret_is_sent_only_when_the_registry_names_it` | test a secret is sent only when the registry names it |
| `test_hold_back.test_a_secret_never_reaches_an_engine_that_did_not_ask_for_it` | test a secret never reaches an engine that did not ask for it |
| `test_hold_back.test_a_wildcard_engine_gets_everything_but_the_secret` | test a wildcard engine gets everything but the secret |
| `test_hold_back.test_held_documents_come_back_in_place_and_unchanged` | test held documents come back in place and unchanged |
| `test_hold_back.test_the_engine_receives_only_its_declared_kinds` | test the engine receives only its declared kinds |
| `test_hold_back.test_without_a_registry_a_server_cannot_ask_for_secrets_by_itself` | test without a registry a server cannot ask for secrets by itself |
| `test_hold_back.test_a_secret_needs_to_be_named` | test a secret needs to be named |
| `test_hold_back.test_a_wildcard_means_everything_except_secrets` | test a wildcard means everything except secrets |
| `test_hold_back.test_named_kinds_are_accepted` | test named kinds are accepted |
| `test_hold_back.test_a_real_server_only_ever_sees_its_declared_kinds` | test a real server only ever sees its declared kinds |
| `test_hold_back.test_the_server_answers_400_to_a_client_that_sends_more` | test the server answers 400 to a client that sends more |
| `test_hold_back.test_a_wildcard_still_holds_back_the_secret` | test a wildcard still holds back the secret |
| `test_hold_back.test_merge_restores_the_original_list` | test merge restores the original list |
| `test_hold_back.test_nothing_declared_means_nothing_sent` | test nothing declared means nothing sent |
| `test_hold_back.test_split_keeps_the_held_documents_with_their_positions` | test split keeps the held documents with their positions |
| `test_matrix.test_examples_found` | test examples found |
| `test_remote.test_remote_run_with_servers_down_fails_loudly` | A missing engine must be an error, never an empty report. |
| `test_remote.test_a_secret_in_the_input_stays_out_of_the_engines_and_in_the_output` | The example servers declare Deployment/Service only. The Secret is held back by the client, and remote and local still render identical manifests. |
| `test_remote.test_remote_output_is_deterministic` | test remote output is deterministic |
| `test_remote.test_remote_result_matches_local_result` | test remote result matches local result |
| `test_runner.test_explain_and_optimize_report_each_gap_exactly_once` | test explain and optimize report each gap exactly once |
| `test_runner.test_remote_with_a_workflow_that_has_no_validator_still_reports_the_gap` | The point of the layer: a workflow author cannot compose coverage away. |
| `test_runner.test_stdin_goes_through_the_runner_too` | test stdin goes through the runner too |
| `test_runner.test_the_runner_does_not_change_the_rendered_manifests` | test the runner does not change the rendered manifests |
| `test_runner.test_it_never_changes_the_documents` | test it never changes the documents |
| `test_runner.test_it_only_appends_to_the_report` | test it only appends to the report |
| `test_runner.test_nothing_to_say_when_every_document_is_modeled` | test nothing to say when every document is modeled |
| `test_runner.test_one_warning_per_unanalyzed_document_in_document_order` | test one warning per unanalyzed document in document order |
| `test_runner.test_opaque_documents_are_flagged_and_typed_ones_are_not` | test opaque documents are flagged and typed ones are not |
| `test_runner.test_a_full_workflow_does_not_report_the_same_gap_twice` | Catches a leftover validator rule that duplicates the system report. |
| `test_runner.test_a_workflow_without_a_validator_still_reports_the_gap` | test a workflow without a validator still reports the gap |
| `test_runner.test_an_empty_workflow_still_reports_the_gap` | test an empty workflow still reports the gap |
| `test_runner.test_an_engine_cannot_erase_the_coverage_findings` | test an engine cannot erase the coverage findings |
| `test_runner.test_skip_rules_and_allow_rules_cannot_hide_it` | DECISION encoded here: coverage is a system responsibility, so the user's rule filters (which only apply to workflow rules) do not touch it. |
| `test_runner.test_a_mutating_engine_may_still_change_typed_documents_next_to_them` | test a mutating engine may still change typed documents next to them |
| `test_runner.test_editing_an_opaque_document_is_rejected` | test editing an opaque document is rejected |
| `test_runner.test_editing_is_rejected_even_when_the_engine_may_mutate_and_reports_it` | test editing is rejected even when the engine may mutate and reports it |
| `test_runner.test_removing_an_opaque_document_is_rejected` | test removing an opaque document is rejected |
| `test_runner.test_reordering_opaque_documents_is_rejected` | test reordering opaque documents is rejected |
| `test_runner.test_any_object_with_run_is_a_workflow` | test any object with run is a workflow |
| `test_runner.test_coverage_runs_before_any_workflow_engine` | test coverage runs before any workflow engine |
| `test_runner.test_the_runner_hands_back_what_the_workflow_returns` | test the runner hands back what the workflow returns |
| `test_runner.test_workflow_and_coverage_each_run_exactly_once` | test workflow and coverage each run exactly once |
| `test_runner.test_workflow_errors_are_not_swallowed` | test workflow errors are not swallowed |
