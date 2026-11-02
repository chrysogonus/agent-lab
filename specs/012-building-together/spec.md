# Feature Specification: M12 — Building Together

**Feature Branch**: `main` (feature directory `012-building-together`)

**Created**: 2026-11-02

**Status**: Draft

**Input**: The roadmap line "M12 Building together: painting houses, planting trees, market
stands, new buildings from a catalogue that take several days, boat trips", and the owner's
answers: "new good such as wood and paint. they are delivered by outside trader that arrive every
day at the market and sell their merchandise. they stay for like 5 hours long and then go again.
villagers meet every three days at the town hall and vote. hilde makes the proposals and then
after the vote she decides what needs to be build next. she also plans and distributes the work.
not every villager needs to help but it can be like that if reasonable"

## Context

M11 gave the villagers plans, work and baskets, and the work comes to something once a year, at
the festival. When the festival is over, nothing they did stays. This milestone gives the village
lasting projects: things the villagers choose together, pay for, carry and build over days, and
that stay on the map afterwards.

Three new parts make this work:

- **Traders**: every day an outside trader comes to the market, stays about five hours and sells
  building goods.
- **The town hall meeting**: every three days the villagers meet at the town hall. Hilde proposes
  what to build, the villagers vote, and Hilde decides.
- **Building**: Hilde plans the chosen project and hands out the work; the villagers buy the
  goods, carry them to the site and build.

All earlier contracts apply:
- every model call is a traced run of a block agent, and the village never calls the model
  directly;
- invalid answers change nothing and record why;
- tests use the scripted fake model only;
- no new dependency;
- reduced motion is respected;
- the village still pauses 60 seconds after the last viewer leaves.

The travelling merchant planned for M13 becomes the daily trader of this milestone, and boat
trips move from M12 to M13: M12 builds the boat. The roadmap is now M13 Daily happenings (the
postman, a visiting friend, boat trips on the lake, …; whispers to villagers), M14 MCP, M15
Harness, M16 Agent memory for the lab's other agents, M17 RAG.

Owner's decisions on the open questions (2026-11-02): villagers pay the trader with their M11
baskets, one basket for one load; Hilde may overrule the vote but must give a reason; the boat is
a catalogue project, and trips on the lake wait for M13.

## User Scenarios & Testing *(mandatory)*

The user is the project owner, who watches the village, reads its chronicle and opens villager
turns to see why they acted.

### User Story 1 - The daily trader (Priority: P1)

Every morning a trader arrives at the market with a stock of building goods (wood, paint,
saplings) and leaves about five hours later. While the trader is there, a villager at the market
can trade the basket it carries (fish, vegetables or flowers, from M11 work) for one load of
goods. A villager carries one thing at a time, so the load takes the basket's place. The owner
sees the trader and its stock at the market, and the villagers are told when it comes, what it
sells and when it leaves.

**Why this priority**: without materials, nothing can be built; the trader is also something new
to see every day, and it gives the villagers' M11 work a use all year. In autumn a basket can go
to the trader or to the festival stalls, a choice the villagers have to make.

**Independent Test**: with the scripted model, a trader appears at the market at its arrival
time with that day's stock and leaves at the leaving time; a villager at the market with a
basket trades it for a load while the trader is there; buying when it is gone, sold out, with
empty hands or while carrying a load is refused with the reason.

**Acceptance Scenarios**:

1. **Given** a new village day, **When** the clock reaches 09:00, **Then** a trader stands at the
   market with that day's stock, and at 14:00 it leaves with what it did not sell.
2. **Given** a villager at the market carrying a basket while the trader is there, **When** it
   answers buy with one of the goods in stock, **Then** the trader takes the basket, the villager
   carries a load of those goods instead, the stock goes down by one, and the trade is noted in
   the day record.
3. **Given** a buy before 09:00, after 14:00, away from the market, of goods out of stock, with
   empty hands ("you have nothing to trade: bring a basket") or while carrying a load, **When**
   it is applied, **Then** the villager waits with the reason and keeps what it carries.
4. **Given** a villager deciding, **When** the trader is in the village, **Then** it is told
   what the trader sells and until when; before 09:00 it is told the trader is expected.
5. **Given** the map, **When** the trader is there, **Then** the market shows the trader and its
   goods; when it has left, it does not.

---

### User Story 2 - The town hall meeting and vote (Priority: P1)

