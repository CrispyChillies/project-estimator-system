USER_ROLES = ("pm", "engineer", "admin")
PROJECT_STATUS = ("draft", "quoted", "won", "lost", "delivered")
DATA_SOURCE = ("user", "dataset", "synthetic")
ESTIMATE_STATUS = ("draft", "final")
ESTIMATE_SOURCE = ("ai", "manual", "clone")
CONFIDENCE = ("low", "medium", "high")
ORIGIN = ("ai", "user", "agent")
ASSUMPTION_KIND = ("assumption", "risk", "out_of_scope")
QUESTION_STATUS = ("open", "asked", "answered", "dismissed")
ACTOR = ("user", "agent", "system")
EVENT_TYPES = (
    "task_added", "task_removed", "task_restored", "hours_changed", "role_changed",
    "category_changed", "title_changed", "task_toggled", "module_added", "module_removed",
    "task_moved", "estimate_finalized", "proposal_op_rejected",
)
REASON_TAGS = (
    "underestimated_complexity", "overestimated", "reuse_existing_code", "client_specific",
    "scope_added", "scope_removed", "risk_buffer", "other",
)
PROPOSAL_STATUS = ("pending", "accepted", "rejected", "partial")
AGENT_MODE = ("generate", "chat")
ACTUAL_SOURCE = ("manual", "csv", "dataset")
LAYER = ("edit", "actual")
SCOPE_TYPE = ("global", "category", "category_author", "project")
RUN_TRIGGER = ("estimate_finalized", "project_delivered", "manual", "backtest", "seed")
RULE_STATUS = ("proposed", "active", "disabled")
JOB_STATUS = ("queued", "running", "done", "failed")
BACKTEST_LEVEL = ("task", "project")
