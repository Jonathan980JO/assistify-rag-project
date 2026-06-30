# Unnecessary Files Report

Generated: 2026-06-29 23:58 UTC

Repo: `assistify-rag-project-main` (project root)

**Report only — no files were deleted.**

## Summary

| Tier | Label | Count |
|------|-------|-------|
| A | Tier A — High confidence unnecessary | 94 |
| B | Tier B — Likely redundant (keep one canonical copy) | 129 |
| C | Tier C — Stale path bindings | 25 |
| D | Tier D — Review before touching | 7 |
| E | Tier E — Flagged but kept / informational | 0 |

| **Total flagged** | | **255** |

## Recommended next actions

- **Tier A:** Safe to delete after manual spot-check (backups, temp scripts, OS junk).
- **Tier B:** Consolidate duplicates; keep canonical copy under `scripts/` or `tools/testing/`.
- **Tier C:** Fix paths to repo-relative or delete if obsolete debug scripts.
- **Tier D:** Archive audit markdown to `docs/archive/`; verify stub modules before removal.

## Tier A — High confidence unnecessary

| Path | Reason | Size | Stale path | Duplicates |
|------|--------|------|------------|------------|
| `._assistify_session_secret` | gitignore_mismatch; os_junk | 96 B | - | - |
| `Json/auto_selftest_report.json` | eval_output | 48.5 KB | - | - |
| `Json/rag_eval_21_report.json` | eval_output | 31.9 KB | - | - |
| `Json/retrieval_debug_report.json` | eval_output | 119.7 KB | - | - |
| `Json/smoke5_debug_report.json` | eval_output | 30.4 KB | - | - |
| `Json/tmp_patch_results.json` | temp_scratch | 1.2 KB | - | - |
| `Login_system/users.db.pre_mt_backup` | gitignore_mismatch; pre_mt_backup | 76.0 KB | - | - |
| `Notepad_Test_Results/temp_db.txt` | temp_scratch | 9.8 KB | - | - |
| `Notepad_Test_Results/tmp_iter1_full.log` | temp_scratch | 486.4 KB | - | - |
| `Notepad_Test_Results/tmp_iter2_full.log` | temp_scratch | 487.7 KB | - | - |
| `Notepad_Test_Results/tmp_iter3_full.log` | temp_scratch | 488.2 KB | - | - |
| `Notepad_Test_Results/tmp_iter4_full.log` | temp_scratch | 470.5 KB | - | - |
| `Notepad_Test_Results/tmp_iter5_full.log` | temp_scratch | 488.2 KB | - | - |
| `Notepad_Test_Results/tmp_psychology_source.txt` | temp_scratch | 128 B | - | - |
| `Notepad_Test_Results/tmp_scidef_debug_out.txt` | temp_scratch | 60.4 KB | - | - |
| `Notepad_Test_Results/tmp_ws_entity_logs.txt` | temp_scratch | 3.5 KB | - | - |
| `Notepad_Test_Results/tmp_ws_entity_logs_utf8.txt` | temp_scratch | 3.5 KB | - | - |
| `Notepad_Test_Results/tmp_ws_final7_proof.log` | temp_scratch | 1.3 KB | - | - |
| `Notepad_Test_Results/tmp_ws_live_backend.log` | temp_scratch | 5.0 KB | - | - |
| `Notepad_Test_Results/tmp_ws_live_backend.out.log` | temp_scratch | 5.0 KB | - | - |
| `archived_pdfs/docs/tmp_validation_Principles_of_Management.pdf` | temp_scratch | 2.7 MB | - | - |
| `backend/analytics.db.pre_mt_backup` | gitignore_mismatch; pre_mt_backup | 52.0 KB | - | - |
| `backend/conversations.db.pre_mt_backup` | gitignore_mismatch; pre_mt_backup | 48.0 KB | - | - |
| `backend/conversations.json` | eval_output | 15.2 KB | - | - |
| `backend/tmp_fact_self_test.py` | temp_scratch | 6.4 KB | - | - |
| `backend/tmp_generation_validation.py` | temp_scratch | 3.1 KB | - | - |
| `backend/tmp_list_logs_after.json` | temp_scratch | 13.7 KB | - | - |
| `backend/tmp_list_logs_after2.json` | temp_scratch | 14.6 KB | - | - |
| `backend/tmp_list_logs_before.json` | temp_scratch | 164.6 KB | - | - |
| `backend/tmp_one_query_debug.py` | temp_scratch | 1.2 KB | - | - |
| `backend/tmp_prompt_quality_eval.py` | temp_scratch | 1.1 KB | - | - |
| `backend/tmp_rag_quality_eval.py` | temp_scratch | 3.8 KB | - | - |
| `legacy/non_functional/TMP_Codes/temp_parse.py` | temp_scratch | 363 B | - | - |
| `legacy/non_functional/TMP_Codes/temp_test.py` | temp_scratch | 1.6 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_activation_lifecycle_result.json` | temp_scratch | 5.2 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_auth_check.py` | temp_scratch | 454 B | - | - |
| `legacy/non_functional/TMP_Codes/tmp_auto_pdf_selftest.py` | temp_scratch | 16.5 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_check_collections.py` | temp_scratch | 1.1 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_check_live_rag.py` | temp_scratch | 729 B | - | - |
| `legacy/non_functional/TMP_Codes/tmp_compare_p3.py` | temp_scratch | 1.4 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_compare_p3b.py` | temp_scratch | 1.4 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_compare_p4.py` | temp_scratch | 1.4 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_debug_steps_query.py` | temp_scratch | 570 B | - | - |
| `legacy/non_functional/TMP_Codes/tmp_def_decision_debug.py` | temp_scratch | 687 B | - | - |
| `legacy/non_functional/TMP_Codes/tmp_def_pipeline_debug3.py` | temp_scratch | 751 B | - | - |
| `legacy/non_functional/TMP_Codes/tmp_def_select_pages_patchcheck.py` | temp_scratch | 1.1 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_def_selection_winner_fix.diff` | temp_scratch | 30.1 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_definition_priority_validation.py` | temp_scratch | 772 B | - | - |
| `legacy/non_functional/TMP_Codes/tmp_definition_typo_validation.py` | temp_scratch | 803 B | - | - |
| `legacy/non_functional/TMP_Codes/tmp_direct_phase_runner.py` | temp_scratch | 3.5 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_entity_select_debug.py` | temp_scratch | 1.2 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_eval_run.py` | temp_scratch | 2.6 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_failed6_check.py` | temp_scratch | 1.6 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_final_answer_quality_validation.py` | temp_scratch | 4.1 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_final_diff_req4.diff` | temp_scratch | 21.6 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_force_promote_patch.diff` | temp_scratch | 11.8 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_http_smoke.py` | temp_scratch | 368 B | - | - |
| `legacy/non_functional/TMP_Codes/tmp_inspect_chroma.py` | temp_scratch | 1.2 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_latency5_final_recovery.py` | temp_scratch | 1.6 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_latency_safety_validate.py` | temp_scratch | 1.9 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_manual_upload_check.py` | temp_scratch | 884 B | - | - |
| `legacy/non_functional/TMP_Codes/tmp_perf_validation_final_opt.py` | temp_scratch | 1.1 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_rebuild_adaptive_psych.py` | stale_path; temp_scratch | 1.3 KB | yes | - |
| `legacy/non_functional/TMP_Codes/tmp_req5_diff.diff` | temp_scratch | 19.3 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_retrieval_debug_pass.py` | temp_scratch | 4.2 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_retrieve_debug_auth.py` | temp_scratch | 1.1 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_scientific_sentences_probe.py` | temp_scratch | 892 B | - | - |
| `legacy/non_functional/TMP_Codes/tmp_single_mode_stability_loop.py` | temp_scratch | 5.0 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_validate_activation_pipeline.py` | temp_scratch | 4.3 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_ws_4_queries_patch.py` | temp_scratch | 2.8 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_ws_7_queries.py` | temp_scratch | 2.7 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_ws_acceptance_5.py` | temp_scratch | 2.9 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_ws_debug_done.py` | temp_scratch | 1.6 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_ws_definition_routing_test.py` | temp_scratch | 2.0 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_ws_eval.py` | temp_scratch | 1.9 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_ws_exact3_patchcheck.py` | temp_scratch | 2.4 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_ws_explain_operant_validation.py` | temp_scratch | 1.8 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_ws_final_target7.py` | temp_scratch | 1.8 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_ws_mandatory_8.py` | temp_scratch | 2.3 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_ws_one.py` | temp_scratch | 1.1 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_ws_perf3.py` | temp_scratch | 1.4 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_ws_perf_new.py` | temp_scratch | 1.3 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_ws_phase_runner.py` | temp_scratch | 4.1 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_ws_phase_tests.py` | temp_scratch | 2.6 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_ws_required_7_structural.py` | temp_scratch | 2.2 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_ws_smoke.py` | temp_scratch | 929 B | - | - |
| `legacy/non_functional/TMP_Codes/tmp_ws_smoke_france.py` | temp_scratch | 925 B | - | - |
| `legacy/non_functional/TMP_Codes/tmp_ws_smoke_ft.py` | temp_scratch | 698 B | - | - |
| `legacy/non_functional/TMP_Codes/tmp_ws_target_5_realpath.py` | temp_scratch | 1.9 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_ws_target_eval.py` | temp_scratch | 2.6 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_ws_validate_stream.py` | temp_scratch | 1.3 KB | - | - |
| `legacy/non_functional/TMP_Codes/tmp_ws_validation_exact.py` | temp_scratch | 2.8 KB | - | - |
| `tests/eval_dual_corpus_report.json` | eval_output | 4.7 KB | - | - |
| `tests/farco_car_kb_eval_report.json` | eval_output | 34.3 KB | - | - |

## Tier B — Likely redundant (keep one canonical copy)

| Path | Reason | Size | Stale path | Duplicates |
|------|--------|------|------------|------------|
| `.remember/.gitignore` | duplicate_basename | 2 B | - | `.gitignore`, `legacy/ui-drafts/assistify-ui-design (1)/.gitignore`, `legacy/ui-drafts/assistify-ui-design (2)/.gitignore` |
| `.vscode/settings.json` | duplicate_basename | 188 B | - | `Backup/project_config_backup/20260311_000646/.vscode/settings.json` |
| `Backup/project_config_backup/20260311_000646/.vscode/settings.json` | duplicate_basename | 56 B | - | `.vscode/settings.json` |
| `Backup/project_config_backup/20260311_000646/body.json` | duplicate_basename | 81 B | - | `Json/body.json` |
| `Backup/project_config_backup/20260311_000646/environment_main.yml` | duplicate_basename | 1.3 KB | - | `environment_main.yml` |
| `Backup/project_config_backup/20260311_000646/environment_main_locked.yml` | duplicate_basename | 4.3 KB | - | `environment_main_locked.yml` |
| `Backup/project_config_backup/20260311_000646/environment_xtts.yml` | duplicate_basename | 1.0 KB | - | `environment_xtts.yml` |
| `Backup/project_config_backup/20260311_000646/environment_xtts_locked.yml` | duplicate_basename | 4.5 KB | - | `environment_xtts_locked.yml` |
| `Json/body.json` | duplicate_basename | 81 B | - | `Backup/project_config_backup/20260311_000646/body.json` |
| `Login_system/core/dependencies.py` | duplicate_basename | 1.1 KB | - | `backend/core/dependencies.py` |
| `Login_system/static/favicon.ico` | duplicate_basename | 872 B | - | `assistify-ui-design/app/favicon.ico`, `assistify-ui-design/out/favicon.ico`, `backend/assets/favicon.ico` |
| `Login_system/utils/validation.py` | duplicate_basename | 2.2 KB | - | `backend/retrieval/validation.py` |
| `Qwen2.5-7B-GGUF/README.md` | duplicate_basename | 4.2 KB | - | `README.md`, `archived_pdfs/docs/README.md`, `archived_pdfs/docs/diagrams/README.md` (+3 more) |
| `TTS/api.py` | duplicate_basename | 235 B | - | `TTS_local_backup/api.py` |
| `TTS_local_backup/api.py` | duplicate_basename | 235 B | - | `TTS/api.py` |
| `archive/audits/assistify_refactor_audit/assistify_rag_server.py` | duplicate_basename | 2.0 MB | - | `backend/assistify_rag_server.py` |
| `archive/audits/assistify_refactor_audit/login_server.py` | duplicate_basename | 229.5 KB | - | `Login_system/login_server.py` |
| `archive/audits/assistify_refactor_audit/pdf_ingestion_rag.py` | duplicate_basename | 96.1 KB | - | `backend/pdf_ingestion_rag.py` |
| `archived_pdfs/docs/ACRONYMS_LIST.md` | duplicate_basename | 7.8 KB | - | `docs/ACRONYMS_LIST.md` |
| `archived_pdfs/docs/ACTUAL_SYSTEM_IMPLEMENTATION.md` | duplicate_basename | 46.7 KB | - | `docs/ACTUAL_SYSTEM_IMPLEMENTATION.md` |
| `archived_pdfs/docs/EMAILJS_SETUP.md` | duplicate_basename | 8.6 KB | - | `docs/EMAILJS_SETUP.md` |
| `archived_pdfs/docs/ENV_SETUP_COMPLETE.md` | duplicate_basename | 2.3 KB | - | `docs/ENV_SETUP_COMPLETE.md` |
| `archived_pdfs/docs/FASTER_WHISPER_MIGRATION.md` | duplicate_basename | 7.9 KB | - | `docs/FASTER_WHISPER_MIGRATION.md` |
| `archived_pdfs/docs/FASTER_WHISPER_SETUP.md` | duplicate_basename | 5.3 KB | - | `docs/FASTER_WHISPER_SETUP.md` |
| `archived_pdfs/docs/GOOGLE_OAUTH_SETUP.md` | duplicate_basename | 7.7 KB | - | `docs/GOOGLE_OAUTH_SETUP.md` |
| `archived_pdfs/docs/IEEE_STANDARDS_CHECKLIST.md` | duplicate_basename | 5.4 KB | - | `docs/IEEE_STANDARDS_CHECKLIST.md` |
| `archived_pdfs/docs/METADATA_FIX_FINAL_REPORT.md` | duplicate_basename | 9.0 KB | - | `docs/METADATA_FIX_FINAL_REPORT.md` |
| `archived_pdfs/docs/OWASP_IMPLEMENTATION_REPORT.md` | duplicate_basename | 16.1 KB | - | `docs/OWASP_IMPLEMENTATION_REPORT.md` |
| `archived_pdfs/docs/PROFILE_AND_PASSWORD_RESET.md` | duplicate_basename | 10.9 KB | - | `docs/PROFILE_AND_PASSWORD_RESET.md` |
| `archived_pdfs/docs/PROJECT_BRIEFING.md` | duplicate_basename | 37.7 KB | - | `docs/PROJECT_BRIEFING.md` |
| `archived_pdfs/docs/QUICK_SECURITY_SETUP.md` | duplicate_basename | 4.5 KB | - | `docs/QUICK_SECURITY_SETUP.md` |
| `archived_pdfs/docs/README.md` | duplicate_basename | 1.5 KB | - | `Qwen2.5-7B-GGUF/README.md`, `README.md`, `archived_pdfs/docs/diagrams/README.md` (+3 more) |
| `archived_pdfs/docs/RESPONSE_VALIDATION_SETUP.md` | duplicate_basename | 6.2 KB | - | `docs/RESPONSE_VALIDATION_SETUP.md` |
| `archived_pdfs/docs/SECURITY_IMPLEMENTATION.md` | duplicate_basename | 11.7 KB | - | `docs/SECURITY_IMPLEMENTATION.md` |
| `archived_pdfs/docs/STABLE_RELEASE_NOTES.md` | duplicate_basename | 3.1 KB | - | `docs/STABLE_RELEASE_NOTES.md` |
| `archived_pdfs/docs/SYSTEM_AUDIT_REPORT.md` | duplicate_basename | 9.5 KB | - | `docs/SYSTEM_AUDIT_REPORT.md` |
| `archived_pdfs/docs/TABLE_OF_CONTENTS_TEMPLATE.md` | duplicate_basename | 11.8 KB | - | `docs/TABLE_OF_CONTENTS_TEMPLATE.md` |
| `archived_pdfs/docs/TOON_IMPLEMENTATION.md` | duplicate_basename | 9.5 KB | - | `docs/TOON_IMPLEMENTATION.md` |
| `archived_pdfs/docs/XTTS_PATCHES.md` | duplicate_basename | 4.2 KB | - | `docs/XTTS_PATCHES.md` |
| `archived_pdfs/docs/diagrams/1_sequence_diagram.md` | duplicate_basename | 3.7 KB | - | `docs/diagrams/1_sequence_diagram.md` |
| `archived_pdfs/docs/diagrams/2_activity_flowchart.md` | duplicate_basename | 6.7 KB | - | `docs/diagrams/2_activity_flowchart.md` |
| `archived_pdfs/docs/diagrams/3_class_diagram.md` | duplicate_basename | 10.1 KB | - | `docs/diagrams/3_class_diagram.md` |
| `archived_pdfs/docs/diagrams/4_process_flow.md` | duplicate_basename | 8.2 KB | - | `docs/diagrams/4_process_flow.md` |
| `archived_pdfs/docs/diagrams/README.md` | duplicate_basename | 6.0 KB | - | `Qwen2.5-7B-GGUF/README.md`, `README.md`, `archived_pdfs/docs/README.md` (+3 more) |
| `backend/ChromaDB/chroma.sqlite3` | duplicate_basename | 164.0 KB | - | `backend/chroma_db_production/chroma.sqlite3`, `chroma_db_production/chroma.sqlite3` |
| `backend/assets/favicon.ico` | duplicate_basename | 872 B | - | `Login_system/static/favicon.ico`, `assistify-ui-design/app/favicon.ico`, `assistify-ui-design/out/favicon.ico` |
| `backend/chroma_db_production/chroma.sqlite3` | duplicate_basename | 1.8 MB | - | `backend/ChromaDB/chroma.sqlite3`, `chroma_db_production/chroma.sqlite3` |
| `backend/core/config.py` | duplicate_basename | 4.9 KB | - | `backend/voice_audio/config.py`, `config.py` |
| `backend/core/dependencies.py` | duplicate_basename | 893 B | - | `Login_system/core/dependencies.py` |
| `backend/retrieval/validation.py` | duplicate_basename | 18.3 KB | - | `Login_system/utils/validation.py` |
| `backend/voice_audio/config.py` | duplicate_basename | 1.8 KB | - | `backend/core/config.py`, `config.py` |
| `backend/voice_audio/stt/routes.py` | duplicate_basename | 3.8 KB | - | `backend/voice_audio/tts/routes.py` |
| `backend/voice_audio/tts/routes.py` | duplicate_basename | 4.4 KB | - | `backend/voice_audio/stt/routes.py` |
| `chroma_db_production/chroma.sqlite3` | duplicate_basename | 164.0 KB | - | `backend/ChromaDB/chroma.sqlite3`, `backend/chroma_db_production/chroma.sqlite3` |
| `legacy/stubs/README.md` | duplicate_basename | 1.2 KB | - | `Qwen2.5-7B-GGUF/README.md`, `README.md`, `archived_pdfs/docs/README.md` (+3 more) |
| `legacy/ui-drafts/assistify-ui-design (1)/.gitignore` | duplicate_basename | 223 B | - | `.gitignore`, `.remember/.gitignore`, `legacy/ui-drafts/assistify-ui-design (2)/.gitignore` |
| `legacy/ui-drafts/assistify-ui-design (1)/app/admin/analytics/page.tsx` | duplicate_basename | 8.3 KB | - | `assistify-ui-design/app/(app)/admin/access-requests/page.tsx`, `assistify-ui-design/app/(app)/admin/analytics/page.tsx`, `assistify-ui-design/app/(app)/admin/audit-logs/page.tsx` (+48 more) |
| `legacy/ui-drafts/assistify-ui-design (1)/app/admin/audit-logs/page.tsx` | duplicate_basename | 10.3 KB | - | `assistify-ui-design/app/(app)/admin/access-requests/page.tsx`, `assistify-ui-design/app/(app)/admin/analytics/page.tsx`, `assistify-ui-design/app/(app)/admin/audit-logs/page.tsx` (+48 more) |
| `legacy/ui-drafts/assistify-ui-design (1)/app/admin/knowledge-base/page.tsx` | duplicate_basename | 9.8 KB | - | `assistify-ui-design/app/(app)/admin/access-requests/page.tsx`, `assistify-ui-design/app/(app)/admin/analytics/page.tsx`, `assistify-ui-design/app/(app)/admin/audit-logs/page.tsx` (+48 more) |
| `legacy/ui-drafts/assistify-ui-design (1)/app/admin/layout.tsx` | duplicate_basename | 3.7 KB | - | `assistify-ui-design/app/(app)/layout.tsx`, `assistify-ui-design/app/(auth)/layout.tsx`, `assistify-ui-design/app/(guest)/layout.tsx` (+4 more) |
| `legacy/ui-drafts/assistify-ui-design (1)/app/admin/page.tsx` | duplicate_basename | 7.1 KB | - | `assistify-ui-design/app/(app)/admin/access-requests/page.tsx`, `assistify-ui-design/app/(app)/admin/analytics/page.tsx`, `assistify-ui-design/app/(app)/admin/audit-logs/page.tsx` (+48 more) |
| `legacy/ui-drafts/assistify-ui-design (1)/app/admin/profile/page.tsx` | duplicate_basename | 10.7 KB | - | `assistify-ui-design/app/(app)/admin/access-requests/page.tsx`, `assistify-ui-design/app/(app)/admin/analytics/page.tsx`, `assistify-ui-design/app/(app)/admin/audit-logs/page.tsx` (+48 more) |
| `legacy/ui-drafts/assistify-ui-design (1)/app/admin/users/page.tsx` | duplicate_basename | 12.3 KB | - | `assistify-ui-design/app/(app)/admin/access-requests/page.tsx`, `assistify-ui-design/app/(app)/admin/analytics/page.tsx`, `assistify-ui-design/app/(app)/admin/audit-logs/page.tsx` (+48 more) |
| `legacy/ui-drafts/assistify-ui-design (1)/app/globals.css` | duplicate_basename | 3.2 KB | - | `assistify-ui-design/app/globals.css`, `legacy/ui-drafts/assistify-ui-design (2)/app/globals.css` |
| `legacy/ui-drafts/assistify-ui-design (1)/app/layout.tsx` | duplicate_basename | 1.5 KB | - | `assistify-ui-design/app/(app)/layout.tsx`, `assistify-ui-design/app/(auth)/layout.tsx`, `assistify-ui-design/app/(guest)/layout.tsx` (+4 more) |
| `legacy/ui-drafts/assistify-ui-design (1)/app/page.tsx` | duplicate_basename | 115 B | - | `assistify-ui-design/app/(app)/admin/access-requests/page.tsx`, `assistify-ui-design/app/(app)/admin/analytics/page.tsx`, `assistify-ui-design/app/(app)/admin/audit-logs/page.tsx` (+48 more) |
| `legacy/ui-drafts/assistify-ui-design (1)/components.json` | duplicate_basename | 449 B | - | `legacy/ui-drafts/assistify-ui-design (2)/components.json` |
| `legacy/ui-drafts/assistify-ui-design (1)/components/assistify.tsx` | duplicate_basename | 1.0 KB | - | `assistify-ui-design/components/assistify.tsx`, `legacy/ui-drafts/assistify-ui-design (2)/components/assistify.tsx` |
| `legacy/ui-drafts/assistify-ui-design (1)/components/chat-area.tsx` | duplicate_basename | 4.8 KB | - | `assistify-ui-design/components/chat-area.tsx`, `legacy/ui-drafts/assistify-ui-design (2)/components/chat-area.tsx` |
| `legacy/ui-drafts/assistify-ui-design (1)/components/chat-message.tsx` | duplicate_basename | 865 B | - | `assistify-ui-design/components/chat-message.tsx`, `legacy/ui-drafts/assistify-ui-design (2)/components/chat-message.tsx` |
| `legacy/ui-drafts/assistify-ui-design (1)/components/header.tsx` | duplicate_basename | 2.9 KB | - | `assistify-ui-design/components/header.tsx`, `legacy/ui-drafts/assistify-ui-design (2)/components/header.tsx` |
| `legacy/ui-drafts/assistify-ui-design (1)/components/kb-banner.tsx` | duplicate_basename | 582 B | - | `assistify-ui-design/components/kb-banner.tsx`, `legacy/ui-drafts/assistify-ui-design (2)/components/kb-banner.tsx` |
| `legacy/ui-drafts/assistify-ui-design (1)/components/sidebar.tsx` | duplicate_basename | 2.3 KB | - | `assistify-ui-design/components/sidebar.tsx`, `legacy/ui-drafts/assistify-ui-design (2)/components/sidebar.tsx` |
| `legacy/ui-drafts/assistify-ui-design (1)/components/thinking-indicator.tsx` | duplicate_basename | 498 B | - | `assistify-ui-design/components/thinking-indicator.tsx`, `legacy/ui-drafts/assistify-ui-design (2)/components/thinking-indicator.tsx` |
| `legacy/ui-drafts/assistify-ui-design (1)/components/ui/button.tsx` | duplicate_basename | 3.2 KB | - | `assistify-ui-design/components/ui/button.tsx`, `legacy/ui-drafts/assistify-ui-design (2)/components/ui/button.tsx` |
| `legacy/ui-drafts/assistify-ui-design (1)/components/voice-overlay.tsx` | duplicate_basename | 2.8 KB | - | `assistify-ui-design/components/voice-overlay.tsx`, `legacy/ui-drafts/assistify-ui-design (2)/components/voice-overlay.tsx` |
| `legacy/ui-drafts/assistify-ui-design (1)/next.config.mjs` | duplicate_basename | 192 B | - | `assistify-ui-design/next.config.mjs`, `legacy/ui-drafts/assistify-ui-design (2)/next.config.mjs` |
| `legacy/ui-drafts/assistify-ui-design (1)/package.json` | duplicate_basename | 857 B | - | `assistify-ui-design/.next/build/package.json`, `assistify-ui-design/.next/package.json`, `assistify-ui-design/package.json` (+1 more) |
| `legacy/ui-drafts/assistify-ui-design (1)/pnpm-lock.yaml` | duplicate_basename | 126.2 KB | - | `legacy/ui-drafts/assistify-ui-design (2)/pnpm-lock.yaml` |
| `legacy/ui-drafts/assistify-ui-design (1)/postcss.config.mjs` | duplicate_basename | 152 B | - | `assistify-ui-design/postcss.config.mjs`, `legacy/ui-drafts/assistify-ui-design (2)/postcss.config.mjs` |
| `legacy/ui-drafts/assistify-ui-design (1)/public/apple-icon.png` | duplicate_basename | 2.6 KB | - | `legacy/ui-drafts/assistify-ui-design (2)/public/apple-icon.png` |
| `legacy/ui-drafts/assistify-ui-design (1)/public/icon-dark-32x32.png` | duplicate_basename | 585 B | - | `legacy/ui-drafts/assistify-ui-design (2)/public/icon-dark-32x32.png` |
| `legacy/ui-drafts/assistify-ui-design (1)/public/icon-light-32x32.png` | duplicate_basename | 566 B | - | `legacy/ui-drafts/assistify-ui-design (2)/public/icon-light-32x32.png` |
| `legacy/ui-drafts/assistify-ui-design (1)/public/icon.svg` | duplicate_basename | 1.3 KB | - | `legacy/ui-drafts/assistify-ui-design (2)/public/icon.svg` |
| `legacy/ui-drafts/assistify-ui-design (1)/public/placeholder-logo.png` | duplicate_basename | 568 B | - | `legacy/ui-drafts/assistify-ui-design (2)/public/placeholder-logo.png` |
| `legacy/ui-drafts/assistify-ui-design (1)/public/placeholder-logo.svg` | duplicate_basename | 3.1 KB | - | `legacy/ui-drafts/assistify-ui-design (2)/public/placeholder-logo.svg` |
| `legacy/ui-drafts/assistify-ui-design (1)/public/placeholder-user.jpg` | duplicate_basename | 1.6 KB | - | `legacy/ui-drafts/assistify-ui-design (2)/public/placeholder-user.jpg` |
| `legacy/ui-drafts/assistify-ui-design (1)/public/placeholder.jpg` | duplicate_basename | 1.0 KB | - | `legacy/ui-drafts/assistify-ui-design (2)/public/placeholder.jpg` |
| `legacy/ui-drafts/assistify-ui-design (1)/public/placeholder.svg` | duplicate_basename | 3.2 KB | - | `legacy/ui-drafts/assistify-ui-design (2)/public/placeholder.svg` |
| `legacy/ui-drafts/assistify-ui-design (1)/tsconfig.json` | duplicate_basename | 736 B | - | `assistify-ui-design/tsconfig.json`, `legacy/ui-drafts/assistify-ui-design (2)/tsconfig.json` |
| `legacy/ui-drafts/assistify-ui-design (2)/.gitignore` | duplicate_basename | 223 B | - | `.gitignore`, `.remember/.gitignore`, `legacy/ui-drafts/assistify-ui-design (1)/.gitignore` |
| `legacy/ui-drafts/assistify-ui-design (2)/app/admin/access-requests/page.tsx` | duplicate_basename | 9.0 KB | - | `assistify-ui-design/app/(app)/admin/access-requests/page.tsx`, `assistify-ui-design/app/(app)/admin/analytics/page.tsx`, `assistify-ui-design/app/(app)/admin/audit-logs/page.tsx` (+48 more) |
| `legacy/ui-drafts/assistify-ui-design (2)/app/admin/analytics/page.tsx` | duplicate_basename | 8.3 KB | - | `assistify-ui-design/app/(app)/admin/access-requests/page.tsx`, `assistify-ui-design/app/(app)/admin/analytics/page.tsx`, `assistify-ui-design/app/(app)/admin/audit-logs/page.tsx` (+48 more) |
| `legacy/ui-drafts/assistify-ui-design (2)/app/admin/audit-logs/page.tsx` | duplicate_basename | 10.3 KB | - | `assistify-ui-design/app/(app)/admin/access-requests/page.tsx`, `assistify-ui-design/app/(app)/admin/analytics/page.tsx`, `assistify-ui-design/app/(app)/admin/audit-logs/page.tsx` (+48 more) |
| `legacy/ui-drafts/assistify-ui-design (2)/app/admin/knowledge-base/page.tsx` | duplicate_basename | 9.8 KB | - | `assistify-ui-design/app/(app)/admin/access-requests/page.tsx`, `assistify-ui-design/app/(app)/admin/analytics/page.tsx`, `assistify-ui-design/app/(app)/admin/audit-logs/page.tsx` (+48 more) |
| `legacy/ui-drafts/assistify-ui-design (2)/app/admin/layout.tsx` | duplicate_basename | 3.9 KB | - | `assistify-ui-design/app/(app)/layout.tsx`, `assistify-ui-design/app/(auth)/layout.tsx`, `assistify-ui-design/app/(guest)/layout.tsx` (+4 more) |
| `legacy/ui-drafts/assistify-ui-design (2)/app/admin/notifications/page.tsx` | duplicate_basename | 9.0 KB | - | `assistify-ui-design/app/(app)/admin/access-requests/page.tsx`, `assistify-ui-design/app/(app)/admin/analytics/page.tsx`, `assistify-ui-design/app/(app)/admin/audit-logs/page.tsx` (+48 more) |
| `legacy/ui-drafts/assistify-ui-design (2)/app/admin/page.tsx` | duplicate_basename | 7.1 KB | - | `assistify-ui-design/app/(app)/admin/access-requests/page.tsx`, `assistify-ui-design/app/(app)/admin/analytics/page.tsx`, `assistify-ui-design/app/(app)/admin/audit-logs/page.tsx` (+48 more) |
| `legacy/ui-drafts/assistify-ui-design (2)/app/admin/profile/page.tsx` | duplicate_basename | 10.7 KB | - | `assistify-ui-design/app/(app)/admin/access-requests/page.tsx`, `assistify-ui-design/app/(app)/admin/analytics/page.tsx`, `assistify-ui-design/app/(app)/admin/audit-logs/page.tsx` (+48 more) |
| `legacy/ui-drafts/assistify-ui-design (2)/app/admin/superadmin/page.tsx` | duplicate_basename | 11.0 KB | - | `assistify-ui-design/app/(app)/admin/access-requests/page.tsx`, `assistify-ui-design/app/(app)/admin/analytics/page.tsx`, `assistify-ui-design/app/(app)/admin/audit-logs/page.tsx` (+48 more) |
| `legacy/ui-drafts/assistify-ui-design (2)/app/admin/users/page.tsx` | duplicate_basename | 12.3 KB | - | `assistify-ui-design/app/(app)/admin/access-requests/page.tsx`, `assistify-ui-design/app/(app)/admin/analytics/page.tsx`, `assistify-ui-design/app/(app)/admin/audit-logs/page.tsx` (+48 more) |
| `legacy/ui-drafts/assistify-ui-design (2)/app/globals.css` | duplicate_basename | 3.2 KB | - | `assistify-ui-design/app/globals.css`, `legacy/ui-drafts/assistify-ui-design (1)/app/globals.css` |
| `legacy/ui-drafts/assistify-ui-design (2)/app/layout.tsx` | duplicate_basename | 1.5 KB | - | `assistify-ui-design/app/(app)/layout.tsx`, `assistify-ui-design/app/(auth)/layout.tsx`, `assistify-ui-design/app/(guest)/layout.tsx` (+4 more) |
| `legacy/ui-drafts/assistify-ui-design (2)/app/login/page.tsx` | duplicate_basename | 6.4 KB | - | `assistify-ui-design/app/(app)/admin/access-requests/page.tsx`, `assistify-ui-design/app/(app)/admin/analytics/page.tsx`, `assistify-ui-design/app/(app)/admin/audit-logs/page.tsx` (+48 more) |
| `legacy/ui-drafts/assistify-ui-design (2)/app/page.tsx` | duplicate_basename | 115 B | - | `assistify-ui-design/app/(app)/admin/access-requests/page.tsx`, `assistify-ui-design/app/(app)/admin/analytics/page.tsx`, `assistify-ui-design/app/(app)/admin/audit-logs/page.tsx` (+48 more) |
| `legacy/ui-drafts/assistify-ui-design (2)/components.json` | duplicate_basename | 449 B | - | `legacy/ui-drafts/assistify-ui-design (1)/components.json` |
| `legacy/ui-drafts/assistify-ui-design (2)/components/assistify.tsx` | duplicate_basename | 1.0 KB | - | `assistify-ui-design/components/assistify.tsx`, `legacy/ui-drafts/assistify-ui-design (1)/components/assistify.tsx` |
| `legacy/ui-drafts/assistify-ui-design (2)/components/chat-area.tsx` | duplicate_basename | 4.8 KB | - | `assistify-ui-design/components/chat-area.tsx`, `legacy/ui-drafts/assistify-ui-design (1)/components/chat-area.tsx` |
| `legacy/ui-drafts/assistify-ui-design (2)/components/chat-message.tsx` | duplicate_basename | 865 B | - | `assistify-ui-design/components/chat-message.tsx`, `legacy/ui-drafts/assistify-ui-design (1)/components/chat-message.tsx` |
| `legacy/ui-drafts/assistify-ui-design (2)/components/header.tsx` | duplicate_basename | 2.9 KB | - | `assistify-ui-design/components/header.tsx`, `legacy/ui-drafts/assistify-ui-design (1)/components/header.tsx` |
| `legacy/ui-drafts/assistify-ui-design (2)/components/kb-banner.tsx` | duplicate_basename | 582 B | - | `assistify-ui-design/components/kb-banner.tsx`, `legacy/ui-drafts/assistify-ui-design (1)/components/kb-banner.tsx` |
| `legacy/ui-drafts/assistify-ui-design (2)/components/sidebar.tsx` | duplicate_basename | 2.3 KB | - | `assistify-ui-design/components/sidebar.tsx`, `legacy/ui-drafts/assistify-ui-design (1)/components/sidebar.tsx` |
| `legacy/ui-drafts/assistify-ui-design (2)/components/thinking-indicator.tsx` | duplicate_basename | 498 B | - | `assistify-ui-design/components/thinking-indicator.tsx`, `legacy/ui-drafts/assistify-ui-design (1)/components/thinking-indicator.tsx` |
| `legacy/ui-drafts/assistify-ui-design (2)/components/ui/button.tsx` | duplicate_basename | 3.2 KB | - | `assistify-ui-design/components/ui/button.tsx`, `legacy/ui-drafts/assistify-ui-design (1)/components/ui/button.tsx` |
| `legacy/ui-drafts/assistify-ui-design (2)/components/voice-overlay.tsx` | duplicate_basename | 2.8 KB | - | `assistify-ui-design/components/voice-overlay.tsx`, `legacy/ui-drafts/assistify-ui-design (1)/components/voice-overlay.tsx` |
| `legacy/ui-drafts/assistify-ui-design (2)/next.config.mjs` | duplicate_basename | 192 B | - | `assistify-ui-design/next.config.mjs`, `legacy/ui-drafts/assistify-ui-design (1)/next.config.mjs` |
| `legacy/ui-drafts/assistify-ui-design (2)/package.json` | duplicate_basename | 857 B | - | `assistify-ui-design/.next/build/package.json`, `assistify-ui-design/.next/package.json`, `assistify-ui-design/package.json` (+1 more) |
| `legacy/ui-drafts/assistify-ui-design (2)/pnpm-lock.yaml` | duplicate_basename | 126.2 KB | - | `legacy/ui-drafts/assistify-ui-design (1)/pnpm-lock.yaml` |
| `legacy/ui-drafts/assistify-ui-design (2)/postcss.config.mjs` | duplicate_basename | 152 B | - | `assistify-ui-design/postcss.config.mjs`, `legacy/ui-drafts/assistify-ui-design (1)/postcss.config.mjs` |
| `legacy/ui-drafts/assistify-ui-design (2)/public/apple-icon.png` | duplicate_basename | 2.6 KB | - | `legacy/ui-drafts/assistify-ui-design (1)/public/apple-icon.png` |
| `legacy/ui-drafts/assistify-ui-design (2)/public/icon-dark-32x32.png` | duplicate_basename | 585 B | - | `legacy/ui-drafts/assistify-ui-design (1)/public/icon-dark-32x32.png` |
| `legacy/ui-drafts/assistify-ui-design (2)/public/icon-light-32x32.png` | duplicate_basename | 566 B | - | `legacy/ui-drafts/assistify-ui-design (1)/public/icon-light-32x32.png` |
| `legacy/ui-drafts/assistify-ui-design (2)/public/icon.svg` | duplicate_basename | 1.3 KB | - | `legacy/ui-drafts/assistify-ui-design (1)/public/icon.svg` |
| `legacy/ui-drafts/assistify-ui-design (2)/public/placeholder-logo.png` | duplicate_basename | 568 B | - | `legacy/ui-drafts/assistify-ui-design (1)/public/placeholder-logo.png` |
| `legacy/ui-drafts/assistify-ui-design (2)/public/placeholder-logo.svg` | duplicate_basename | 3.1 KB | - | `legacy/ui-drafts/assistify-ui-design (1)/public/placeholder-logo.svg` |
| `legacy/ui-drafts/assistify-ui-design (2)/public/placeholder-user.jpg` | duplicate_basename | 1.6 KB | - | `legacy/ui-drafts/assistify-ui-design (1)/public/placeholder-user.jpg` |
| `legacy/ui-drafts/assistify-ui-design (2)/public/placeholder.jpg` | duplicate_basename | 1.0 KB | - | `legacy/ui-drafts/assistify-ui-design (1)/public/placeholder.jpg` |
| `legacy/ui-drafts/assistify-ui-design (2)/public/placeholder.svg` | duplicate_basename | 3.2 KB | - | `legacy/ui-drafts/assistify-ui-design (1)/public/placeholder.svg` |
| `legacy/ui-drafts/assistify-ui-design (2)/tsconfig.json` | duplicate_basename | 736 B | - | `assistify-ui-design/tsconfig.json`, `legacy/ui-drafts/assistify-ui-design (1)/tsconfig.json` |

## Tier C — Stale path bindings

| Path | Reason | Size | Stale path | Duplicates |
|------|--------|------|------------|------------|
| `Environment_Validation_Report.md` | stale_path | 4.1 KB | yes | - |
| `LAUNCHER_README.md` | stale_path | 4.2 KB | yes | - |
| `Notepad_Test_Results/traceback.txt` | stale_path | 334 B | yes | - |
| `backend/extract_headings.py` | stale_path | 1.2 KB | yes | - |
| `backend/inspect_chroma.py` | stale_path | 1.6 KB | yes | - |
| `backend/run_query.py` | stale_path | 1.1 KB | yes | - |
| `backend/test_chroma_query.py` | stale_path | 865 B | yes | - |
| `backend/test_list_direct.py` | stale_path | 887 B | yes | - |
| `backend/test_list_full.py` | stale_path | 1.6 KB | yes | - |
| `backend/test_ocr.py` | stale_path | 1.1 KB | yes | - |
| `scripts/_rag_score_probe.py` | stale_path | 577 B | yes | - |
| `scripts/_rag_smoke_test.py` | stale_path | 1008 B | yes | - |
| `scripts/launch_windows/_env.bat` | stale_path | 839 B | yes | - |
| `scripts/launch_windows/run_llm.bat` | stale_path | 437 B | yes | - |
| `scripts/launch_windows/run_login.bat` | stale_path | 446 B | yes | - |
| `scripts/launch_windows/run_ollama.bat` | stale_path | 1.6 KB | yes | - |
| `scripts/launch_windows/run_piper.bat` | stale_path | 450 B | yes | - |
| `scripts/launch_windows/run_rag.bat` | stale_path | 444 B | yes | - |
| `scripts/scan_unnecessary_files.py` | stale_path | 20.1 KB | yes | - |
| `scripts/test_six_ms.py` | stale_path | 2.3 KB | yes | - |
| `start_piper_service.bat` | stale_path | 745 B | yes | - |
| `test_search.py` | root_debug_clutter; stale_path; unreferenced | 906 B | yes | - |
| `tools/experiments/dump_chunks_sql_v3.py` | stale_path | 2.4 KB | yes | - |
| `tools/experiments/get_chunks.py` | stale_path | 2.4 KB | yes | - |
| `tools/testing/piper_smoke_load.py` | stale_path | 672 B | yes | - |

## Tier D — Review before touching

| Path | Reason | Size | Stale path | Duplicates |
|------|--------|------|------------|------------|
| `AGENT_TASK_PROMPT.md` | audit_markdown | 5.4 KB | - | - |
| `_write_phase13d_report.py` | root_debug_clutter; unreferenced | 24.8 KB | - | - |
| `backend/test` | misnamed_test | 127 B | - | - |
| `cleanup_repo.py` | root_debug_clutter; unreferenced | 8.2 KB | - | - |
| `conftest.py` | root_debug_clutter; unreferenced | 271 B | - | - |
| `hotswap_validation.py` | root_debug_clutter; unreferenced | 18.1 KB | - | - |
| `test_list_patch.py` | root_debug_clutter; unreferenced | 1.3 KB | - | - |