Every third day the villagers meet at the town hall at 17:00. That morning Hilde writes her
proposals: two or three projects from the village catalogue, each with a reason. All day,
everyone is told about the meeting and the proposals. At the meeting, Hilde chairs and each
other villager at the town hall votes for one proposal and gives a reason. Then Hilde decides what is built next. She sees
the votes and usually follows them, but she may choose another proposal if she gives a reason;
the villagers are told when she went against the vote, and the chronicle notes it. The owner sees
the proposals, the votes and the decision, and so does the chronicle.

**Why this priority**: choosing together is what makes the projects the village's own and
gives the owner a decision to watch.

**Independent Test**: with the scripted model, on a meeting day Hilde's proposal run produces
proposals from the catalogue; at 17:00 every villager at the town hall casts a vote; Hilde's
decision then sets the current project; invalid proposals, votes or decisions are recorded with
the reason, and the meeting still ends with a decision or with none.

**Acceptance Scenarios**:

1. **Given** day 3, 6, 9, … (every third day), **When** Hilde wakes, **Then** one proposal run
   starts for her, and a valid answer gives two or three catalogue projects that are not built
   yet, each with a reason.
2. **Given** a meeting day, **When** any villager decides or plans that day, **Then** it is told
   about the meeting at 17:00 and what Hilde proposes.
3. **Given** 17:00 on a meeting day, **When** the meeting starts, **Then** every awake villager
   but Hilde at the town hall gets one vote run; a valid vote names one of the proposals and a reason.
4. **Given** the votes, **When** they are in, **Then** Hilde's decision run sees the proposals
   and the votes, and a valid decision names one of the proposals as the project built next,
   with a reason.
5. **Given** a decision for a proposal other than the one with the most votes, **When** it is
   stored, **Then** it stands, every villager is told that Hilde went against the vote and why,
   and the day record and the chronicle note it.
6. **Given** a meeting where only Hilde is at the town hall, **When** it starts, **Then** she
   decides alone, and the record says nobody else came; a meeting Hilde does not come to by
   18:30 is called off, and the record says so.
7. **Given** a project still unfinished on a meeting day, **When** the meeting is held,
   **Then** nothing new is proposed: Hilde reviews the progress and may hand out the work again.
8. **Given** the villager panel and the chronicle, **When** the owner looks after a meeting,
   **Then** they see the proposals, each vote with its reason, and the decision; each run opens
   its trace.

---

### User Story 3 - Hilde plans and hands out the work (Priority: P1)

When a project is chosen, Hilde plans it: who buys which goods from the trader, who carries
them to the site, and who builds. Not everyone has to help; she gives work to those it suits,
and several villagers can share a job. The tasks go into the villagers' plans and observations
until they are done.

**Why this priority**: it is how a decision becomes work, and it gives the villagers' days a
shared purpose beyond their own routines.

**Independent Test**: with the scripted model, a decision is followed by a work-plan run for
Hilde; its valid answer gives tasks to named villagers; each assigned villager's next plan and
observations show its task; an invalid answer leaves the project without tasks and records why.

**Acceptance Scenarios**:

1. **Given** a decided project, **When** the decision is stored, **Then** Hilde's work-plan run
   starts and a valid answer gives one to six tasks: buy goods, bring them to the site, or
   build, each with one or more villagers.
2. **Given** a villager with a task, **When** it plans its day or decides, **Then** it is told
   its task and what the project still needs.
3. **Given** a villager without a task, **When** it decides, **Then** it is told about the
   project but nothing is asked of it; it may still help.
4. **Given** a task that names a villager or goods that do not exist, **When** the plan is
   checked, **Then** that task is dropped; a work plan left with no tasks is invalid.

---

### User Story 4 - Building and seeing it stay (Priority: P2)

Villagers carry their loads to the project's site and set them down there (give, standing at the
site), then work at the site. Each village hour of building work uses one load from the site.
When the last load has been worked in, the project is done. While it is being built, the site
shows the goods and the progress. Afterwards the change stays on the map: a painted house, a row
of new trees, a market stand, a new building. The villagers know it is there, the chronicle
celebrates it, and the next proposals come from what is left in the catalogue.

**Why this priority**: the visible, lasting result is the point of the milestone, but it builds
on the trader, the meeting and the tasks.

**Independent Test**: with the scripted model, loads given at the site add to it, work there uses
them one village hour at a time, and the project completes and stays on the map and in the state;
building without loads, or at another place, is refused with the reason.

**Acceptance Scenarios**:

1. **Given** a villager carrying a load the project needs, at its site, **When** it answers give
   without a name, **Then** the load goes onto the site and counts toward the project.
2. **Given** a site with loads, **When** villagers work there, **Then** their work adds up as in
   M11, and every village hour of work uses one load and moves the project forward.
