"""Shared task template library.

Used by (a) the synthetic dataset generator and (b) the offline `fake` LLM, so that offline demos
produce analog matches. It is NOT used by the live LLM path.
"""

from __future__ import annotations

import hashlib
import re

# category -> default role, base hours (what a "raw LLM" would say for a typical task), keywords
CATEGORY_INFO: dict[str, dict] = {
    "auth": {"role": "Backend", "base": 16, "kw": ["login", "auth", "sso", "password", "oauth", "sign", "role", "permission"]},
    "crud_admin": {"role": "Backend", "base": 14, "kw": ["admin", "crud", "manage", "list", "edit", "catalog", "back office", "backoffice"]},
    "ui_frontend": {"role": "Frontend", "base": 20, "kw": ["page", "screen", "ui", "dashboard", "responsive", "frontend", "web app", "landing"]},
    "api_backend": {"role": "Backend", "base": 18, "kw": ["api", "endpoint", "backend", "service", "rest", "graphql", "booking", "search"]},
    "integration_3rd_party": {"role": "Backend", "base": 20, "kw": ["integrat", "third-party", "third party", "sync", "erp", "crm", "salesforce", "hubspot", "maps", "webhook"]},
    "payments": {"role": "Backend", "base": 24, "kw": ["payment", "stripe", "checkout", "invoice", "billing", "subscription", "paypal"]},
    "data_migration": {"role": "Data Engineer", "base": 24, "kw": ["migrat", "import", "legacy", "etl", "spreadsheet", "excel"]},
    "reporting_analytics": {"role": "Data Engineer", "base": 20, "kw": ["report", "analytics", "chart", "kpi", "export", "statistics", "metrics"]},
    "notifications": {"role": "Backend", "base": 10, "kw": ["notif", "email", "sms", "push", "remind", "alert"]},
    "ml_cv": {"role": "ML/CV Engineer", "base": 40, "kw": ["ml", "machine learning", "model", "recognition", "vision", "ocr", "recommend", "predict", "ai "]},
    "infra_devops": {"role": "DevOps", "base": 16, "kw": ["deploy", "ci/cd", "infrastructure", "cloud", "aws", "docker", "hosting", "environment"]},
    "testing_qa": {"role": "QA", "base": 24, "kw": ["test", "qa", "regression", "quality"]},
    "design_ux": {"role": "Designer", "base": 24, "kw": ["design", "ux", "wireframe", "mockup", "prototype", "branding"]},
    "pm_overhead": {"role": "PM", "base": 30, "kw": ["meeting", "project management", "communication", "planning", "workshop"]},
    "security_compliance": {"role": "Backend", "base": 16, "kw": ["gdpr", "security", "compliance", "audit", "encrypt", "hipaa", "pci"]},
    "other": {"role": "Backend", "base": 12, "kw": []},
}

CATEGORY_NAMES: dict[str, tuple[str, str]] = {
    "auth": ("Authentication & access", "Sign-up, login, SSO, roles and permissions"),
    "crud_admin": ("CRUD / admin", "Back-office screens and simple data management"),
    "ui_frontend": ("UI / frontend", "User-facing screens and client-side logic"),
    "api_backend": ("API / backend", "Server-side business logic and APIs"),
    "integration_3rd_party": ("3rd-party integration", "Integrations with external APIs and systems"),
    "payments": ("Payments", "Payment flows, billing, invoices"),
    "data_migration": ("Data migration", "Importing and transforming legacy data"),
    "reporting_analytics": ("Reporting & analytics", "Reports, dashboards and exports"),
    "notifications": ("Notifications", "Email, SMS and push notifications"),
    "ml_cv": ("ML / computer vision", "Machine-learning and CV features"),
    "infra_devops": ("Infra / DevOps", "CI/CD, environments, hosting"),
    "testing_qa": ("Testing / QA", "Test plans, regression, automation"),
    "design_ux": ("Design / UX", "Wireframes, UI design, prototypes"),
    "pm_overhead": ("PM overhead", "Project management and communication"),
    "security_compliance": ("Security & compliance", "Security hardening, GDPR, audits"),
    "other": ("Other", "Anything that does not fit elsewhere"),
}

