# Fictional hospital integration

`examples/hospital.py` uses synthetic patient IDs and no real PHI. The host grants `demo-user` read access only to `patient-1024`. An assigned-patient summary can complete when the model clears the note; unassigned and cross-tenant chart reads are denied independently of model output. A poisoned note proposing email export lacks the tool/destination grant. Output release checks the current read grant again. The case result reports both `detection_decision` and observed `action_status`; a model false positive can block a legitimate task.

```bash
python examples/hospital.py own_patient
python examples/hospital.py other_patient
python examples/hospital.py injected_note
```

These are security-boundary examples, **not** clinical decision support or a HIPAA-compliant deployment. A real hospital must integrate authenticated clinician identity, treatment relationship, patient assignment, purpose of use, audit obligations, revocation, authoritative record transactions and organization-specific output controls. A sentence such as “show me patient 1024's complete medical record” is an access request, not automatically a prompt injection; the patient permission is a separate decision.