3. **Given** a site with no loads left and the project not finished, **When** a villager answers
   work there, **Then** it waits with the reason that the site needs goods first.
4. **Given** the last load worked in, **When** the hour passes, **Then** the project is done,
   the map shows the result from then on, every villager is told, and the day record notes it.
5. **Given** a load the project does not need (paint for planting trees), **When** it is given
   at the site, **Then** the villager waits with the reason and keeps the load.
6. **Given** a building that needs more loads than fit in a day's work, **When** days pass,
   **Then** the site keeps its loads and progress overnight and the work goes on.

---

### Edge Cases

- **A load at bedtime.** A villager carrying a load goes to bed and keeps it overnight. A
  villager carries one thing at a time: a basket or a load.
- **Late to the meeting.** 17:00 is before everyone's bedtime. Everyone away is called at 16:30
  (the walk can take half an hour). A villager arriving before Hilde decides still votes; Hilde
  decides from 17:30 once she is there.
- **Festival day.** A meeting day that is also the festival day moves the meeting to the next
  day.
- **Bad proposals.** Hilde proposes a project that is built already or not in the catalogue →
  that proposal is dropped. Fewer than two proposals left → only one is offered, and nothing is
  offered when the catalogue is empty.
- **Bad votes.** A vote for something not proposed is invalid and not counted; the reason is
  recorded.
- **A bad decision.** Hilde's decision names nothing she proposed → the proposal with the most
  valid votes is built (ties: her order); with no valid votes, nothing is decided until the next
  meeting. Either way the reason is recorded.
- **Hilde stays away.** Hilde has not come to the town hall by 18:30 → the meeting is
  called off; the votes cast are kept on record, and the next meeting is three days later.
- **An empty catalogue.** Everything is built → the meeting is held without proposals and the
  chronicle says so.
- **Nobody buys.** The trader leaves, and the next day's trader comes with fresh stock.
- **Hilde has no basket.** She has no goods of her own; she can buy with a basket someone gives
  her.
- **The baskets leave.** Baskets traded away leave with the trader; they are no longer the
  village's, and they do not count for the festival.
- **Buying without a task.** A villager may buy and bring goods without a task; anything the
  project needs counts.
- **More than needed.** A load the project no longer needs (its site already holds enough of
  that kind) is refused at the site; the villager keeps it for a later project or gives it away.
- **Reset.** Reset clears the trader, meetings, projects, sites and everything built.
- **An M11 village.** A village saved by M11 loads with no project, no loads, nothing built, and
  the next meeting on the next day divisible by three.

## Requirements *(mandatory)*

### Functional Requirements

**Traders**

- **FR-001**: Every village day a trader MUST come to the market at 09:00 and leave at 14:00, with
  a stock of wood, paint and saplings that differs from day to day but is fixed for a given day.
- **FR-002**: A new action buy MUST, while the trader is there, trade the basket of a villager at
  the market (any of fish, vegetables or flowers) for one load of goods in stock; any other buy
  (no trader, not at the market, out of stock, empty hands, carrying a load) becomes a wait with
  the reason, and the villager keeps what it carries.
- **FR-003**: Villagers MUST be told when the trader comes, what it sells and until when; the map
  MUST show the trader and its stock while it is there.

**The meeting**

- **FR-004**: On every third day (the festival day moves it to the next day), Hilde's proposal run
  MUST give two or three catalogue projects not yet built (fewer when fewer are left), each with
  a reason of at most 120 characters; projects not in the catalogue or already built are dropped.
- **FR-005**: On a meeting day, every villager's plan and observations MUST mention the meeting at
  17:00 at the town hall and the proposals.
- **FR-006**: From 17:00 every awake villager but Hilde at the town hall, or arriving there before
  Hilde decides (from 17:30, once she is there; called off without her by 18:30), MUST get one
  vote run whose valid answer names one proposal and a reason; then Hilde's decision
  run MUST see the proposals and votes and name one proposal as the project built next, with a
  reason; it may differ from the vote, and then every villager is told that Hilde went against
  the vote and why, and the day record and the chronicle note it.
- **FR-007**: While a project is unfinished, the meeting MUST review its progress instead of
  proposing, and Hilde may hand out the work again.

**Work plan**

- **FR-008**: A decided project MUST start Hilde's work-plan run; a valid answer gives one to six
  tasks (buy goods, bring them to the site, build), each for one or more named villagers; tasks
  naming unknown villagers or goods are dropped.
- **FR-009**: Each villager's plan and observations MUST show its tasks and what the project still
  needs; villagers without a task are told about the project.

