import json
import re

import pytest

from coding_tutor.engine.codes import dotted
from coding_tutor.engine.rules import (
    TableError,
    all_codes,
    answer_to_dict,
    code_check,
    combos,
    correct_codes,
    coverage_check,
    is_excluded,
    load_table,
    load_tables,
    main,
    make_table,
    match_rule,
    matches,
    resolve,
    resolve_report,
    table_report,
    validate,
)

# CPT (AMA-licensed) codes look like 5 digits or 4 digits + F/T/U. ICD-10-CM codes never do.
CPT_LIKE = re.compile(r"^\d{4}[0-9FTU]$")

# Hand-written answers, one case per decision-table rule (checked by test_every_rule_has_an_expected_case).
EXPECTED = [
    # ckd_staging: htn, ckd, status
    ("ckd_staging", {"stage": "1", "hypertension": "yes", "dialysis": "no"}, ["I12.9", "N18.1"]),
    ("ckd_staging", {"stage": "2", "hypertension": "no", "dialysis": "no"}, ["N18.2"]),
    ("ckd_staging", {"stage": "3a", "hypertension": "no", "dialysis": "no"}, ["N18.31"]),
    ("ckd_staging", {"stage": "3b", "hypertension": "yes", "dialysis": "no"}, ["I12.9", "N18.32"]),
    ("ckd_staging", {"stage": "3_unspecified", "hypertension": "no", "dialysis": "no"}, ["N18.30"]),
    ("ckd_staging", {"stage": "4", "hypertension": "yes", "dialysis": "no"}, ["I12.9", "N18.4"]),
    ("ckd_staging", {"stage": "5", "hypertension": "yes", "dialysis": "no"}, ["I12.0", "N18.5"]),
    ("ckd_staging", {"stage": "esrd", "hypertension": "yes", "dialysis": "yes"}, ["I12.0", "N18.6", "Z99.2"]),
    ("ckd_staging", {"stage": "esrd", "hypertension": "no", "dialysis": "no"}, ["N18.6"]),
    # diabetes_complications: diabetes, ckd_stage, neuropathy, medication
    ("diabetes_complications",
     {"dm_type": "type2", "complication": "ckd_stage4", "provider_says_unrelated": "no", "meds": "insulin"},
     ["E11.22", "N18.4", "Z79.4"]),
    ("diabetes_complications",
     {"dm_type": "type2", "complication": "ckd_stage4", "provider_says_unrelated": "yes", "meds": "oral"},
     ["E11.9", "N18.4", "Z79.84"]),
    ("diabetes_complications",
     {"dm_type": "type2", "complication": "polyneuropathy", "provider_says_unrelated": "no",
      "meds": "insulin_and_oral"},
     ["E11.42", "Z79.4", "Z79.84"]),
    ("diabetes_complications",
     {"dm_type": "type2", "complication": "polyneuropathy", "provider_says_unrelated": "yes", "meds": "diet_only"},
     ["E11.9", "G62.9"]),
    ("diabetes_complications",
     {"dm_type": "type2", "complication": "hyperglycemia", "provider_says_unrelated": "no", "meds": "insulin"},
     ["E11.65", "Z79.4"]),
    ("diabetes_complications",
     {"dm_type": "type2", "complication": "hypoglycemia", "provider_says_unrelated": "no", "meds": "oral"},
     ["E11.649", "Z79.84"]),
    ("diabetes_complications",
     {"dm_type": "type2", "complication": "none", "provider_says_unrelated": "no", "meds": "diet_only"},
     ["E11.9"]),
    ("diabetes_complications",
     {"dm_type": "type1", "complication": "ckd_stage4", "provider_says_unrelated": "no", "meds": "insulin"},
     ["E10.22", "N18.4"]),
    ("diabetes_complications",
     {"dm_type": "type1", "complication": "ckd_stage4", "provider_says_unrelated": "yes", "meds": "insulin"},
     ["E10.9", "N18.4"]),
    ("diabetes_complications",
     {"dm_type": "type1", "complication": "polyneuropathy", "provider_says_unrelated": "no", "meds": "insulin"},
     ["E10.42"]),
    ("diabetes_complications",
     {"dm_type": "type1", "complication": "polyneuropathy", "provider_says_unrelated": "yes", "meds": "insulin"},
     ["E10.9", "G62.9"]),
    ("diabetes_complications",
     {"dm_type": "type1", "complication": "hyperglycemia", "provider_says_unrelated": "no", "meds": "insulin"},
     ["E10.65"]),
    ("diabetes_complications",
     {"dm_type": "type1", "complication": "hypoglycemia", "provider_says_unrelated": "no", "meds": "insulin"},
     ["E10.649"]),
    ("diabetes_complications",
     {"dm_type": "type1", "complication": "none", "provider_says_unrelated": "no", "meds": "insulin"},
     ["E10.9"]),
    # meat_support: dx
    ("meat_support", {"condition": "copd", "documentation": "meat_supported"}, ["J44.9"]),
    ("meat_support", {"condition": "chf_chronic_systolic", "documentation": "meat_supported"}, ["I50.22"]),
    ("meat_support", {"condition": "mdd_recurrent_moderate", "documentation": "meat_supported"}, ["F33.1"]),
    ("meat_support", {"condition": "copd", "documentation": "problem_list_only"}, []),
    ("meat_support", {"condition": "chf_chronic_systolic", "documentation": "problem_list_only"}, []),
    ("meat_support", {"condition": "mdd_recurrent_moderate", "documentation": "problem_list_only"}, []),
    ("meat_support", {"condition": "copd", "documentation": "med_list_only"}, []),
    ("meat_support", {"condition": "chf_chronic_systolic", "documentation": "med_list_only"}, []),
    ("meat_support", {"condition": "mdd_recurrent_moderate", "documentation": "med_list_only"}, []),
    # dementia_severity: etiology, dementia
    ("dementia_severity", {"type": "unspecified", "severity": "unspecified", "behavior": "none"}, ["F03.90"]),
    ("dementia_severity", {"type": "unspecified", "severity": "unspecified", "behavior": "agitation"}, ["F03.911"]),
    ("dementia_severity", {"type": "unspecified", "severity": "mild", "behavior": "none"}, ["F03.A0"]),
    ("dementia_severity", {"type": "unspecified", "severity": "mild", "behavior": "agitation"}, ["F03.A11"]),
    ("dementia_severity", {"type": "unspecified", "severity": "moderate", "behavior": "none"}, ["F03.B0"]),
    ("dementia_severity", {"type": "unspecified", "severity": "moderate", "behavior": "agitation"}, ["F03.B11"]),
    ("dementia_severity", {"type": "unspecified", "severity": "severe", "behavior": "none"}, ["F03.C0"]),
    ("dementia_severity", {"type": "unspecified", "severity": "severe", "behavior": "agitation"}, ["F03.C11"]),
    ("dementia_severity", {"type": "alzheimers", "severity": "unspecified", "behavior": "none"}, ["G30.9", "F02.80"]),
    ("dementia_severity", {"type": "alzheimers", "severity": "unspecified", "behavior": "agitation"},
     ["G30.9", "F02.811"]),
    ("dementia_severity", {"type": "alzheimers", "severity": "mild", "behavior": "none"}, ["G30.9", "F02.A0"]),
    ("dementia_severity", {"type": "alzheimers", "severity": "mild", "behavior": "agitation"}, ["G30.9", "F02.A11"]),
    ("dementia_severity", {"type": "alzheimers", "severity": "moderate", "behavior": "none"}, ["G30.9", "F02.B0"]),
    ("dementia_severity", {"type": "alzheimers", "severity": "moderate", "behavior": "agitation"},
     ["G30.9", "F02.B11"]),
    ("dementia_severity", {"type": "alzheimers", "severity": "severe", "behavior": "none"}, ["G30.9", "F02.C0"]),
    ("dementia_severity", {"type": "alzheimers", "severity": "severe", "behavior": "agitation"}, ["G30.9", "F02.C11"]),
    ("dementia_severity", {"type": "mci", "severity": "unspecified", "behavior": "none"}, ["G31.84"]),
    # depression_severity: dx
    ("depression_severity", {"episode": "single", "status": "mild"}, ["F32.0"]),
    ("depression_severity", {"episode": "single", "status": "moderate"}, ["F32.1"]),
    ("depression_severity", {"episode": "single", "status": "severe"}, ["F32.2"]),
    ("depression_severity", {"episode": "single", "status": "severe_psychotic"}, ["F32.3"]),
    ("depression_severity", {"episode": "single", "status": "partial_remission"}, ["F32.4"]),
    ("depression_severity", {"episode": "single", "status": "full_remission"}, ["F32.5"]),
    ("depression_severity", {"episode": "single", "status": "unspecified"}, ["F32.9"]),
    ("depression_severity", {"episode": "recurrent", "status": "mild"}, ["F33.0"]),
    ("depression_severity", {"episode": "recurrent", "status": "moderate"}, ["F33.1"]),
    ("depression_severity", {"episode": "recurrent", "status": "severe"}, ["F33.2"]),
    ("depression_severity", {"episode": "recurrent", "status": "severe_psychotic"}, ["F33.3"]),
    ("depression_severity", {"episode": "recurrent", "status": "partial_remission"}, ["F33.41"]),
    ("depression_severity", {"episode": "recurrent", "status": "full_remission"}, ["F33.42"]),
    ("depression_severity", {"episode": "recurrent", "status": "unspecified"}, ["F33.9"]),
    ("depression_severity", {"episode": "unspecified_depression", "status": "unspecified"}, ["F32.A"]),
    # cancer_status: primary, mets
    ("cancer_status", {"site": "breast_right", "status": "active", "mets": "none"}, ["C50.911"]),
    ("cancer_status", {"site": "breast_right", "status": "history", "mets": "bone"}, ["Z85.3", "C79.51"]),
    ("cancer_status", {"site": "prostate", "status": "active", "mets": "bone"}, ["C61", "C79.51"]),
    ("cancer_status", {"site": "prostate", "status": "history", "mets": "none"}, ["Z85.46"]),
    ("cancer_status", {"site": "lung_right", "status": "active", "mets": "liver"}, ["C34.91", "C78.7"]),
    ("cancer_status", {"site": "lung_right", "status": "history", "mets": "none"}, ["Z85.118"]),
    ("cancer_status", {"site": "colon", "status": "active", "mets": "none"}, ["C18.9"]),
    ("cancer_status", {"site": "colon", "status": "history", "mets": "liver"}, ["Z85.038", "C78.7"]),
    # stroke_sequelae: sequela
    ("stroke_sequelae", {"deficit": "none", "handedness": "not_documented"}, ["Z86.73"]),
    ("stroke_sequelae", {"deficit": "aphasia", "handedness": "not_documented"}, ["I69.320"]),
    ("stroke_sequelae", {"deficit": "hemiplegia_right", "handedness": "right"}, ["I69.351"]),
    ("stroke_sequelae", {"deficit": "hemiplegia_right", "handedness": "left"}, ["I69.353"]),
    ("stroke_sequelae", {"deficit": "hemiplegia_right", "handedness": "not_documented"}, ["I69.351"]),
    ("stroke_sequelae", {"deficit": "hemiplegia_left", "handedness": "right"}, ["I69.354"]),
    ("stroke_sequelae", {"deficit": "hemiplegia_left", "handedness": "left"}, ["I69.352"]),
    ("stroke_sequelae", {"deficit": "hemiplegia_left", "handedness": "not_documented"}, ["I69.354"]),
    # heart_failure: htn, hf
    ("heart_failure", {"hf_type": "systolic", "acuity": "chronic", "hypertension": "yes"}, ["I11.0", "I50.22"]),
    ("heart_failure", {"hf_type": "systolic", "acuity": "acute_on_chronic", "hypertension": "no"}, ["I50.23"]),
    ("heart_failure", {"hf_type": "diastolic", "acuity": "chronic", "hypertension": "no"}, ["I50.32"]),
    ("heart_failure", {"hf_type": "diastolic", "acuity": "acute_on_chronic", "hypertension": "yes"},
     ["I11.0", "I50.33"]),
    # obesity_bmi: dx, bmi
    ("obesity_bmi", {"diagnosis": "none", "bmi": "32"}, []),
    ("obesity_bmi", {"diagnosis": "none", "bmi": "37"}, []),
    ("obesity_bmi", {"diagnosis": "none", "bmi": "42"}, []),
    ("obesity_bmi", {"diagnosis": "none", "bmi": "52"}, []),
    ("obesity_bmi", {"diagnosis": "obesity", "bmi": "32"}, ["E66.9", "Z68.32"]),
    ("obesity_bmi", {"diagnosis": "obesity", "bmi": "52"}, ["E66.9", "Z68.43"]),
    ("obesity_bmi", {"diagnosis": "morbid_obesity", "bmi": "37"}, ["E66.01", "Z68.37"]),
    ("obesity_bmi", {"diagnosis": "morbid_obesity", "bmi": "42"}, ["E66.01", "Z68.41"]),
    # status_codes: status
    ("status_codes", {"condition": "bka_right", "state": "present"}, ["Z89.511"]),
    ("status_codes", {"condition": "aka_left", "state": "present"}, ["Z89.612"]),
    ("status_codes", {"condition": "toe_right", "state": "present"}, ["Z89.411"]),
    ("status_codes", {"condition": "colostomy", "state": "present"}, ["Z93.3"]),
    ("status_codes", {"condition": "ileostomy", "state": "present"}, ["Z93.2"]),
    ("status_codes", {"condition": "colostomy", "state": "reversed"}, []),
    ("status_codes", {"condition": "ileostomy", "state": "reversed"}, []),
    # alcohol_use: dx
    ("alcohol_use", {"documentation": "social_drinking", "remission": "no"}, []),
    ("alcohol_use", {"documentation": "use_disorder_mild", "remission": "no"}, ["F10.10"]),
    ("alcohol_use", {"documentation": "use_disorder_mild", "remission": "yes"}, ["F10.11"]),
    ("alcohol_use", {"documentation": "use_disorder_moderate", "remission": "no"}, ["F10.20"]),
    ("alcohol_use", {"documentation": "use_disorder_severe", "remission": "yes"}, ["F10.21"]),
    # atrial_fibrillation: afib, anticoag
    ("atrial_fibrillation", {"type": "unspecified", "status": "resolved", "anticoagulant": "no"}, ["Z86.79"]),
    ("atrial_fibrillation", {"type": "paroxysmal", "status": "current", "anticoagulant": "yes"}, ["I48.0", "Z79.01"]),
    ("atrial_fibrillation", {"type": "persistent", "status": "current", "anticoagulant": "no"}, ["I48.19"]),
    ("atrial_fibrillation", {"type": "permanent", "status": "current", "anticoagulant": "yes"}, ["I48.21", "Z79.01"]),
    ("atrial_fibrillation", {"type": "unspecified", "status": "current", "anticoagulant": "no"}, ["I48.91"]),
    # diabetes_htn_ckd: diabetes, htn, ckd, status
    ("diabetes_htn_ckd", {"stage": "3a", "hypertension": "yes", "dialysis": "no"}, ["E11.22", "I12.9", "N18.31"]),
    ("diabetes_htn_ckd", {"stage": "3b", "hypertension": "no", "dialysis": "no"}, ["E11.22", "N18.32"]),
    ("diabetes_htn_ckd", {"stage": "4", "hypertension": "yes", "dialysis": "no"}, ["E11.22", "I12.9", "N18.4"]),
    ("diabetes_htn_ckd", {"stage": "5", "hypertension": "yes", "dialysis": "no"}, ["E11.22", "I12.0", "N18.5"]),
    ("diabetes_htn_ckd", {"stage": "esrd", "hypertension": "no", "dialysis": "yes"}, ["E11.22", "N18.6", "Z99.2"]),
    # pad_atherosclerosis: pad, ulcer
    ("pad_atherosclerosis", {"severity": "pvd_unspecified", "side": "right"}, ["I73.9"]),
    ("pad_atherosclerosis", {"severity": "claudication", "side": "right"}, ["I70.211"]),
    ("pad_atherosclerosis", {"severity": "claudication", "side": "left"}, ["I70.212"]),
    ("pad_atherosclerosis", {"severity": "rest_pain", "side": "right"}, ["I70.221"]),
    ("pad_atherosclerosis", {"severity": "rest_pain", "side": "left"}, ["I70.222"]),
    ("pad_atherosclerosis", {"severity": "ulcer", "side": "right"}, ["I70.235", "L97.519"]),
    ("pad_atherosclerosis", {"severity": "ulcer", "side": "left"}, ["I70.245", "L97.529"]),
    # copd_respiratory: lung, respiratory
    ("copd_respiratory", {"form": "copd", "respiratory": "none"}, ["J44.9"]),
    ("copd_respiratory", {"form": "copd_exacerbation", "respiratory": "oxygen_only"}, ["J44.1", "Z99.81"]),
    ("copd_respiratory", {"form": "emphysema", "respiratory": "chronic_failure"}, ["J43.9", "J96.11", "Z99.81"]),
    # pressure_ulcer: ulcer
    ("pressure_ulcer", {"site": "sacral", "stage": "2"}, ["L89.152"]),
    ("pressure_ulcer", {"site": "sacral", "stage": "3"}, ["L89.153"]),
    ("pressure_ulcer", {"site": "sacral", "stage": "4"}, ["L89.154"]),
    ("pressure_ulcer", {"site": "sacral", "stage": "unstageable"}, ["L89.150"]),
    ("pressure_ulcer", {"site": "sacral", "stage": "unspecified"}, ["L89.159"]),
    ("pressure_ulcer", {"site": "sacral", "stage": "healed"}, []),
    ("pressure_ulcer", {"site": "right_heel", "stage": "2"}, ["L89.612"]),
    ("pressure_ulcer", {"site": "right_heel", "stage": "3"}, ["L89.613"]),
    ("pressure_ulcer", {"site": "right_heel", "stage": "4"}, ["L89.614"]),
    ("pressure_ulcer", {"site": "right_heel", "stage": "unstageable"}, ["L89.610"]),
    ("pressure_ulcer", {"site": "right_heel", "stage": "unspecified"}, ["L89.619"]),
    ("pressure_ulcer", {"site": "right_heel", "stage": "healed"}, []),
    # liver_disease: liver
    ("liver_disease", {"condition": "cirrhosis"}, ["K74.60"]),
    ("liver_disease", {"condition": "alcoholic_cirrhosis"}, ["K70.30"]),
    ("liver_disease", {"condition": "alcoholic_cirrhosis_ascites"}, ["K70.31"]),
    ("liver_disease", {"condition": "hep_c_chronic"}, ["B18.2"]),
    ("liver_disease", {"condition": "hep_c_cured"}, ["Z86.19"]),
    ("liver_disease", {"condition": "fatty_liver"}, ["K76.0"]),
    # neuro_conditions: neuro
    ("neuro_conditions", {"condition": "epilepsy"}, ["G40.909"]),
    ("neuro_conditions", {"condition": "epilepsy_intractable"}, ["G40.919"]),
    ("neuro_conditions", {"condition": "seizure_disorder"}, ["G40.909"]),
    ("neuro_conditions", {"condition": "single_seizure_history"}, ["Z86.69"]),
    ("neuro_conditions", {"condition": "parkinsons"}, ["G20.A1"]),
    ("neuro_conditions", {"condition": "ms_relapsing"}, ["G35.A"]),
    ("neuro_conditions", {"condition": "ms_unspecified"}, ["G35.D"]),
    # rheumatoid_arthritis: arthritis, drug
    ("rheumatoid_arthritis", {"diagnosis": "ra_unspecified", "methotrexate": "no"}, ["M06.9"]),
    ("rheumatoid_arthritis", {"diagnosis": "ra_seropositive", "methotrexate": "yes"}, ["M05.79", "Z79.631"]),
    ("rheumatoid_arthritis", {"diagnosis": "osteoarthritis", "methotrexate": "no"}, ["M17.0"]),
    # hiv
    ("hiv_status", {"status": "asymptomatic"}, ["Z21"]),
    ("hiv_status", {"status": "aids"}, ["B20"]),
    ("hiv_status", {"status": "prior_hiv_illness"}, ["B20"]),
    ("hiv_status", {"status": "inconclusive"}, ["R75"]),
    # ibd
    ("gi_conditions", {"condition": "crohns"}, ["K50.90"]),
    ("gi_conditions", {"condition": "crohns_small"}, ["K50.00"]),
    ("gi_conditions", {"condition": "uc"}, ["K51.90"]),
    ("gi_conditions", {"condition": "uc_pancolitis"}, ["K51.00"]),
    ("gi_conditions", {"condition": "ibs"}, ["K58.9"]),
    ("gi_conditions", {"condition": "chronic_pancreatitis"}, ["K86.1"]),
    ("gi_conditions", {"condition": "acute_pancreatitis_history"}, ["Z87.19"]),
    # blood_immune
    ("blood_immune", {"condition": "sickle_cell_disease"}, ["D57.1"]),
    ("blood_immune", {"condition": "sickle_cell_trait"}, ["D57.3"]),
    ("blood_immune", {"condition": "itp"}, ["D69.3"]),
    ("blood_immune", {"condition": "thrombocytopenia"}, ["D69.6"]),
    ("blood_immune", {"condition": "cvid"}, ["D83.9"]),
    # eye
    ("eye_conditions", {"condition": "wet_amd_active"}, ["H35.3211"]),
    ("eye_conditions", {"condition": "wet_amd_scar"}, ["H35.3213"]),
    ("eye_conditions", {"condition": "dry_amd_early"}, ["H35.3111"]),
    ("eye_conditions", {"condition": "pdr"}, ["E11.3591"]),
    ("eye_conditions", {"condition": "npdr_mild"}, ["E11.3291"]),
    # hip_fracture
    ("hip_fracture", {"side": "right", "encounter": "initial"}, ["S72.001A"]),
    ("hip_fracture", {"side": "left", "encounter": "initial"}, ["S72.002A"]),
    ("hip_fracture", {"side": "right", "encounter": "healing"}, ["S72.001D"]),
    ("hip_fracture", {"side": "left", "encounter": "healing"}, ["S72.002D"]),
    ("hip_fracture", {"side": "right", "encounter": "healed"}, ["Z87.81"]),
    ("hip_fracture", {"side": "left", "encounter": "healed"}, ["Z87.81"]),
    # acceptable_sources
    ("acceptable_sources", {"source": "office_visit"}, ["J44.9"]),
    ("acceptable_sources", {"source": "radiology_report"}, []),
    ("acceptable_sources", {"source": "nurse_visit"}, []),
    ("acceptable_sources", {"source": "unsigned_note"}, []),
    # heart_failure_advanced
    ("heart_failure_advanced", {"condition": "end_stage"}, ["I50.84"]),
    ("heart_failure_advanced", {"condition": "end_stage_systolic"}, ["I50.84", "I50.22"]),
    ("heart_failure_advanced", {"condition": "lvad"}, ["I50.22", "Z95.811"]),
    ("heart_failure_advanced", {"condition": "acute_systolic"}, ["I50.21"]),
    ("heart_failure_advanced", {"condition": "acute_diastolic"}, ["I50.31"]),
    # cardiomyopathy
    ("cardiomyopathy", {"condition": "hcm_obstructive"}, ["I42.1"]),
    ("cardiomyopathy", {"condition": "hcm_nonobstructive"}, ["I42.2"]),
    ("cardiomyopathy", {"condition": "ischemic"}, ["I25.5"]),
    ("cardiomyopathy", {"condition": "unspecified"}, ["I42.9"]),
    # mi_angina
    ("mi_angina", {"condition": "nstemi_recent"}, ["I21.4"]),
    ("mi_angina", {"condition": "old_mi"}, ["I25.2"]),
    ("mi_angina", {"condition": "cad_unstable"}, ["I25.110"]),
    ("mi_angina", {"condition": "cad_angina"}, ["I25.119"]),
    # vte_status
    ("vte_status", {"condition": "acute_dvt"}, ["I82.411"]),
    ("vte_status", {"condition": "chronic_dvt"}, ["I82.511"]),
    ("vte_status", {"condition": "dvt_history"}, ["Z86.718"]),
    ("vte_status", {"condition": "acute_pe"}, ["I26.99"]),
    ("vte_status", {"condition": "chronic_pe"}, ["I27.82"]),
    ("vte_status", {"condition": "pe_history"}, ["Z86.711"]),
    # bipolar_schizophrenia
    ("bipolar_schizophrenia", {"condition": "schizophrenia_paranoid"}, ["F20.0"]),
    ("bipolar_schizophrenia", {"condition": "schizoaffective_bipolar"}, ["F25.0"]),
    ("bipolar_schizophrenia", {"condition": "bipolar_depressed_moderate"}, ["F31.32"]),
    ("bipolar_schizophrenia", {"condition": "bipolar_partial_remission"}, ["F31.75"]),
    ("bipolar_schizophrenia", {"condition": "bipolar_full_remission"}, ["F31.76"]),
    ("bipolar_schizophrenia", {"condition": "bipolar_unspecified"}, ["F31.9"]),
    # personality_eating
    ("personality_eating", {"condition": "borderline"}, ["F60.3"]),
    ("personality_eating", {"condition": "personality_unspecified"}, ["F60.9"]),
    ("personality_eating", {"condition": "anorexia_restricting_moderate"}, ["F50.011"]),
    ("personality_eating", {"condition": "anorexia_restricting_remission"}, ["F50.014"]),
    ("personality_eating", {"condition": "bulimia_severe"}, ["F50.23"]),
    # drug_use
    ("drug_use", {"condition": "opioid_mild"}, ["F11.10"]),
    ("drug_use", {"condition": "opioid_moderate"}, ["F11.20"]),
    ("drug_use", {"condition": "opioid_remission"}, ["F11.21"]),
    ("drug_use", {"condition": "cannabis_mild"}, ["F12.10"]),
    ("drug_use", {"condition": "cocaine_psychotic"}, ["F14.251"]),
    ("drug_use", {"condition": "alcohol_psychotic"}, ["F10.251"]),
    # stroke_inpatient
    ("stroke_inpatient", {"condition": "ischemic"}, ["I63.9"]),
    ("stroke_inpatient", {"condition": "hemorrhage"}, ["I61.9"]),
    ("stroke_inpatient", {"condition": "tia"}, ["G45.9"]),
    # paralysis
    ("paralysis", {"condition": "quad_c5c7_incomplete"}, ["G82.54"]),
    ("paralysis", {"condition": "para_complete"}, ["G82.21"]),
    ("paralysis", {"condition": "para_unspecified"}, ["G82.20"]),
    ("paralysis", {"condition": "monoplegia_right_leg"}, ["G83.11"]),
    ("paralysis", {"condition": "cauda_equina"}, ["G83.4"]),
    ("paralysis", {"condition": "spondylotic_myelopathy"}, ["M47.12"]),
    # nerve_muscle
    ("nerve_muscle", {"condition": "als"}, ["G12.21"]),
    ("nerve_muscle", {"condition": "mg_exacerbation"}, ["G70.01"]),
    ("nerve_muscle", {"condition": "mg_stable"}, ["G70.00"]),
    ("nerve_muscle", {"condition": "becker"}, ["G71.01"]),
    ("nerve_muscle", {"condition": "cidp"}, ["G61.81"]),
    ("nerve_muscle", {"condition": "polyneuropathy"}, ["G62.9"]),
    # cp_ataxia_brain
    ("cp_ataxia_brain", {"condition": "cp_quadriplegic"}, ["G80.0"]),
    ("cp_ataxia_brain", {"condition": "cp_diplegic"}, ["G80.1"]),
    ("cp_ataxia_brain", {"condition": "friedreich"}, ["G11.11"]),
    ("cp_ataxia_brain", {"condition": "huntington"}, ["G10"]),
    ("cp_ataxia_brain", {"condition": "anoxic_brain"}, ["G93.1"]),
    # asthma_cf
    ("asthma_cf", {"condition": "severe_persistent"}, ["J45.50"]),
    ("asthma_cf", {"condition": "severe_persistent_exac"}, ["J45.51"]),
    ("asthma_cf", {"condition": "moderate_persistent"}, ["J45.40"]),
    ("asthma_cf", {"condition": "cf_pulmonary"}, ["E84.0"]),
    # fibrosis_airway
    ("fibrosis_airway", {"condition": "ipf"}, ["J84.112"]),
    ("fibrosis_airway", {"condition": "pf_unspecified"}, ["J84.10"]),
    ("fibrosis_airway", {"condition": "ssc_lung"}, ["M34.81"]),
    ("fibrosis_airway", {"condition": "trach_vent"}, ["Z93.0", "Z99.11"]),
    ("fibrosis_airway", {"condition": "trach_only"}, ["Z93.0"]),
    # pneumonia_inpatient
    ("pneumonia_inpatient", {"condition": "aspiration"}, ["J69.0"]),
    ("pneumonia_inpatient", {"condition": "mrsa"}, ["J15.212"]),
    ("pneumonia_inpatient", {"condition": "unspecified_organism"}, ["J18.9"]),
    ("pneumonia_inpatient", {"condition": "lung_abscess"}, ["J85.2"]),
    ("pneumonia_inpatient", {"condition": "empyema"}, ["J86.9"]),
    ("pneumonia_inpatient", {"condition": "resp_arrest"}, ["R09.2"]),
    # sepsis_inpatient
    ("sepsis_inpatient", {"condition": "sepsis"}, ["A41.9"]),
    ("sepsis_inpatient", {"condition": "severe_sepsis"}, ["A41.9", "R65.20"]),
    ("sepsis_inpatient", {"condition": "septic_shock"}, ["A41.9", "R65.21"]),
    ("sepsis_inpatient", {"condition": "mssa_sepsis"}, ["A41.01"]),
    ("sepsis_inpatient", {"condition": "urosepsis"}, []),
    ("sepsis_inpatient", {"condition": "bacteremia"}, []),
    # opportunistic
    ("opportunistic", {"condition": "pcp"}, ["B59"]),
    ("opportunistic", {"condition": "candida_esophagitis"}, ["B37.81"]),
    ("opportunistic", {"condition": "oral_thrush"}, ["B37.0"]),
    ("opportunistic", {"condition": "cmv"}, ["B25.9"]),
    # diabetes_acute
    ("diabetes_acute", {"condition": "t2_dka"}, ["E11.10"]),
    ("diabetes_acute", {"condition": "t1_dka"}, ["E10.10"]),
    ("diabetes_acute", {"condition": "t2_hhs"}, ["E11.00"]),
    ("diabetes_acute", {"condition": "t2_hypo_coma"}, ["E11.641"]),
    ("diabetes_acute", {"condition": "t2_hyperglycemia"}, ["E11.65"]),
    # transplant_status
    ("transplant_status", {"condition": "heart"}, ["Z94.1"]),
    ("transplant_status", {"condition": "lung"}, ["Z94.2"]),
    ("transplant_status", {"condition": "heart_lung"}, ["Z94.3"]),
    ("transplant_status", {"condition": "liver"}, ["Z94.4"]),
    ("transplant_status", {"condition": "kidney_pancreas"}, ["Z94.0", "Z94.83"]),
    ("transplant_status", {"condition": "intestine"}, ["Z94.82"]),
    ("transplant_status", {"condition": "stem_cell"}, ["Z94.84"]),
    ("transplant_status", {"condition": "liver_rejection"}, ["T86.41"]),
    ("transplant_status", {"condition": "lung_rejection"}, ["T86.810"]),
    # blood_cancers
    ("blood_cancers", {"condition": "myeloma_active"}, ["C90.00"]),
    ("blood_cancers", {"condition": "myeloma_remission"}, ["C90.01"]),
    ("blood_cancers", {"condition": "mds"}, ["D46.9"]),
    ("blood_cancers", {"condition": "nhl_active"}, ["C85.90"]),
    ("blood_cancers", {"condition": "nhl_history"}, ["Z85.72"]),
    ("blood_cancers", {"condition": "hodgkin_active"}, ["C81.90"]),
    # blood_disorders
    ("blood_disorders", {"condition": "hb_sc"}, ["D57.20"]),
    ("blood_disorders", {"condition": "aiha_warm"}, ["D59.11"]),
    ("blood_disorders", {"condition": "pancytopenia_chemo"}, ["D61.810"]),
    ("blood_disorders", {"condition": "pancytopenia_other"}, ["D61.818"]),
    ("blood_disorders", {"condition": "hemophilia_a"}, ["D66"]),
    ("blood_disorders", {"condition": "cyclic_neutropenia"}, ["D70.4"]),
    # liver_failure_biliary
    ("liver_failure_biliary", {"condition": "chronic_liver_failure"}, ["K72.10"]),
    ("liver_failure_biliary", {"condition": "cirrhosis_portal_htn"}, ["K74.60", "K76.6"]),
    ("liver_failure_biliary", {"condition": "pbc"}, ["K74.3"]),
    ("liver_failure_biliary", {"condition": "psc"}, ["K83.01"]),
    ("liver_failure_biliary", {"condition": "bile_obstruction"}, ["K83.1"]),
    # bowel_obstruction
    ("bowel_obstruction", {"condition": "adhesions_partial"}, ["K56.51"]),
    ("bowel_obstruction", {"condition": "adhesions_complete"}, ["K56.52"]),
    ("bowel_obstruction", {"condition": "obstruction_unknown"}, ["K56.600"]),
    ("bowel_obstruction", {"condition": "ileus"}, ["K56.7"]),
    # metabolic_endocrine
    ("metabolic_endocrine", {"condition": "gaucher"}, ["E75.22"]),
    ("metabolic_endocrine", {"condition": "fabry"}, ["E75.21"]),
    ("metabolic_endocrine", {"condition": "attr"}, ["E85.82"]),
    ("metabolic_endocrine", {"condition": "amyloid_unspecified"}, ["E85.9"]),
    ("metabolic_endocrine", {"condition": "addison"}, ["E27.1"]),
    ("metabolic_endocrine", {"condition": "adrenal_unspecified"}, ["E27.40"]),
    ("metabolic_endocrine", {"condition": "acromegaly"}, ["E22.0"]),
    ("metabolic_endocrine", {"condition": "cushing_drug"}, ["E24.2"]),
    # bone_lupus_skin
    ("bone_lupus_skin", {"condition": "osteo_chronic"}, ["M86.671"]),
    ("bone_lupus_skin", {"condition": "osteo_acute"}, ["M86.171"]),
    ("bone_lupus_skin", {"condition": "sle_nephritis"}, ["M32.14"]),
    ("bone_lupus_skin", {"condition": "discoid"}, ["L93.0"]),
    ("bone_lupus_skin", {"condition": "pemphigus"}, ["L10.0"]),
    ("bone_lupus_skin", {"condition": "pemphigoid"}, ["L12.0"]),
    # ulcer_burn
    ("ulcer_burn", {"condition": "ulcer_fat"}, ["L97.412"]),
    ("ulcer_burn", {"condition": "ulcer_bone"}, ["L97.414"]),
    ("ulcer_burn", {"condition": "ulcer_depth_unknown"}, ["L97.419"]),
    ("ulcer_burn", {"condition": "burn_major"}, ["T31.32"]),
    ("ulcer_burn", {"condition": "burn_minor"}, ["T31.10"]),
    # head_injury
    ("head_injury", {"condition": "tbi_loc_long"}, ["S06.2X5A"]),
    ("head_injury", {"condition": "tbi_loc_short"}, ["S06.2X1A"]),
    ("head_injury", {"condition": "tbi_no_loc"}, ["S06.2X0A"]),
    ("head_injury", {"condition": "concussion_loc"}, ["S06.0X1A"]),
    # spine_amputation
    ("spine_amputation", {"condition": "vert_initial"}, ["S32.010A"]),
    ("spine_amputation", {"condition": "vert_followup"}, ["S32.010D"]),
    ("spine_amputation", {"condition": "vert_osteoporotic"}, ["M80.08XA"]),
    ("spine_amputation", {"condition": "amputation_acute"}, ["S88.111A"]),
    ("spine_amputation", {"condition": "amputation_status"}, ["Z89.511"]),
]  # fmt: skip