# (title, description, hours multiplier vs. category base)
TEMPLATES: dict[str, list[tuple[str, str, float]]] = {
    "auth": [
        ("Email/password sign-up and login", "Registration, login, password reset with email verification.", 1.0),
        ("Single sign-on (SSO) via OAuth/SAML", "Enterprise SSO login using the client's identity provider.", 1.5),
        ("Roles and permissions", "Role-based access control for admin, manager and user roles.", 1.0),
    ],
    "crud_admin": [
        ("Admin panel for users", "Back-office list, search, create/edit/deactivate users.", 1.0),
        ("Catalog management admin", "Admin CRUD for products/items with categories and images.", 1.2),
        ("Content management screens", "Admin editing of static pages, FAQs and banners.", 0.8),
    ],
    "ui_frontend": [
        ("Responsive landing and marketing pages", "Public pages with responsive layout and SEO basics.", 0.8),
        ("User dashboard UI", "Main dashboard with widgets, filters and empty states.", 1.2),
        ("Search and listing UI", "Search results page with filters, sorting and pagination.", 1.0),
        ("Mobile app screens", "Native/cross-platform screens for core user flows.", 1.6),
    ],
    "api_backend": [
        ("Core domain API", "REST endpoints for the main business entities and validation.", 1.2),
        ("Booking/scheduling logic", "Availability rules, reservations and conflict handling.", 1.3),
        ("Search backend", "Full-text search and filtering on the backend.", 0.9),
    ],
    "integration_3rd_party": [
        ("CRM integration", "Two-way sync of contacts and deals with the client's CRM.", 1.2),
        ("ERP integration", "Export orders and import stock levels from the ERP system.", 1.4),
        ("Maps and geolocation integration", "Map display, geocoding and distance calculations.", 0.8),
        ("Webhook integration with partner API", "Receive and process partner webhooks with retries.", 0.8),
    ],
    "payments": [
        ("Stripe checkout and payments", "Card payments with Stripe including refunds and webhooks.", 1.0),
        ("Subscriptions and invoicing", "Recurring billing plans and PDF invoices.", 1.3),
    ],
    "data_migration": [
        ("Legacy data migration", "Import and clean data from the legacy database.", 1.2),
        ("Spreadsheet import", "Bulk import of records from Excel/CSV files with validation.", 0.6),
    ],
    "reporting_analytics": [
        ("KPI reporting dashboard", "Charts and KPIs for managers with date filters.", 1.0),
        ("CSV/Excel exports", "Export of lists and reports to CSV/Excel.", 0.5),
    ],
    "notifications": [
        ("Email notifications", "Transactional emails with templates.", 1.0),
        ("Push notifications", "Mobile push notifications for key events.", 1.2),
        ("SMS reminders", "SMS reminders via an SMS gateway.", 0.8),
    ],
    "ml_cv": [
        ("Image recognition model", "Train/integrate a CV model to classify uploaded images.", 1.2),
        ("Recommendation engine", "Personalized recommendations based on user behavior.", 1.0),
        ("Document OCR extraction", "Extract fields from scanned documents with OCR.", 0.9),
    ],
    "infra_devops": [
        ("CI/CD pipeline", "Automated build, test and deploy pipeline.", 1.0),
        ("Environments setup (dev/staging/prod)", "Cloud environments, secrets, monitoring.", 1.2),
    ],
    "testing_qa": [
        ("QA and regression testing", "Test plan, manual regression and bug verification.", 1.0),
        ("Automated end-to-end tests", "E2E test suite for critical flows.", 0.8),
    ],
    "design_ux": [
        ("UX wireframes", "Wireframes for main flows and stakeholder review.", 0.8),
        ("UI design system and mockups", "High-fidelity mockups and component styles.", 1.2),
    ],
    "pm_overhead": [
        ("Project management and communication", "Planning, meetings, status reports, client communication.", 1.0),
        ("Code review", "Peer code review across the team.", 0.6),
    ],
    "security_compliance": [
        ("GDPR compliance features", "Consent, data export and deletion requests.", 1.0),
        ("Security hardening", "OWASP review, rate limiting, audit logging.", 0.9),
    ],
    "other": [("Miscellaneous tasks", "Small tasks not covered elsewhere.", 1.0)],
}

HIDDEN_TASKS = [
    ("infra_devops", 0), ("infra_devops", 1), ("testing_qa", 0), ("pm_overhead", 1), ("pm_overhead", 0),
]


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9/]+", text.lower())


def classify(text: str) -> str:
    t = " " + text.lower() + " "
    best, score = "other", 0
    for cat, info in CATEGORY_INFO.items():
        s = sum(1 for k in info["kw"] if k in t)
        if s > score:
            best, score = cat, s
    return best


def pick_template(category: str, text: str) -> int:
    words = set(tokens(text))
    best, score = 0, -1
    for i, (title, desc, _) in enumerate(TEMPLATES[category]):
        s = len(words & set(tokens(title + " " + desc)))
        if s > score:
            best, score = i, s
    return best


def stable_unit(*parts: object) -> float:
    """Deterministic pseudo-random number in [0, 1)."""
    h = hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()
    return int(h[:12], 16) / float(16**12)
