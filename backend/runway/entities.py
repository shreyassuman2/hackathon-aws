"""Entity names, used as the sort-key prefix in the store. Keep this list in one place."""

COMPANY = "company"
EMPLOYEE = "employee"
TRANSACTION = "transaction"
SEAT = "seat"  # per-employee tool usage signals
AI_USAGE = "ai_usage"  # weekly model usage rows per vendor
RENEWAL = "renewal"  # subscription contracts + renewal dates
OVERLAP = "overlap"  # tools that do the same job
PLAN_OPT = "plan_opt"  # tier downgrade opportunities
FEATURE_WASTE = "feature_waste"
SHADOW_IT = "shadow_it"
SAVINGS = "savings"

ALERT = "alert"  # everything Runway tells (or holds back from) the founder
RESTRAINT = "restraint"  # why an alert was sent now vs. held for the digest
POLICY = "policy"
POLICY_ACTION = "policy_action"  # audit log of autonomous actions

NEGOTIATION = "negotiation"  # live negotiation state (one record per deal)
NEGOTIATION_HISTORY = "negotiation_history"  # past outcomes, used as tone/leverage reference

EMPLOYEE_THREAD = "employee_thread"
MESSAGE = "message"  # iMessage history (short-term memory)
