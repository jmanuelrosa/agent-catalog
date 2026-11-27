---
work-id: <work-id>
id: rfc
status: draft
imported-from: <SRC-nn when brought in by lets-work; omit otherwise>
next: <the skill to run next; kept in frontmatter so the body stays publishable>
---

# [Team] Subject (EPIC-KEY)

<!--
When the project or the team has its own RFC template, follow its outline instead; this one is the default.
Prefix the title with [WIP] while it is a draft.
Read to-rfc/references/rfc-writing.md before filling it, and delete every italic guidance line and this comment before sharing.
-->

## 1 Executive Summary

*Five to ten lines. A reader who stops here knows what we build and what we need from them.*

- **What:** *one or two sentences.*
- **Scope:** *the stories or tickets covered, linked.*
- **Non-goals:** *what this RFC does not cover, and where it lives instead.*
- **Release:** *one line (feature flag, order), unless reviewers must agree on something about it, in which case it gets a 3.x subsection.*
- **Needs from reviewers:** *the number of technical questions in section 8, or sign-off when none is open.*
- **Links:** *epic, PRD, design, related RFCs.*

## 2 Motivation

*Half a page at most.*

*Current state in two or three lines, then its limitations as a numbered list, then why now.*

1. *Limitation one.*
2. *Limitation two.*

## 3 Proposed Implementation

*Most of the document, and only the solution we propose: the options we weighed go to section 6.*

*Open with a small diagram when the flow spans systems. Prefer a top-down flowchart with one subgraph per owner, and a sequence diagram for steps over time, to one long left-to-right chain.*

*One subsection per decision or component that changes in the system, not per screen. Each opens with a bold one-line verdict, then the reasoning in a few lines.*

### 3.1 *Decision or component*

**Verdict:** *we do X.*

*Why, in three to six lines.*

### 3.2 *Decision or component*

**Verdict:** *...*

## 4 Metrics & Dashboards

*What we measure to know it works, and which new alerts fire when it does not. Check what already exists, and list only what is new. Include storage growth for new tables or columns.*

## 5 Drawbacks

*Three to six bullets: costs and risks of the chosen design that we accept, one line each, with the mitigation when there is one. A constraint to keep in mind (an order of work, a dependency) is not a drawback: it goes in section 7.*

## 6 Alternatives

*Grouped under the section 3 subsection they belong to. For each one, say how it would work, then why we don't do it. No "Rejected:" label. Only options weighed for a current verdict: a design an earlier draft had and a later decision replaced is deleted, not moved here.*

**3.1 *Decision or component*.**

- *Alternative.* *How it would work. Why we don't do it.*

## 7 Potential Impact and Dependencies

*Other teams, repos, epics and open PRs this touches, and the order between them.*

| Area | Impact | Dependency or risk |
|---|---|---|
| *repo / team / epic* | | |

## 8 Unresolved questions

*Only technical questions that are really open: architecture, data, infrastructure, rollout. Everything with a clear winner is a verdict in section 3. Write "None open." when nothing is.*

*Each item: a bold question, the owner, two or three lines of context citing its source, the options one line each, and our recommendation. Ten lines at most.*

*When an item is answered, keep it here with "Answered (date):" and the answer, or move the outcome into section 3.*

**Q1. *Question?***
*Owner: ...*
*Context.*

1. *Option.*
2. *Option.*

**Our recommendation:** *option and one-line reason.*

## 9 Security considerations

*Two to five plain bullets: new inputs, permissions, tenant isolation, personal data, abuse. Each says what we do, in words a non-engineer can follow. Data built from input anyone can send (request headers) stays inert until a user acts on it.*

## 10 Conclusion

*Two to four sentences: why this is the right design now, and the main risk we accept.*

## Decision log

*The publishable summary of decisions agreed in a meeting or a comment thread, so the outcome survives once comments are resolved. One row each; the full question, answer and reason live in rfc.log.md. Mark our own proposals as such. When a later decision reverses a row, replace that row.*

| Date | Decision | Where | Section |
|---|---|---|---|
| | | *technical refinement, Slack thread, review comment, "proposal, after a review comment"* | |
