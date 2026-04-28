# Scheduling Engine — Problem & Requirements Document (Translated & Refined)

## For Delivery to AI Agent / Developer

---

## 1. Institutional Context

Columbus is a school institution with High School, Middle School, and Elementary programs. Academic scheduling is currently a **manual, complex, and difficult-to-maintain process**.

This document defines:
- The business problem
- Available data
- Functional and technical requirements

The goal is to enable an AI agent or developer to **design, estimate, and build a scheduling solution**.

---

## 2. Business Problem

The current scheduling process:

- Relies heavily on specific individuals (knowledge is not systematized)
- Is difficult to replicate year-to-year
- Is inflexible to changes (staff, students, constraints)
- Does not allow scenario simulation ("what if..." analysis)
- Does not scale across HS, MS, and ES consistently

### Objective

Build a **configurable scheduling engine** that:

- Reduces manual dependency
- Improves consistency
- Supports multiple academic models
- Enables simulation and rapid iteration

---

## 3. Expected Functional Scope

The solution must:

1. Ingest structured data (students, teachers, courses, rooms, rules)
2. Apply configurable constraints (hard and soft)
3. Generate a **master schedule** (teachers ↔ blocks ↔ rooms)
4. Assign students to sections
5. Allow scenario simulation before finalizing
6. Export outputs compatible with PowerSchool
7. Support manual review and overrides
8. Allow adding new rules dynamically
9. Handle real-world unpredictability (last-minute changes)

---

## 4. Academic Scenarios

## 4.1 High School (Primary Use Case)

### Schedule Structure

- 5 school days: A, B, C, D, E
- 5 blocks per day
- 8 rotating schedules (schemes)
- Each student takes 8 courses
- Each course meets 3 times per week
- Courses may have multiple sections
- Courses may be taught by up to 3 teachers
- 2 semesters / 4 quarters
- Teachers may have prep periods

### Advisory

- Fixed session for all students
- Day E, Block 3 (IMMOVABLE)

### Rotation Example

| Block | Day A | Day B | Day C | Day D | Day E |
|------|------|------|------|------|------|
| 1 | 1 | 6 | 3 | 8 | 5 |
| 2 | 2 | 7 | 4 | 1 | 6 |
| 3 | 3 | 8 | 5 | 2 | Advisory |
| 4 | 4 | 1 | 6 | 3 | 7 |
| 5 | 5 | 2 | 7 | 4 | 8 |

---

## 4.2 Middle School

- Similar A–E structure
- 5 blocks per day
- More fixed schedules (fewer electives)
- Different structure for grades 6 vs 7–8

---
## 4.2 Elementary School

- Simple weekly structure
- 7 blocks per day
- More fixed schedules (no electives)
- Different hours for grades k4 -5
- Tipical elementary school with homeroom teacher
- Fixed classroom for each group (A-F)
- We can look deeper into elementary school once MS and HS are done, not a priority

## 5. Available Data

### 5.1 Real Files

**High School**
- Master schedule
- ~520 students with course assignments
- Teacher list with load and prep periods
- Room assignments
- Student distribution per teacher

**Middle School**
- Similar structure adapted to MS

**Course Demand Data**
- Enrollment per course and grade
- Teacher-course assignments
- Number of sections needed

---

## 5.2 Student Data Structure

Each student includes:

- ID, Name, Grade
- Core courses + elective sections
- E1–E8 elective section codes
- Total scheduled courses
- Conflict count
- Separation codes (students must NOT share classes)
- Grouping codes (students SHOULD share classes)

---

## 5.3 Missing Data (To Be Defined)

- Full course catalog with prerequisites
- Formal teacher qualifications
- Teacher availability schedules
- Structured behavioral/grouping matrix

---

## 6. Constraints

## 6.1 Hard Constraints (MUST NEVER BREAK)

1. No student in two classes at the same time
2. No teacher in two classes at the same time
3. No room used by multiple classes simultaneously
4. Max class size: 25 (26 for AP Research)
5. No teacher with more than 4 consecutive classes
6. Advisory fixed (Day E, Block 3)
7. Lab courses must be in lab rooms
8. Students must avoid restricted teachers
9. Separation codes must be enforced

---

## 6.2 Soft Constraints (OPTIMIZE)

1. Balance class sizes
2. Maximize first-choice electives
3. Enable co-planning for teachers
4. Encourage positive grouping (Together codes)
5. Balance teacher workload
6. Avoid undesirable schedule patterns for teachers

---

## 7. Two-Phase Scheduling Process

### Phase 1 — Master Schedule

- Assign teachers and rooms to time blocks
- Output reviewed by school leadership

### Phase 2 — Student Assignment

- Assign students to sections
- Apply constraints and optimization

---

## 8. Existing Tool

A JavaScript visualization tool exists:
- Displays rotating schedules
- Does NOT optimize scheduling

This tool can remain independent.

---

## 9. PowerSchool Integration

### Phase 1 (Required)
- CSV import/export

### Phase 2 (Optional)
- API integration

---

## 10. Success Metrics

| Metric | Target |
|------|------|
| Fully scheduled students | ≥ 98% |
| Remaining conflicts | < 5% |
| Required course fulfillment | ≥ 98% |
| First-choice electives | ≥ 80% |
| Section balance deviation | ≤ 3 students |
| Time reduction vs manual | ≥ 90% |

---

## 11. Recommended Technical Stack

### Core

- Language: Java (or Python alternative acceptable)
- Optimization: Google OR-Tools (preferred)
- Excel processing: Apache POI
- Backend: Spring Boot (optional)
- Database: PostgreSQL
- Export: CSV

---

## 12. Implementation Clarifications

- PowerSchool access: API + CSV
- Existing UI tool: independent
- Pilot grade: Grade 12
- Behavioral matrix: available
- Development: AI-assisted (Claude Code)
- Deadline: May 1

---

## 13. AI Agent Instructions

The agent should:

1. Build a **constraint-based scheduling engine**
2. Separate:
   - Master schedule generation
   - Student assignment
3. Allow iterative optimization
4. Provide explainability for decisions
5. Support scenario simulation
6. Export PowerSchool-compatible outputs

---

## 14. Recommended Development Approach

### Step 1
Data ingestion and validation

### Step 2
Master schedule optimization

### Step 3
Student assignment optimization

### Step 4
Constraint tuning

### Step 5
Export + testing in PowerSchool

### Step 6
Add AI assistant layer (optional)

---

## 15. Key Insight

This is NOT primarily an AI problem.

This is a:
- Constraint optimization problem
- Data modeling problem

Success depends on:
- Clean data
- Well-defined constraints
- Strong optimization engine

---

## 16. Final Recommendation

Use a hybrid approach:

1. PowerSchool as system of record
2. External optimization engine
3. AI layer for explanation and decision support
4. Human-in-the-loop validation

Preferred engine: 

**Google OR-Tools**
(Agent may propose a better alternative)

Ask only requiered questions to continue.
