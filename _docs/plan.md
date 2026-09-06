# SignalLoop — MVP Scope

## Product Goal

Build **SignalLoop**, a weekly, anonymous, AI-assisted feedback tool for multi-project teams that helps managers detect important issues earlier.

### Product statement

> **A 5-minute weekly feedback loop that turns anonymous team signals into early warnings and actionable manager insights.**

---

## Core Product Decisions

### 1. Feedback direction
**Decision:** Two-way feedback.

The product should support feedback flowing in both directions:
- Contributors / team members provide feedback about project delivery, collaboration, workload, blockers, and support needs.
- Managers use the aggregated insights to act on issues and improve the team/project environment.

---

### 2. Feedback focus
**Decision:** Project delivery and people/performance equally.

Weekly feedback should cover:
- Project progress and delivery health
- Blockers and risks
- Collaboration
- Workload
- Wins and challenges
- Support needed
- Team dynamics

The tool should not become a formal performance-review platform.

---

### 3. Weekly feedback experience
**Decision:** Combination of structured input and adaptive AI follow-ups.

The weekly flow should:
1. Start with a lightweight structured check-in.
2. Use AI to ask follow-up questions where useful.
3. Produce an AI-generated project/team summary.

The AI should only dig deeper when an answer indicates something worth exploring.

---

### 4. Anonymity
**Decision:** Anonymous by default and by design.

Feedback should be anonymous.

### Hard product rule
The product must prevent managers and application administrators from accessing raw feedback or linking published feedback to contributors through product-provided identifiers, joins or unsafe content. Publication fails closed under the mandatory [MVP anonymity policy](anonymity-policy.md).

This is a product-enforced access and publication requirement, not a guarantee against arbitrary prior knowledge, collusion or privileged infrastructure access. The policy defines those limits, fixed thresholds, content rules and release blockers; meeting a threshold or removing a name alone does not prove anonymity.

This is not a configurable setting in the MVP.

---

### 5. Summary audiences
**Decision:** Different views for team and manager.

#### Team view
Should contain:
- Major themes
- Wins
- Blockers
- Shared concerns
- Next-week focus
- Published team commitments

#### Manager view
Should contain deeper analysis:
- Important risks
- Recurring concerns
- Severity
- Anonymous supporting evidence
- Trends over time
- Recommended actions

---

### 6. AI action recommendations
**Decision:** AI should suggest concrete manager actions.

When the AI detects a meaningful issue, it should do more than summarize it.

It should:
- Explain why the issue matters
- Recommend concrete actions for the manager
- Suggest which actions could become visible team commitments

The manager remains in control of what gets published.

---

### 7. Team commitments
**Decision:** AI suggests which manager actions should become team commitments.

The AI can recommend that selected actions be shared with the team.

Managers decide whether to publish them.

---

### 8. Primary organisational unit
**Decision:** Project-first model with people belonging to multiple projects.

The system should organise feedback primarily around **projects**.

A person may belong to multiple projects simultaneously.

---

### 9. Multi-project weekly check-in
**Decision:** Hybrid model.

Each person completes:
- One lightweight personal weekly check-in
- Project-specific sections for each project they participate in

The AI then aggregates feedback anonymously by project.

The [MVP check-in policy](check-in-policy.md) fixes the questions, project-selection and follow-up budgets, and timing behavior. Personal reflection stays in the transient draft; only separately answered project fields can contribute to project aggregates.

---

### 10. Check-in duration
**Decision:** Adaptive flow.

Target:
- **Ideal completion time:** ~5 minutes
- **Maximum completion time:** 10 minutes

The AI should only ask follow-up questions when needed.

The flow should avoid turning into a long survey.

---

### 11. Personal check-in content
**Decision:** Lightweight coverage of all key areas.

The personal check-in should include:
- Mood / energy
- Workload
- Wins
- Challenges
- Support needed from manager/team

The AI decides where additional follow-up is useful.

---

### 12. Trends over time
**Decision:** Trend tracking is a core feature.

The system should track project-level trends such as:
- Sentiment
- Workload
- Blockers
- Recurring themes
- Collaboration concerns
- Risk patterns
- Whether previous actions improved the situation

Trend analysis should help distinguish a one-off complaint from a developing issue.

---

### 13. Project goals and milestones
**Decision:** Later feature, not MVP.

The MVP should not deeply integrate project goals or milestones.

This may be added later to connect feedback with delivery objectives.

---

## MVP Success Metric

### Primary outcome

The MVP succeeds if it helps managers:

> **Identify important project or team issues earlier than they otherwise would.**

This is the primary success metric.

Other benefits such as higher participation, better feedback quality, or psychological safety are valuable but secondary for the MVP.

---

## Important Issue Detection

The AI should be capable of detecting multiple types of important issues.

### Categories

#### Delivery risk
Examples:
- Persistent blockers
- Dependency problems
- Delivery confidence dropping
- Unclear ownership
- Repeated delays

#### Workload / burnout risk
Examples:
- Unsustainable workload
- Repeated overtime
- High stress
- Lack of capacity
- Multiple weeks of declining energy

