PRIVACY_POLICY = "1.0"
ANALYSIS_SCHEMAS = frozenset(f"{kind}/1.0" for kind in (
    "themes", "trends", "issues", "evidence", "recommendations", "manager-report", "team-summary"))
RESTRICTED_SCHEMAS = ANALYSIS_SCHEMAS | {"feedback/1.0"}