def codes_for(tables, table_id, slots):
    return [dotted(c) for c in resolve(tables[table_id], slots).codes]


# ---- every real table ----
def test_tables_present(tables):
    assert len(tables) >= 3


def test_full_coverage_no_dead_rules(table):
    cov = coverage_check(table)
    assert cov["gaps"] == []
    assert cov["unreachable"] == []
    assert cov["no_distractor"] == []


def test_no_cpt_like_codes(table):
    assert not [c for c in all_codes(table) if CPT_LIKE.match(c)]


def test_distractors_differ_and_are_tagged(table):
    for s in combos(table):
        a = resolve(table, s)
        for d in a.distractors:
            assert set(d.codes) != set(a.codes)
            assert d.confusion in table["confusions"]


def test_status_is_draft_or_reviewed(table):
    assert table["status"] in {"draft", "reviewed"}


# ---- known answers: one per rule ----
@pytest.mark.parametrize(("table_id", "slots", "expected"), EXPECTED, ids=lambda v: v if isinstance(v, str) else None)
def test_expected_answer(tables, table_id, slots, expected):
    assert codes_for(tables, table_id, slots) == expected


def test_every_rule_has_an_expected_case(tables):
    hit = {
        (tid, comp["id"], match_rule(comp, slots)) for tid, slots, _ in EXPECTED for comp in tables[tid]["components"]
    }
    every = {
        (tid, comp["id"], i) for tid, t in tables.items() for comp in t["components"] for i in range(len(comp["rules"]))
    }
    assert sorted(every - hit) == []