#### Team conflict / collaboration
Examples:
- Communication breakdown
- Lack of trust
- Conflict
- Poor coordination
- Cross-team friction

#### Recurring negative themes
Examples:
- The same complaint appearing across multiple weeks
- Multiple people raising similar concerns
- A previously resolved issue returning

---

## Severity Scoring

**Decision:** All important issue categories should support severity scoring.

The AI should evaluate issues based on factors such as:
- Frequency
- Number of supporting signals
- Trend direction
- Persistence
- Potential impact
- Urgency

Example levels may eventually be:

- Low
- Moderate
- High
- Critical

Exact scoring rules should be defined during product/design implementation.

---

## Manager Evidence View

**Decision:** Managers should see context and evidence, not just an AI conclusion.

For each important issue, the manager view should show:

- Issue / theme
- Severity
- Explanation of why it matters
- Trend/history
- Anonymous supporting evidence
- Privacy-reviewed paraphrases or labelled, grounded synthesised examples where permitted by the anonymity policy; no verbatim feedback quotes
- Recommended manager actions

The system should **not expose the identity of the contributor**.

---

## Weekly User Journey

### Team member

1. Receives weekly check-in.
2. Starts with personal lightweight questions.
3. Completes a small section for each active project.
4. AI asks limited follow-up questions where useful.
5. Completes the entire process in ~5 minutes, with a hard cap of 10 minutes.
6. Feedback is stored anonymously for aggregation.

### AI processing

1. Aggregate anonymous feedback by project.
2. Identify themes.
3. Compare against previous weeks.
4. Detect developing risks.
5. Assign severity.
6. Generate supporting evidence.
7. Recommend manager actions.
8. Suggest which actions may be appropriate as public team commitments.
9. Generate separate team and manager summaries.

### Manager

1. Opens project weekly report.
2. Sees overall project/team health.
3. Reviews flagged issues.
4. Reviews severity, trends, and anonymous evidence.
5. Reviews recommended actions.
6. Decides which actions to take.
7. Optionally publishes selected actions as team commitments.

### Team

The team receives a safe, shared summary containing:
- Key themes
- Wins
- Common blockers
- General areas of concern
- Next-week focus
- Manager-published commitments

Sensitive manager-only insights should not appear in this view.

---

## MVP Boundaries

The MVP should stay narrowly focused on:

> **Weekly feedback + anonymous aggregation + early risk detection + actionable manager insights.**

### Explicitly out of scope

#### Performance review system
Do not build:
- Employee ratings
- Formal individual performance scoring
- Promotion recommendations
- Performance review cycles
- Employee ranking

#### Project management system
Do not build:
- Task management
- Kanban boards
- Sprint planning
- Work assignment
- Detailed delivery tracking

The tool may later integrate with project-management platforms, but should not replace them.

#### Employee engagement survey platform
Do not build:
- Large organisation-wide engagement surveys
- Annual employee surveys
- Complex HR benchmarking
- General-purpose survey builders

#### Detailed goal/milestone management
Do not build in MVP:
- OKR management
- Project milestone tracking
- Detailed goal alignment

This may be introduced later as context for feedback.

---

## MVP Feature Set

### Must Have

- Projects
- People can belong to multiple projects
- Weekly personal check-in
- Project-specific feedback sections
- Anonymous feedback
- Structured questions
- Adaptive AI follow-ups
- ~5-minute target completion
- 10-minute maximum
- AI theme extraction
- Important issue detection
- Issue categorisation
- Severity scoring
- Weekly project summary
- Team view
- Manager view
- Anonymous supporting evidence
- Historical trends
- Recommended manager actions
- Suggested team commitments
- Manager-controlled publishing of commitments

### Later / Possible Extensions

- Project milestones and goals
- Jira / Azure DevOps / Linear integration
- Slack / Microsoft Teams integration
- Automatic reminders
- Manager follow-up workflows
- Project health dashboards
- Organisation-wide patterns
- Cross-project risk detection
- Feedback effectiveness measurement
- Action completion tracking
- More advanced sentiment models

---

## Design Principles

### 1. Anonymous means anonymous
The product must earn trust.

Prevent product-enabled identification and withhold outputs with unresolved inference risk, following the [MVP anonymity policy](anonymity-policy.md). Communicate its residual-risk limits before collecting feedback.

### 2. Short enough to become a habit
The product should feel like a weekly check-in rather than a survey.

Target: **5 minutes**.

### 3. AI should reduce work, not create more forms
AI should:
- Ask better follow-ups
- Find patterns
- Summarise
- Highlight risk
- Suggest action

It should not unnecessarily increase the number of questions.

### 4. Action over analytics
The manager should leave the report knowing:

> **What should I pay attention to, and what should I do next?**

### 5. Detect changes, not just sentiment
The real value comes from identifying:
- Something getting worse
- Something repeatedly appearing
- A concern spreading across the team
- An intervention that is or is not working

---

## SignalLoop — One-Sentence MVP Definition

> **An anonymous AI-powered weekly check-in for multi-project teams that takes about five minutes and helps managers detect emerging delivery, workload, and collaboration risks early and turn them into concrete actions.**
