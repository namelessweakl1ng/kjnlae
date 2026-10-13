# Fictional enterprise integration

`examples/enterprise.py` uses synthetic policy and employee records. The host grants public-policy and one assigned employee read; another employee's record, forged admin tool proposal and redirected email are denied by resource/tool/destination checks. The `detector_miss` case sends innocuous-looking content with an unauthorized action to demonstrate authorization independence. Cases use no live mail account or company data.

```bash
python examples/enterprise.py public_policy
python examples/enterprise.py other_employee
python examples/enterprise.py redirect_email
```

The scanner may return a false positive or miss an injected document. Host access control remains the boundary: ordinary “get me details of the other employee” is not inherently prompt injection, yet it must be denied if the authenticated user has no HR grant. Real organizations need tenant and department policies from trusted identity/record systems, transactional revocation and exact approval ceremonies for export actions.