# ---- matching ----
@pytest.mark.parametrize(
    ("when", "slots", "ok"),
    [
        ({}, {"a": "x"}, True),
        ({"a": "x"}, {"a": "x"}, True),
        ({"a": ["x", "y"]}, {"a": "y"}, True),
        ({"a": "x"}, {"a": "y"}, False),
        ({"a": "x"}, {}, False),
    ],
)
def test_matches(when, slots, ok):
    assert matches(when, slots) is ok


def test_match_rule_first_wins_and_none(tiny_data):
    comp = make_table(tiny_data)["components"][1]
    assert match_rule(comp, {"b": "2"}) == 0
    assert match_rule(comp, {"b": "1"}) == 1
    assert match_rule({"rules": [{"when": {"b": "9"}}]}, {"b": "1"}) is None


# ---- building / validation ----
def test_make_table_fills_defaults_without_mutating(tiny_data):
    del tiny_data["exclude"]
    t = make_table(tiny_data, "src.json")
    assert t["exclude"] == [] and t["title"] == "tiny" and t["source"] == "src.json"
    assert "exclude" not in tiny_data


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: d["slots"]["b"].update(values=[]), "has no values"),
        (lambda d: d["slots"]["a"]["evidence"].update(z=["?"]), "undeclared value z"),
        (lambda d: d["confusions"]["mixed_up"].update(lean="sideways"), "lean must be"),
        (lambda d: d["components"].append({"id": "main", "rules": []}), "duplicate component"),
        (lambda d: d["components"][0]["rules"][0]["when"].update(q="x"), "unknown slot q"),
        (lambda d: d["components"][0]["rules"][0]["when"].update(a="z"), "a=z is not a declared value"),
        (lambda d: d["components"][0]["rules"][0]["wrong"][0].update(confusion="nope"), "unknown confusion"),
        (lambda d: d["exclude"].append({"q": "1"}), "exclude uses unknown slot"),
        (lambda d: d.update(note_rules=[{"when": {"q": "1"}}]), "note_rules[0] uses unknown slot"),
    ],
    ids=["no_values", "evidence_value", "lean", "dup_component", "when_slot", "when_value", "confusion",
         "exclude_slot", "note_rules_slot"],
)  # fmt: skip
def test_validate_rejects(tiny_data, mutate, message):
    mutate(tiny_data)
    with pytest.raises(TableError, match=re.escape(message)):
        make_table(tiny_data)


