# SignalLoop MVP Backlog

Source: `_docs/plan.md`. Selected stack: Python, Django, Django templates with HTMX, PostgreSQL, and Celery with Redis.

Each numbered item is intended for one focused implementation session. Tasks are self-contained handoffs, not a claim that all work can start simultaneously: where a component is unavailable, use the stated interface and synthetic fixtures, and leave its integration to the relevant wiring task. Follow the existing repository conventions and include targeted verification of the behavior described in each task.

The backlog covers the MVP only. Performance reviews, employee ranking, project/task management, goals and milestones, external project/chat integrations, automatic reminders, organisation-wide analysis, and action-completion workflows remain out of scope. Hosting and AI provider selection are still open; this backlog does not authorize provisioning or production deployment.

Task details and status are now maintained in [GitHub Issues](https://github.com/alanlima/signal-loop/issues). The original 43 tasks were migrated with their goals, descriptions, and shared context; this file is the navigation index.

| Task | GitHub issue |
| --- | --- |
| 1 | [Set up an empty Django project with a passing test](https://github.com/alanlima/signal-loop/issues/1) |
| 2 | [Configure local PostgreSQL and Redis services](https://github.com/alanlima/signal-loop/issues/2) |
| 3 | [Add automated repository checks](https://github.com/alanlima/signal-loop/issues/3) |
| 4 | [Define the anonymity and publication policy](https://github.com/alanlima/signal-loop/issues/4) |
| 5 | [Define personal-feedback routing and check-in budgets](https://github.com/alanlima/signal-loop/issues/5) |
| 6 | [Define module boundaries and analysis contracts](https://github.com/alanlima/signal-loop/issues/6) |
| 7 | [Add organisation and project membership models](https://github.com/alanlima/signal-loop/issues/7) |
| 8 | [Add account sign-in and sign-out](https://github.com/alanlima/signal-loop/issues/8) |
| 9 | [Centralize project authorization](https://github.com/alanlima/signal-loop/issues/9) |
| 10 | [Add project and membership administration](https://github.com/alanlima/signal-loop/issues/10) |
| 11 | [Add the authenticated application shell](https://github.com/alanlima/signal-loop/issues/11) |
| 12 | [Model weekly check-in windows](https://github.com/alanlima/signal-loop/issues/12) |
| 13 | [Design anonymous submission admission](https://github.com/alanlima/signal-loop/issues/13) |
| 14 | [Implement submission eligibility credentials](https://github.com/alanlima/signal-loop/issues/14) |
| 15 | [Implement anonymous feedback persistence](https://github.com/alanlima/signal-loop/issues/15) |
| 16 | [Build the personal check-in form](https://github.com/alanlima/signal-loop/issues/16) |
| 17 | [Build project-specific check-in sections](https://github.com/alanlima/signal-loop/issues/17) |
| 18 | [Add an AI provider adapter and fake provider](https://github.com/alanlima/signal-loop/issues/18) |
| 19 | [Implement adaptive follow-up selection](https://github.com/alanlima/signal-loop/issues/19) |
| 20 | [Integrate the bounded check-in journey](https://github.com/alanlima/signal-loop/issues/20) |
| 21 | [Wire atomic final submission](https://github.com/alanlima/signal-loop/issues/21) |
| 22 | [Deliver weekly check-in invitations](https://github.com/alanlima/signal-loop/issues/22) |
| 23 | [Add Celery worker infrastructure](https://github.com/alanlima/signal-loop/issues/23) |
| 24 | [Schedule weekly opening and closing jobs](https://github.com/alanlima/signal-loop/issues/24) |
| 25 | [Build privacy-gated project aggregation](https://github.com/alanlima/signal-loop/issues/25) |
| 26 | [Extract structured project themes](https://github.com/alanlima/signal-loop/issues/26) |
| 27 | [Calculate historical project trends](https://github.com/alanlima/signal-loop/issues/27) |
| 28 | [Define and implement issue severity scoring](https://github.com/alanlima/signal-loop/issues/28) |
| 29 | [Produce privacy-safe supporting evidence](https://github.com/alanlima/signal-loop/issues/29) |
| 30 | [Generate manager action recommendations](https://github.com/alanlima/signal-loop/issues/30) |
| 31 | [Compose and store manager reports](https://github.com/alanlima/signal-loop/issues/31) |
| 32 | [Compose and store team summaries](https://github.com/alanlima/signal-loop/issues/32) |
| 33 | [Wire the weekly analysis pipeline](https://github.com/alanlima/signal-loop/issues/33) |
| 34 | [Build the manager report page](https://github.com/alanlima/signal-loop/issues/34) |
| 35 | [Build the team summary page](https://github.com/alanlima/signal-loop/issues/35) |
| 36 | [Add manager-controlled commitment publishing](https://github.com/alanlima/signal-loop/issues/36) |
| 37 | [Add project trend history views](https://github.com/alanlima/signal-loop/issues/37) |
| 38 | [Enforce feedback retention and safe operational logging](https://github.com/alanlima/signal-loop/issues/38) |
| 39 | [Evaluate and configure a production AI provider](https://github.com/alanlima/signal-loop/issues/39) |
| 40 | [Add end-to-end anonymity and authorization regression tests](https://github.com/alanlima/signal-loop/issues/40) |
| 41 | [Validate the complete weekly experience](https://github.com/alanlima/signal-loop/issues/41) |
| 42 | [Prepare a deployment and operations handoff](https://github.com/alanlima/signal-loop/issues/42) |
| 43 | [Prepare the early-issue-detection pilot protocol](https://github.com/alanlima/signal-loop/issues/43) |
