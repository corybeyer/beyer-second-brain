# Systems Check

Review the code changes or specified files against the System Behavior patterns defined in CLAUDE.md.

## Review Checklist

For each piece of code, evaluate:

### 1. Error Handling
- [ ] Are all failure modes from the Failure Modes table handled?
- [ ] Are errors logged with structured context (source_id, step, duration)?
- [ ] Do failures result in appropriate status updates (PARSE_FAILED, EXTRACT_FAILED)?
- [ ] Are error messages stored for debugging?

### 2. Retry Patterns
- [ ] Does the code use exponential backoff for Claude API calls?
- [ ] Does the code respect rate limit headers (Retry-After)?
- [ ] Are SQL connections retried appropriately?
- [ ] Is there a maximum retry limit to prevent infinite loops?

### 3. Idempotency
- [ ] Can the same input be processed multiple times safely?
- [ ] Are upserts used instead of blind inserts where appropriate?
- [ ] Is there a natural key for deduplication?
- [ ] Does reprocessing clean up old data before inserting new?

### 4. Cost Controls
- [ ] Are file size limits enforced before processing?
- [ ] Are chunk size limits enforced before Claude API calls?
- [ ] Is there protection against processing too many items?
- [ ] Are expensive operations (Claude API) rate-limited?

### 5. Transactions & Data Integrity
- [ ] Are related database operations wrapped in transactions?
- [ ] Do transactions roll back on partial failure?
- [ ] Are invariants maintained (FK constraints, required fields)?
- [ ] Is cascade delete configured for parent-child relationships?

### 6. Observability
- [ ] Is logging structured (JSON with consistent fields)?
- [ ] Are durations measured for performance tracking?
- [ ] Are success/failure counts trackable?
- [ ] Can stuck processing be detected?

### 7. Contracts
- [ ] Are input contracts validated (file type, size, format)?
- [ ] Are output contracts documented and consistent?
- [ ] Are external API contracts (Claude) handled defensively?

## Output Format

Provide findings as:

```
## Systems Check Results

### Passed
- [pattern]: [evidence from code]

### Issues Found
- [pattern]: [what's wrong] → [suggested fix]

### Not Applicable
- [pattern]: [why it doesn't apply to this code]
```

Review the recent changes or files the user specifies.