def test_validate_returns_table(tiny_data):
    t = make_table(tiny_data)
    assert validate(t) is t


def test_unknown_slot_value_rejected():
    bad = {
        "id": "x",
        "slots": {"a": {"values": ["1"]}},
        "confusions": {},
        "components": [{"id": "c", "rules": [{"when": {"a": "2"}, "codes": []}]}],
    }
    with pytest.raises(TableError):
        make_table(bad)


# ---- combinations and code sets ----
def test_combos_skip_excluded(tiny_data):
    t = make_table(tiny_data)
    assert list(combos(t)) == [{"a": "x", "b": "1"}, {"a": "x", "b": "2"}, {"a": "y", "b": "1"}]
    assert is_excluded(t, {"a": "y", "b": "2"})
    assert not is_excluded(t, {"a": "x", "b": "2"})


def test_code_sets(tiny_data):
    t = make_table(tiny_data)
    assert correct_codes(t) == {"A000", "A001", "Z0000"}
    assert all_codes(t) == {"A000", "A001", "Z0000"}


# ---- resolution ----
def test_resolve_tiny(tiny_data):
    a = resolve(make_table(tiny_data), {"a": "x", "b": "2"})
    assert a.codes == ("A000", "Z0000")
    assert a.explanations == ["x -> A00.0"] and a.refs == ["R1"]
    assert [(d.codes, d.confusion, d.component) for d in a.distractors] == [(("A001", "Z0000"), "mixed_up", "main")]