**Building**

- **FR-010**: Give without a name at the site of the current project MUST put a load the project
  still needs onto the site; any other load there is refused with the reason.
- **FR-011**: Work MUST be valid at the site of the current project while it has loads; every
  village hour of work added up there (as in M11) uses one load and moves the project forward;
  work without loads is refused with the reason.
- **FR-012**: When a project's last load is worked in, it MUST be done: it stays on the map and in
  the state for good, every villager is told, and it is noted in the day record and named in the
  chronicle.
- **FR-013**: The village catalogue MUST hold the projects that can be built, each with a name,
  a site on the map, the loads it needs and how it looks when done; it MUST include painting a
  house, planting trees, a market stand, at least two buildings that take more than one day of
  one villager's work, and a boat at the pier.

**Showing it**

- **FR-014**: The owner MUST see the current project (what it needs, what the site holds, its
  progress and its tasks), the latest meeting (proposals, votes and decision), and everything
  built; proposal, vote, decision and work-plan runs appear among the villagers' turns.
- **FR-015**: The chronicle MUST be told about trader visits, purchases, meetings with their
  votes and decision, deliveries, progress and completions.

**State and quality**

- **FR-016**: The villagers' rules MUST describe buy, the meeting and building; stored agents
  still holding the M11 rules text get the new text on load, others are left alone.
- **FR-017**: A village saved by M11 MUST keep going with no project, no loads and nothing built;
  Reset clears all of it and keeps the agents.
- **FR-018**: Tests MUST use the scripted fake model only and cover: the trader's arrival, stock
  and departure; every valid and invalid buy; proposals, votes and decisions, valid and invalid;
  a decision against the vote; meetings with nobody else, with an unfinished project and on the
  festival day; work plans and tasks in observations; deliveries and building, valid and invalid;
  completion staying on the map, the boat included; loading an M11 village.
- **FR-019**: All quality gates MUST pass; every requirement maps to a test or a manual check in
  `tasks.md`.

### Key Entities

- **Trader**: per day. Arrival and leaving time, and the stock left of each of the goods.
- **Load**: per villager. One load of wood, paint or saplings, carried instead of a basket.
- **Catalogue project**: name, site, loads needed by kind, and how it looks when done.
- **Meeting**: per meeting day. Proposals with reasons, votes with reasons, Hilde's decision
  with its reason, and who attended.
- **Current project**: the chosen catalogue project, its tasks, the loads at its site and the
  loads worked in so far.
- **Task**: kind (buy, bring, build), goods if any, and the villagers it is for.
- **Built**: the projects finished, kept for good.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In scripted days, the trader is at the market from 09:00 to 14:00 on every day and
  at no other time, and every buy is either applied or refused with a reason.
- **SC-002**: In a scripted cycle, a meeting leads to a decision; the decision's tasks show in the
  assigned villagers' plans; the goods are bought and brought; the project is completed by work
  and stays on the map after the next day begins.
- **SC-003**: In scripted meetings, every villager but Hilde at the town hall has exactly one vote
  recorded,
  and the decision and its reason are visible to the owner and in the chronicle.
- **SC-004**: On the real model, starting on a meeting day at Fast pace, the meeting is held with
  at least three villagers present, and at least one project is completed within six village days
  (manual check).
- **SC-005**: On the real model, at least two villagers trade a basket for goods and at least two
  work at the site during the first project (manual check).

## Assumptions

- **Not agents.** The trader is not an agent and never calls the model; it is a figure with a
  stock. Talking traders can come with M13.
- **Hilde's runs.** Hilde's proposals, decision and work plan are traced runs of shared village
  agents, like the planner, so the villagers' decision prompts stay small; each vote is a run too.
- **One project at a time.** The next is chosen only after the current one is done.
- **Fixed sites.** Every catalogue project has its own place on the map; new buildings go on
  grass that is free today.
- **One basket, one load.** Any basket buys any one load; prices never change, there is no money,
  and goods never spoil.
- **The boat stays moored.** A finished boat is shown at the pier; going out on the lake comes
  with M13.
- **Unchanged rules.** The work and growth rules of M11 stay as they are; building is work at a
  new kind of place.
- **One load is one hour.** A load is one village hour of work: a painted house needs 2 loads of
  paint, a row of trees 3 loads of saplings, a market stand 3 wood and 1 paint, and a new
  building 17 or more loads, more than the longest waking day (16 hours), so it takes more than
  a day for one villager.
- **Every season.** Building goes on in every season and in any weather.