def test_resolve_dedupes_refs(tiny_data):
    assert resolve(make_table(tiny_data), {"a": "y", "b": "1"}).refs == ["R1", "R2"]


@pytest.mark.parametrize(
    ("slots", "message"),
    [
        ({"a": "x"}, "missing slots"),
        ({"a": "z", "b": "1"}, "invalid slot a=z"),
        ({"a": "x", "b": "1", "c": "1"}, "invalid slot c=1"),
        ({"a": "y", "b": "2"}, "excluded"),
    ],
)
def test_resolve_rejects(tiny_data, slots, message):
    with pytest.raises(TableError, match=message):
        resolve(make_table(tiny_data), slots)


def test_resolve_no_matching_rule(tiny_data):
    tiny_data["components"][1]["rules"].pop()  # remove the catch-all
    with pytest.raises(TableError, match="no rule in component extra"):
        resolve(make_table(tiny_data), {"a": "x", "b": "1"})


def test_excluded_combo_rejected(tables):
    with pytest.raises(TableError):
        resolve(tables["ckd_staging"], {"stage": "2", "hypertension": "no", "dialysis": "yes"})


def test_answer_to_dict_uses_dotted_codes(tiny_data):
    d = answer_to_dict(resolve(make_table(tiny_data), {"a": "x", "b": "2"}))
    assert d["codes"] == ["A00.0", "Z00.00"]
    assert d["distractors"][0] == {"codes": ["A00.1", "Z00.00"], "confusion": "mixed_up", "why": "that is y"}
    json.dumps(d)


# ---- loading ----
def test_load_table_and_tables(tmp_path, tiny_data):
    (tmp_path / "tiny.json").write_text(json.dumps(tiny_data), encoding="utf-8")
    (tmp_path / "schema.json").write_text("{}", encoding="utf-8")
    assert load_table(tmp_path / "tiny.json")["id"] == "tiny"
    assert list(load_tables(tmp_path)) == ["tiny"]


def test_load_tables_duplicate_id(tmp_path, tiny_data):
    for name in ("a.json", "b.json"):
        (tmp_path / name).write_text(json.dumps(tiny_data), encoding="utf-8")
    with pytest.raises(TableError, match="duplicate table id"):
        load_tables(tmp_path)


def test_load_tables_empty_dir(tmp_path):
    assert load_tables(tmp_path) == {}


# ---- checks and reports ----
def test_coverage_check_finds_gaps_and_dead_rules(tiny_data):
    tiny_data["components"][1]["rules"] = [{"when": {"b": "2"}, "codes": []}, {"when": {"b": "2"}, "codes": []}]
    cov = coverage_check(make_table(tiny_data))
    assert cov["combos"] == 3
    assert ("extra", {"a": "x", "b": "1"}) in cov["gaps"]
    assert cov["unreachable"] == [("extra", 1)]
    assert cov["no_distractor"] == []  # not computed when there are gaps


def test_table_report_without_db(tiny_data):
    ok, lines = table_report(make_table(tiny_data), None)
    assert ok and lines[0].startswith("[OK] tiny")


def test_resolve_report_without_db(tiny_data):
    text = resolve_report(make_table(tiny_data), {"a": "x", "b": "1"}, None)
    assert json.loads(text)["codes"] == ["A00.0"]


def test_main_checks_every_table(capsys):
    assert main([]) == 0
    assert "[OK] diabetes_complications" in capsys.readouterr().out


def test_main_resolves_one_case(capsys):
    assert main(["ckd_staging", "stage=4", "hypertension=no", "dialysis=no"]) == 0
    assert '"N18.4"' in capsys.readouterr().out


# ---- against the CMS files ----
def test_codes_valid_in_current_fy(db, table):
    assert code_check(table, db) == []


def test_code_check_reports_problems(db, tiny_data):
    tiny_data["components"][0]["rules"][0]["codes"] = ["E11"]  # category: exists, not billable
    tiny_data["components"][0]["rules"][1]["codes"] = ["Q99.99"]  # does not exist
    problems = code_check(make_table(tiny_data), db)
    assert "E11 is used as a correct answer but is not billable" in problems
    assert "Q99.99 does not exist in the code set" in problems
