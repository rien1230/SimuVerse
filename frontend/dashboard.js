// Replay dashboard logic: builds the timeline, panels, and playback state.
const SCENARIOS = {
      office: {
        key: "office",
        label: "Office Project",
        sceneTitle: "Live Office Simulation",
        intro: "A project team must exchange four owned inputs before they can move the office project forward.",
        goal: "Goal: complete all project tasks by sharing and confirming information between agents.",
        coordinator: "A1",
        deputy: "A4",
        agents: [
          { id: "A1", name: "John", role: "Project Lead", x: 14, y: 88, color: "#2a78c5", skin: "#efc9ae", hair: "#5a4136", accent: "#f4d35e", hairStyle: "side", accessory: "tie", gender: "m" },
          { id: "A2", name: "Lisa", role: "Developer", x: 34, y: 62, color: "#1f8f83", skin: "#f2d3bb", hair: "#74493f", accent: "#d9f2ec", hairStyle: "bun", accessory: "lanyard", gender: "f" },
          { id: "A3", name: "Mark", role: "Designer", x: 66, y: 62, color: "#c84a4a", skin: "#d9a987", hair: "#2f2b2a", accent: "#f9c9c4", hairStyle: "wave", accessory: "strap", gender: "m" },
          { id: "A4", name: "Emma", role: "Data Analyst", x: 86, y: 88, color: "#b97418", skin: "#c98f6c", hair: "#3f2d25", accent: "#ffd8a8", hairStyle: "bob", accessory: "lanyard", gender: "f" }
        ],
        tasks: [
          {
            key: "requirements",
            label: "Requirements",
            completedLabel: "Requirements Confirmed",
            artifact: "project requirements",
            owner: "A2",
            requester: "A1",
            receiver: "A4",
            shareText: [
              "I have the project requirements and client constraints ready for the team.",
              "Here are the agreed project requirements and delivery expectations."
            ],
            blockerText: "The team cannot scope the work until the Developer shares the requirements."
          },
          {
            key: "design",
            label: "Design Plan",
            completedLabel: "Design Confirmed",
            artifact: "design plan",
            owner: "A3",
            requester: "A1",
            receiver: "A2",
            shareText: [
              "Here is the latest design plan and the screen flow we can build against.",
              "I have the design plan ready, including the flow we need to support."
            ],
            blockerText: "Implementation decisions are waiting on the Designer's plan."
          },
          {
            key: "tech_specs",
            label: "Technical Specs Review",
            completedLabel: "Technical Specs Confirmed",
            artifact: "technical specification",
            owner: "A4",
            requester: "A2",
            receiver: "A1",
            shareText: [
              "I translated the requirements into technical specifications and delivery constraints.",
              "The technical specification is ready, including the data and implementation constraints."
            ],
            blockerText: "The build cannot be scheduled until the technical specification is shared."
          },
          {
            key: "budget",
            label: "Budget Sign-off",
            completedLabel: "Budget Approved",
            artifact: "budget sign-off",
            owner: "A1",
            requester: "A4",
            receiver: "A3",
            shareText: [
              "I have the budget sign-off and the acceptable trade-offs for the team.",
              "The budget sign-off is approved. We now know what we can commit to."
            ],
            blockerText: "The project cannot be committed until the budget owner signs off."
          }
        ]
      },
      cafe: {
        key: "cafe",
        label: "Cafe Planning",
        sceneTitle: "Live Cafe Simulation",
        intro: "A small team needs to align on destination, timing, food, and budget before the cafe plan feels settled.",
        goal: "Goal: complete the cafe plan by sharing and confirming the missing details between agents.",
        coordinator: "A1",
        deputy: "A4",
        agents: [
          { id: "A1", name: "Ava", role: "Organiser", x: 14, y: 88, color: "#2a78c5", skin: "#f1c8ad", hair: "#422f2b", accent: "#cfe6fb", hairStyle: "bob", accessory: "lanyard", gender: "f" },
          { id: "A2", name: "Theo", role: "Researcher", x: 34, y: 62, color: "#1f8f83", skin: "#d9aa86", hair: "#57473d", accent: "#d2f1eb", hairStyle: "short", accessory: "strap", gender: "m" },
          { id: "A3", name: "Priya", role: "Food Planner", x: 66, y: 62, color: "#c84a4a", skin: "#b97957", hair: "#251817", accent: "#fff0ea", hairStyle: "bun", accessory: "apron", gender: "f" },
          { id: "A4", name: "Noah", role: "Budget Keeper", x: 86, y: 88, color: "#b97418", skin: "#8b5d42", hair: "#2f211d", accent: "#ffe1b8", hairStyle: "curl", accessory: "tie", gender: "m" }
        ],
        tasks: [
          {
            key: "dietary_constraint",
            label: "Dietary Constraint",
            completedLabel: "Dietary Needs Confirmed",
            artifact: "dietary constraint",
            owner: "A2",
            requester: "A1",
            receiver: "A4",
            shareText: [
              "I checked the dietary needs — there are restrictions the group needs to accommodate.",
              "The dietary constraint is clear now. The venue needs to support these requirements."
            ],
            blockerText: "The group cannot commit to a venue until dietary needs are confirmed."
          },
          {
            key: "budget_constraint",
            label: "Budget Constraint",
            completedLabel: "Budget Agreed",
            artifact: "budget constraint",
            owner: "A3",
            requester: "A1",
            receiver: "A2",
            shareText: [
              "I have the budget constraint. We know what the group can comfortably spend.",
              "The budget limit is confirmed — it narrows down the options nicely."
            ],
            blockerText: "The team cannot narrow venue options until the budget is clear."
          },
          {
            key: "location_constraint",
            label: "Location Constraint",
            completedLabel: "Location Confirmed",
            artifact: "location constraint",
            owner: "A4",
            requester: "A1",
            receiver: "A3",
            shareText: [
              "I found a location that works for everyone — close enough and easy to get to.",
              "The location constraint is set. It rules out the places that are too far."
            ],
            blockerText: "The plan is still open until location preferences are on the table."
          },
          {
            key: "decision",
            label: "Final Decision",
            completedLabel: "Plan Complete",
            artifact: "final decision",
            owner: "A1",
            requester: "A4",
            receiver: "A3",
            shareText: [
              "The decision is in — we know where we're going and the plan feels settled.",
              "Final decision confirmed. The group is aligned and the booking can go ahead."
            ],
            blockerText: "The cafe plan cannot close until the group reaches a final decision."
          }
        ]
      },
      escape: {
        key: "escape",
        label: "Escape Room",
        sceneTitle: "Live Escape Room Simulation",
        intro: "Each agent owns one part of the puzzle. The team only escapes if the clues are handed over in time.",
        goal: "Goal: escape by sharing and confirming every clue before the final code is used.",
        coordinator: "A1",
        deputy: "A4",
        agents: [
          { id: "A1", name: "Quinn", role: "Team Lead", x: 14, y: 88, color: "#2a78c5", skin: "#e7bc96", hair: "#4a3428", accent: "#d5e7fb", hairStyle: "short", accessory: "strap", gender: "m" },
          { id: "A2", name: "Zara", role: "Code Breaker", x: 34, y: 62, color: "#1f8f83", skin: "#f0d4bc", hair: "#1f1718", accent: "#d6f3ee", hairStyle: "wave", accessory: "strap", gender: "f" },
          { id: "A3", name: "Leo", role: "Puzzle Solver", x: 66, y: 62, color: "#c84a4a", skin: "#a86f51", hair: "#6a4b39", accent: "#f9d6d1", hairStyle: "curl", accessory: "lanyard", gender: "m" },
          { id: "A4", name: "Nova", role: "Scout", x: 86, y: 88, color: "#b97418", skin: "#d7a27d", hair: "#352521", accent: "#ffe0b0", hairStyle: "bun", accessory: "strap", gender: "f" }
        ],
        tasks: [
          {
            key: "map",
            label: "Room Map",
            completedLabel: "Room Map Shared",
            artifact: "room map",
            owner: "A4",
            requester: "A1",
            receiver: "A2",
            shareText: [
              "I found the room map and marked the hidden panel on it.",
              "The room map is here. It shows where the hidden panel really is."
            ],
            blockerText: "The team cannot read the room until the Scout shares the map."
          },
          {
            key: "key",
            label: "Key Location",
            completedLabel: "Key Location Found",
            artifact: "key location",
            owner: "A2",
            requester: "A1",
            receiver: "A4",
            shareText: [
              "I found the key location. It is under the loose tile by the door.",
              "The key location is confirmed. It is hidden near the exit panel."
            ],
            blockerText: "The team is still waiting on the Code Breaker's key location clue."
          },
          {
            key: "lock",
            label: "Lock Pattern",
            completedLabel: "Lock Pattern Solved",
            artifact: "lock pattern",
            owner: "A3",
            requester: "A2",
            receiver: "A1",
            shareText: [
              "The lock pattern is solved. The sequence is triangle, circle, square.",
              "I decoded the lock pattern, so the team can stop guessing."
            ],
            blockerText: "The next mechanism stays blocked until the lock pattern is known."
          },
          {
            key: "door",
            label: "Door Code",
            completedLabel: "Door Code Confirmed",
            artifact: "door code",
            owner: "A1",
            requester: "A4",
            receiver: "A3",
            shareText: [
              "The door code is confirmed now, so the team can finally move.",
              "I have the final door code. We can leave if everyone trusts it."
            ],
            blockerText: "The group cannot escape until the Team Lead confirms the final code."
          },
          {
            key: "unlock",
            label: "Exit Lock",
            completedLabel: "Room Escaped",
            artifact: "exit lock",
            owner: "A1",
            requester: "A4",
            receiver: "A2",
            shareText: [
              "The exit lock is open. We made it.",
              "Exit confirmed — the room is unlocked."
            ],
            blockerText: "The team cannot escape until all clues are confirmed and the exit is unlocked."
          }
        ]
      }
    };

    const TEAM_STYLES = {
      smooth: {
        key: "smooth",
        label: "Smooth Team",
        modeHint: "Cooperative personalities share quickly and recover from minor delays.",
        baseTrust: 0.68,
        baseStress: 0.16,
        baseConflict: 0.06,
        trustFactor: 1.05,
        stressFactor: 0.85,
        conflictFactor: 0.8
      },
      tension: {
        key: "tension",
        label: "Tension Team",
        modeHint: "Guarded personalities hesitate more, question more, and feel waiting pressure faster.",
        baseTrust: 0.48,
        baseStress: 0.28,
        baseConflict: 0.16,
        trustFactor: 0.92,
        stressFactor: 1.2,
        conflictFactor: 1.3
      },
      creative: {
        key: "creative",
        label: "Creative Team",
        modeHint: "Curious personalities explore alternatives before they settle on a shared answer.",
        baseTrust: 0.57,
        baseStress: 0.22,
        baseConflict: 0.1,
        trustFactor: 1,
        stressFactor: 1,
        conflictFactor: 1
      },
      pressure: {
        key: "pressure",
        label: "Pressure Team",
        modeHint: "Urgent personalities move quickly, but the pace itself increases emotional strain.",
        baseTrust: 0.54,
        baseStress: 0.31,
        baseConflict: 0.12,
        trustFactor: 0.96,
        stressFactor: 1.28,
        conflictFactor: 1.08
      }
    };

    const EVENT_META = {
      ask: { label: "ASK" },
      share: { label: "SHARE" },
      confirm: { label: "CONFIRM" },
      hold: { label: "HOLD" },
      refuse: { label: "REFUSE" },
      challenge: { label: "CHALLENGE" },
      brainstorm: { label: "IDEA" },
      wrap: { label: "WRAP" }
    };

    const EVENT_EFFECTS = {
      ask: { trust: 0, stress: 0.025, conflict: 0 },
      share: { trust: 0.055, stress: -0.02, conflict: -0.018 },
      confirm: { trust: 0.03, stress: -0.012, conflict: -0.01 },
      refuse: { trust: -0.05, stress: 0.055, conflict: 0.06 },
      challenge: { trust: -0.02, stress: 0.032, conflict: 0.045 },
      brainstorm: { trust: 0.01, stress: 0.015, conflict: 0.01 },
      wrap: { trust: 0.02, stress: -0.05, conflict: -0.025 }
    };

    const PARAMS = new URLSearchParams(window.location.search);

    function normalizeScenario(value) {
      const lower = String(value || "").toLowerCase();
      if (lower.includes("cafe")) return "cafe";
      if (lower.includes("escape")) return "escape";
      return "office";
    }

    function normalizeTeam(value) {
      const lower = String(value || "").toLowerCase();
      if (lower.includes("tension") || lower.includes("tense")) return "tension";
      if (lower.includes("creative")) return "creative";
      if (lower.includes("pressure")) return "pressure";
      return "smooth";
    }

    function normalizeMode(value) {
      const lower = String(value || "").toLowerCase();
      if (lower.includes("step") || lower === "interactive") return "step";
      return "auto";
    }

    function clamp(value, min, max) {
      return Math.min(max, Math.max(min, value));
    }

    function average(values) {
      return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
    }

    function hashString(value) {
      let hash = 2166136261;
      for (let i = 0; i < value.length; i += 1) {
        hash ^= value.charCodeAt(i);
        hash = Math.imul(hash, 16777619);
      }
      return hash >>> 0;
    }

    function mulberry32(seed) {
      return function rng() {
        let t = seed += 0x6d2b79f5;
        t = Math.imul(t ^ (t >>> 15), t | 1);
        t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
      };
    }

    function createRng(seedText) {
      return mulberry32(hashString(String(seedText)));
    }

    function jitter(rng, min, max) {
      return min + (max - min) * rng();
    }

    function pick(rng, options) {
      return options[Math.floor(rng() * options.length)] || options[0];
    }

    function moodLabel(score) {
      if (score < 0.26) return "Tense";
      if (score < 0.44) return "Guarded";
      if (score < 0.62) return "Focused";
      if (score < 0.8) return "Steady";
      return "Confident";
    }

    function trustMeaning(value) {
      if (value < 0.42) {
        return {
          label: "Fragile cooperation",
          copy: "The agent is hesitant to rely on others and may resist new input."
        };
      }
      if (value < 0.62) {
        return {
          label: "Stable cooperation",
          copy: "The agent is generally willing to accept help, but delays can still create doubt."
        };
      }
      return {
        label: "High cooperation",
        copy: "The agent is openly receptive to useful information from the rest of the team."
      };
    }

    function stressMeaning(value) {
      if (value <= 0.25) {
        return {
          label: "Low pressure",
          copy: "The agent is calm enough to coordinate without visible strain."
        };
      }
      if (value <= 0.55) {
        return {
          label: "Moderate pressure",
          copy: "The agent feels urgency, but the situation is still manageable."
        };
      }
      return {
        label: "High pressure",
        copy: "Waiting, friction, or deadlines are creating strong emotional load."
      };
    }

    function conflictMeaning(value) {
      if (value < 0.12) {
        return {
          label: "Low friction",
          copy: "Disagreement is present only in small amounts and is not slowing the team much."
        };
      }
      if (value < 0.24) {
        return {
          label: "Manageable friction",
          copy: "There is some disagreement or doubt, but the team is still moving."
        };
      }
      return {
        label: "Visible friction",
        copy: "Refusals, doubt, or pressure are actively slowing coordination."
      };
    }

    function progressMeaning(value) {
      if (value === 0) {
        return {
          label: "Just starting",
          copy: "The team has identified the first dependency but has not cleared any scenario goals yet."
        };
      }
      if (value < 50) {
        return {
          label: "Early progress",
          copy: "The team has started clearing dependencies, but key dependencies still remain."
        };
      }
      if (value < 100) {
        return {
          label: "Momentum building",
          copy: "Most goals are moving, and the team is clearly advancing through the scenario."
        };
      }
      return {
        label: "Run complete",
        copy: "All scenario goals are complete, so the team can close the loop."
      };
    }

    function ticksMeaning(currentTick, totalTicks) {
      if (currentTick >= totalTicks) {
        return {
          label: "Run complete",
          copy: "All planned steps are complete, so the full run can be reviewed."
        };
      }
      if (currentTick <= Math.max(2, Math.ceil(totalTicks * 0.3))) {
        return {
          label: "Early stage",
          copy: "The team is still establishing the first handoffs."
        };
      }
      if (currentTick >= Math.floor(totalTicks * 0.75)) {
        return {
          label: "Final stretch",
          copy: "Most of the run is visible, and only the remaining steps are left."
        };
      }
      return {
        label: "Mid run",
        copy: "The run is underway and the team has already cleared some dependencies."
      };
    }

    function modeLabel(mode) {
      return mode === "step" ? "Interactive Mode" : "Watch Mode";
    }

    function scenarioCompletionLabel(scenario) {
      if (scenario.key === "escape") return "Escape Successful";
      if (scenario.key === "cafe") return "Plan Complete";
      return "Run Complete";
    }

    function scenarioResolvedNoun(scenario) {
      if (scenario.key === "escape") return "clues";
      if (scenario.key === "cafe") return "plan details";
      return "dependencies";
    }

    function scenarioWrapCopy(scenario) {
      if (scenario.key === "escape") return "All clues are confirmed, so the escape room is complete.";
      if (scenario.key === "cafe") return "All plan details are confirmed, so the cafe plan is complete.";
      return "All tasks are complete, so the team can close the scenario.";
    }

    const API_BASE = window.SimuVerseAPI.API_BASE;
    const BACKEND_EVENT_PRIORITY = {
      share_info: 9,
      refuse: 8,
      challenge: 7,
      agree: 7,
      ask_info: 6,
      suggest: 5,
      help: 4,
      say: 3,
      compliment: 2,
      ignore: 1,
      insult: 1
    };

    // CONFIG holds the scenario + team identity for this page. It starts from the
    // URL query (preferred: setup.html always attaches scenario= and team=), but
    // `reconcileConfigFromStatus(status)` below overwrites it from the backend
    // `status.scenario.environment` / `status.config.resolved_team_type` as soon
    // as the first /runs/{id} fetch returns, so the frontend can never silently
    // render a cafe run with office templates (or any other cross-wire).
    const CONFIG = {
      scenarioKey: normalizeScenario(PARAMS.get("scenario") || PARAMS.get("env")),
      teamKey: normalizeTeam(PARAMS.get("team") || PARAMS.get("style") || PARAMS.get("team_type")),
      mode: normalizeMode(PARAMS.get("mode"))
    };

    function reconcileConfigFromStatus(status) {
      if (!status) return;
      const backendScenario = status?.scenario?.environment || status?.config?.environment;
      if (backendScenario) {
        const resolved = normalizeScenario(backendScenario);
        if (resolved !== CONFIG.scenarioKey) {
          console.info("[dashboard] scenarioKey reconciled", CONFIG.scenarioKey, "→", resolved);
          CONFIG.scenarioKey = resolved;
        }
      }
      const backendTeam = status?.config?.resolved_team_type || status?.config?.team_type || status?.team_type;
      if (backendTeam) {
        const resolvedTeam = normalizeTeam(backendTeam);
        if (resolvedTeam !== CONFIG.teamKey) {
          console.info("[dashboard] teamKey reconciled", CONFIG.teamKey, "→", resolvedTeam);
          CONFIG.teamKey = resolvedTeam;
        }
      }
    }

    let runId = PARAMS.get("run_id") || PARAMS.get("id") || "";
    let rawRunState = null;
    let RUN = null;
    let currentIndex = 0;
    let currentView = "live";
    let playing = false;
    let playbackMode = "idle";
    let timer = null;
    let ws = null;
    let wsReady = false;

    function taskProgress(tasks) {
      return tasks.length ? Math.round((tasks.filter((task) => task.done).length / tasks.length) * 100) : 0;
    }

    function taskDisplayLabel(task) {
      if (!task) return "Complete";
      return task.done ? (task.completedLabel || task.label) : task.label;
    }

    function formatDelta(value) {
      return (value > 0 ? "+" : "") + value.toFixed(2);
    }

    function joinWithAnd(parts) {
      if (!parts.length) return "";
      if (parts.length === 1) return parts[0];
      return parts.slice(0, -1).join(", ") + " and " + parts[parts.length - 1];
    }

    function titleCase(value) {
      return String(value || "")
        .split(/[\s_-]+/)
        .filter(Boolean)
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(" ");
    }

    function prettifyKey(value) {
      const special = {
        map: "Room Map",
        lock: "Lock Pattern",
        key: "Key Location",
        door: "Door Code",
        unlock: "Exit Lock",
        dietary_constraint: "Dietary Constraint",
        spec_doc: "Spec Doc",
        tech_specs: "Tech Specs",
        complete_proposal: "Complete Proposal",
        choose_restaurant: "Choose Restaurant",
        solve_puzzle: "Solve Puzzle",
        escape_room: "Escape Room"
      };
      return special[value] || titleCase(value);
    }

    function formatGoal(goal, scenarioKey) {
      const goalMap = {
        office: "Goal: complete the project proposal by sharing the required information.",
        cafe: "Goal: finish the group trip plan by aligning the missing details.",
        escape: "Goal: escape the room by sharing and confirming the remaining clues."
      };
      if (!goal) return goalMap[scenarioKey] || "Goal: complete the scenario.";
      return "Goal: " + prettifyKey(goal) + ".";
    }

    function resolveScenarioKeyFromStatus(status) {
      return normalizeScenario(status?.scenario?.environment || status?.config?.environment || CONFIG.scenarioKey);
    }

    function resolveTeamKeyFromStatus(status) {
      return normalizeTeam(
        status?.config?.resolved_team_type || status?.config?.team_type || status?.team_type || CONFIG.teamKey
      );
    }

    function taskTemplateByKey(scenarioKey) {
      const pairs = (SCENARIOS[scenarioKey]?.tasks || []).map((task) => [task.key, task]);
      return new Map(pairs);
    }

    function buildTaskRows(taskState, knowledgeMap, scenarioKey) {
      const ownerByTask = {};
      Object.entries(knowledgeMap || {}).forEach(([agentId, items]) => {
        (items || []).forEach((item) => {
          ownerByTask[item] = agentId;
        });
      });

      const templateMap = taskTemplateByKey(scenarioKey);
      return Object.entries(taskState || {}).map(([key, done]) => {
        const template = templateMap.get(key);
        const label = template?.label || prettifyKey(key);
        return {
          key,
          label,
          completedLabel: template?.completedLabel || (label + " Complete"),
          artifact: template?.artifact || label.toLowerCase(),
          owner: ownerByTask[key] || template?.owner || "A1",
          done: Boolean(done)
        };
      });
    }

    function latestRelatedEvent(step, taskKey) {
      const related = (step?.eventsRaw || []).filter((event) => event?.item === taskKey);
      return related.length ? related[related.length - 1] : null;
    }

    function actorNameFromEvent(step, event, fallback = "the team") {
      if (!event?.actor) return fallback;
      return step?.agents?.[event.actor]?.name || event.actor || fallback;
    }

    function targetNameFromEvent(step, event, fallback = "the team") {
      if (!event?.target) return fallback;
      return step?.agents?.[event.target]?.name || event.target || fallback;
    }

    function taskStatusMeta(task, step) {
      const owner = step?.agents?.[task.owner];
      const latest = latestRelatedEvent(step, task.key);
      const blockerTask = step?.tasks?.find((entry) => entry.label === step.blockerAfter);
      const activeBlockerLabel = blockerTask?.label || step?.blockerAfter || "this dependency";

      if (task.done) {
        return {
          statusTone: "done",
          statusText: "Confirmed",
          detail: ""
        };
      }

      if (task.label === step.blockerAfter) {
        if (latest?.type === "share_info") {
          return {
            statusTone: "waiting",
            statusText: "Waiting",
            detail: "Shared by " + actorNameFromEvent(step, latest) + " — awaiting " + targetNameFromEvent(step, latest) + " confirmation"
          };
        }
        if (latest?.type === "ask_info") {
          return {
            statusTone: "waiting",
            statusText: "Waiting",
            detail: actorNameFromEvent(step, latest) + " requested this clue from " + targetNameFromEvent(step, latest)
          };
        }
        if (latest?.type === "challenge") {
          return {
            statusTone: "waiting",
            statusText: "Waiting",
            detail: actorNameFromEvent(step, latest) + " is re-checking this clue with " + targetNameFromEvent(step, latest)
          };
        }
        return {
          statusTone: "waiting",
          statusText: "Waiting",
          detail: "Waiting for " + (owner ? owner.name : "the owner") + " to resolve this clue"
        };
      }

      return {
        statusTone: "pending",
        statusText: "Locked",
        detail: activeBlockerLabel !== "Complete"
          ? "Locked until " + activeBlockerLabel + " is confirmed"
          : "Not available yet"
      };
    }

    function blockerExplanation(step, activeTask) {
      const latest = activeTask ? latestRelatedEvent(step, activeTask.key) : null;
      if (!activeTask) {
        return "The simulation is still waiting on the next unresolved dependency.";
      }
      if (latest?.type === "share_info") {
        return activeTask.label + " needs confirmation from " + targetNameFromEvent(step, latest) + ".";
      }
      if (latest?.type === "ask_info") {
        return actorNameFromEvent(step, latest) + " is asking " + targetNameFromEvent(step, latest) + " for " + activeTask.label + ".";
      }
      if (latest?.type === "challenge") {
        return activeTask.label + " is being checked before the next step can unlock.";
      }
      const owner = step?.agents?.[activeTask.owner];
      return owner
        ? activeTask.label + " is waiting on " + owner.name + "."
        : activeTask.label + " is the next unresolved dependency.";
    }

    function renderEventMessageHtml(step) {
      const lines = (step?.eventsRaw || []).filter((event) => event?.text).slice(0, 3);
      if (!lines.length) {
        return `<div class="event-message-text">${escapeHtml(currentActionSupport(step))}</div>`;
      }
      return `<div class="event-message-lines">` + lines.map((event) => {
        const actor = actorNameFromEvent(step, event, "Agent");
        const target = targetNameFromEvent(step, event, "");
        const meta = target
          ? `<strong>${escapeHtml(actor)}</strong><span>→</span><strong>${escapeHtml(target)}</strong><span>${escapeHtml(backendEventLabel(event.type, normalizeBackendEventType(event.type)))}</span>`
          : `<strong>${escapeHtml(actor)}</strong><span>${escapeHtml(backendEventLabel(event.type, normalizeBackendEventType(event.type)))}</span>`;
        return `
          <div class="event-message-line">
            <div class="event-message-meta">${meta}</div>
            <div class="event-message-text">${escapeHtml(event.text)}</div>
          </div>
        `;
      }).join("") + `</div>`;
    }

    function firstIncompleteTask(tasks) {
      return tasks.find((task) => !task.done) || null;
    }

    function averageTrustForAgent(agent) {
      const values = Object.values(agent?.trust || {});
      return values.length ? average(values) : 0.5;
    }

    function trustFromSnapshot(snapshot) {
      if (typeof snapshot?.metrics?.avg_trust === "number") return snapshot.metrics.avg_trust;
      if (Array.isArray(snapshot?.ties) && snapshot.ties.length) {
        return average(snapshot.ties.map((tie) => tie.trust || 0));
      }
      if (Array.isArray(snapshot?.agents) && snapshot.agents.length) {
        return average(snapshot.agents.map((agent) => averageTrustForAgent(agent)));
      }
      return 0;
    }

    function stressFromSnapshot(snapshot) {
      if (typeof snapshot?.metrics?.avg_stress === "number") return snapshot.metrics.avg_stress;
      if (Array.isArray(snapshot?.agents) && snapshot.agents.length) {
        return average(snapshot.agents.map((agent) => agent.stress || 0));
      }
      return 0;
    }

    function conflictFromSnapshot(snapshot) {
      if (typeof snapshot?.group_state?.tension === "number") return snapshot.group_state.tension;
      if (typeof snapshot?.metrics?.conflict_rate === "number") return snapshot.metrics.conflict_rate;
      if (typeof snapshot?.run_metrics?.conflict === "number") return snapshot.run_metrics.conflict;
      return 0;
    }

    function peakStressThroughIndex(snapshots, lastIndex) {
      let peak = 0;
      snapshots.slice(0, lastIndex + 1).forEach((snapshot) => {
        (snapshot?.agents || []).forEach((agent) => {
          peak = Math.max(peak, agent?.stress || 0);
        });
      });
      return peak;
    }

    function displayMetricsForSnapshot(snapshot, snapshots, stepIndex) {
      const taskRows = buildTaskRows(
        snapshot?.scenario?.tasks || {},
        snapshot?.scenario?.knowledge_map || {},
        normalizeScenario(snapshot?.scenario?.environment || CONFIG.scenarioKey)
      );
      return {
        progress: typeof snapshot?.scenario?.progress === "number"
          ? Math.round(snapshot.scenario.progress * 100)
          : taskProgress(taskRows),
        averageTrust: trustFromSnapshot(snapshot),
        averageStress: stressFromSnapshot(snapshot),
        peakStress: peakStressThroughIndex(snapshots, stepIndex),
        conflict: conflictFromSnapshot(snapshot)
      };
    }

    function pickPrimaryEvent(events) {
      if (!events?.length) return null;
      return [...events].sort((a, b) => {
        return (BACKEND_EVENT_PRIORITY[b.type] || 0) - (BACKEND_EVENT_PRIORITY[a.type] || 0);
      })[0];
    }

    function buildEventContext(events) {
      const list = Array.isArray(events) ? events.filter(Boolean) : [];
      const firstOfType = (type) => list.find((event) => event?.type === type) || null;
      const share = firstOfType("share_info");
      const ask = firstOfType("ask_info");
      const agree = firstOfType("agree");
      const challenge = firstOfType("challenge");
      const suggest = firstOfType("suggest");
      const lead = share || ask || agree || challenge || suggest || list[0] || null;

      return {
        list,
        share,
        ask,
        agree,
        challenge,
        suggest,
        lead,
        leadItemLabel: lead?.item ? prettifyKey(lead.item) : ""
      };
    }

    function normalizeBackendEventType(type) {
      if (!type) return "hold";
      const map = {
        ask_info: "ask",
        share_info: "share",
        agree: "confirm",
        compliment: "confirm",
        suggest: "brainstorm",
        help: "share",
        say: "say",
        ignore: "ignore",
        insult: "insult"
      };
      return map[type] || type || "say";
    }

    function backendEventLabel(type, initialisedType) {
      const explicit = {
        ask_info: "ASK",
        share_info: "SHARE",
        agree: "CONFIRM",
        compliment: "CONFIRM",
        suggest: "IDEA",
        help: "SHARE",
        say: "SAY",
        ignore: "IGNORE",
        insult: "INSULT"
      };
      return explicit[type] || EVENT_META[initialisedType]?.label || titleCase(type || "say");
    }

    function buildAgentMap(agents, scenarioKey) {
      const templateAgents = SCENARIOS[scenarioKey]?.agents || [];
      const templateById = new Map(templateAgents.map((agent) => [agent.id, agent]));
      const fallbackPositions = [
        { x: 14, y: 88 },
        { x: 34, y: 62 },
        { x: 66, y: 62 },
        { x: 86, y: 88 }
      ];

      const result = {};
      (agents || []).forEach((agent, index) => {
        const template = templateById.get(agent.id) || templateAgents[index] || {};
        const avgTrust = averageTrustForAgent(agent);
        result[agent.id] = {
          ...template,
          ...agent,
          id: agent.id,
          name: agent.name || template.name || agent.id,
          role: agent.role || template.role || "Agent",
          x: template.x ?? fallbackPositions[index % fallbackPositions.length].x,
          y: template.y ?? fallbackPositions[index % fallbackPositions.length].y,
          color: template.color || "#2a78c5",
          skin: template.skin || "#efc9ae",
          hair: template.hair || "#5a4136",
          gender: template.gender || "m",
          mood: clamp(0.5 + ((agent.mood?.valence || 0) * 0.35) + (avgTrust * 0.25) - ((agent.stress || 0) * 0.25), 0.08, 0.94),
          trust_average: avgTrust,
          state: "idle"
        };
      });
      return result;
    }

    function summarizeEvent(event, agentsById) {
      if (!event) return "";
      const actor = agentsById[event.actor];
      const target = agentsById[event.target];
      const actorName = actor ? actor.name : (event.actor || "Agent");
      const targetName = target ? target.name : (event.target || "team");
      const text = event.text || titleCase(event.type);
      return actorName + " -> " + targetName + ": " + text;
    }

    function completedTasksBetween(previousTasks, currentTasks) {
      const previousByKey = new Map((previousTasks || []).map((task) => [task.key, task]));
      return (currentTasks || []).filter((task) => {
        const previous = previousByKey.get(task.key);
        return task.done && (!previous || !previous.done);
      });
    }

    function effectBullets(previousMetrics, nextMetrics, completedTasks, ended, endReason) {
      const bullets = [];
      if (completedTasks.length) {
        bullets.push({
          tone: "good",
          text: joinWithAnd(completedTasks.map((task) => task.completedLabel || task.label))
        });
      }

      if (!previousMetrics) {
        bullets.push({
          tone: "note",
          text: nextMetrics.progress > 0 ? "Progress: 0% → " + nextMetrics.progress + "%" : "Ready to begin"
        });
      } else if (nextMetrics.progress !== previousMetrics.progress) {
        bullets.push({
          tone: nextMetrics.progress > previousMetrics.progress ? "good" : "warn",
          text: "Progress " + previousMetrics.progress + "% -> " + nextMetrics.progress + "%"
        });
      } else {
        bullets.push({
          tone: "note",
          text: "Progress unchanged"
        });
      }

      if (previousMetrics) {
        const trustDelta = nextMetrics.averageTrust - previousMetrics.averageTrust;
        const stressDelta = nextMetrics.peakStress - previousMetrics.peakStress;
        if (Math.abs(trustDelta) > 0.005) {
          bullets.push({
            tone: trustDelta > 0 ? "good" : "warn",
            text: "Trust " + formatDelta(trustDelta)
          });
        }

        if (Math.abs(stressDelta) > 0.005) {
          bullets.push({
            tone: stressDelta < 0 ? "good" : "warn",
            text: "Peak stress " + formatDelta(stressDelta)
          });
        }

      }

      if (ended) {
        bullets.push({
          tone: endReason === "success" || endReason === "harmony" ? "good" : "warn",
          text: "Outcome: " + titleCase(endReason || "complete")
        });
      }

      return bullets.slice(0, 4);
    }

    function whyTitle(stepType, actor, target, completedTasks, ended, scenario, primaryEvent) {
      if (ended) return scenarioCompletionLabel(scenario);
      if (stepType === "hold") return "No new interaction this step";
      if (completedTasks.length) return completedTasks[0].completedLabel || completedTasks[0].label;
      const itemName = primaryEvent?.item ? prettifyKey(primaryEvent.item) : "information";
      if (stepType === "share") return itemName + " Shared";
      if (stepType === "ask") return itemName + " Requested";
      if (stepType === "refuse") return actor.name + " holds the handoff";
      if (stepType === "challenge") return itemName + " Under Review";
      if (stepType === "brainstorm") return actor.name + " suggests another option";
      return actor.name + " speaks to " + target.name;
    }

    function whyTrigger(blockerLabel, event, eventContext, ended, scenario, isPreStart) {
      if (ended) return "All required " + scenarioResolvedNoun(scenario) + " are complete.";
      if (blockerLabel === "Complete") return "No task is blocking progress right now.";
      if (eventContext?.ask && eventContext?.share && eventContext.ask.item === eventContext.share.item) {
        return eventContext.leadItemLabel + " remained blocked, so this step requested the missing detail and passed it to the next agent.";
      }
      if (eventContext?.share && eventContext?.agree && eventContext.share.item === eventContext.agree.item) {
        return eventContext.leadItemLabel + " was almost ready, so this step shared it and pushed it toward confirmation.";
      }
      if (eventContext?.challenge) {
        return eventContext.leadItemLabel + " is under pressure, so this step checks whether the current answer is reliable enough to use.";
      }
      if (!event) return isPreStart
        ? blockerLabel + " is the current blocker, so this is where the team needs to start."
        : blockerLabel + " is still the current blocker, so this step keeps the team aligned on that dependency.";
      const item = event.item ? prettifyKey(event.item) : blockerLabel;
      if (event.type === "share_info") return item + " is blocking progress, so the team is trying to pass the clue to the next person.";
      if (event.type === "ask_info") return item + " is still missing, so the team is requesting the detail it needs.";
      if (event.type === "challenge") return item + " is under pressure, so the team is checking whether the current answer is reliable.";
      if (event.type === "agree") return item + " is close to being locked in, so the team is confirming it before moving on.";
      return blockerLabel + " is the current blocker, so this step is still about clearing that dependency.";
    }

    function whyReasoning(event, eventContext, actor, target, isPreStart, agentMap) {
      if (!event) return isPreStart
        ? "Run is ready. No agent interaction recorded yet."
        : "No direct agent exchange landed this step, so the run carried the current blocker state forward.";
      if (eventContext?.ask && eventContext?.share && eventContext.ask.item === eventContext.share.item) {
        const asker = actorNameFromEvent({ agents: agentMap }, eventContext.ask, "the team");
        const sharer = actorNameFromEvent({ agents: agentMap }, eventContext.share, "the team");
        const receiver = targetNameFromEvent({ agents: agentMap }, eventContext.share, "the team");
        return sharer + " shared " + eventContext.leadItemLabel + " after " + asker + " asked for it, giving " + receiver + " the missing detail needed to continue.";
      }
      if (eventContext?.share && eventContext?.agree && eventContext.share.item === eventContext.agree.item) {
        const sharer = actorNameFromEvent({ agents: agentMap }, eventContext.share, "the team");
        const confirmer = actorNameFromEvent({ agents: agentMap }, eventContext.agree, "the team");
        return sharer + " surfaced " + eventContext.leadItemLabel + " and " + confirmer + " treated it as reliable enough to move the run forward.";
      }
      const item = event.item ? prettifyKey(event.item) : "the current blocker";
      if (event.type === "share_info") return actor.name + " shared the " + item + " so " + target.name + " has what's needed to move forward.";
      if (event.type === "ask_info") return actor.name + " requested the " + item + " from " + target.name + " because the team needs this missing detail.";
      if (event.type === "agree") return actor.name + " confirmed the " + item + " with " + target.name + ", locking it in and moving progress forward.";
      if (event.type === "challenge") return actor.name + " questioned the " + item + " with " + target.name + " to test whether it holds under pressure.";
      if (event.type === "suggest") return actor.name + " suggested a next move to " + target.name + " based on the current blocker.";
      return actor.name + " spoke to " + target.name + " about " + item + ".";
    }

    function whyImpact(previousMetrics, nextMetrics, completedTasks, ended, endReason, hasBackendEvent) {
      if (!previousMetrics) {
        return nextMetrics.progress > 0
          ? "The run already shows measurable progress at this point in the replay."
          : "This is the starting state before any step changes have landed.";
      }

      const shifts = [];

      if (nextMetrics.progress !== previousMetrics.progress) {
        shifts.push("Progress moved from " + previousMetrics.progress + "% to " + nextMetrics.progress + "%.");
      } else {
        shifts.push("Progress stays at " + nextMetrics.progress + "%.");
      }

      if (completedTasks.length) {
        shifts.push(joinWithAnd(completedTasks.map((task) => task.label)) + " is now complete.");
      }

      const trustDelta = nextMetrics.averageTrust - previousMetrics.averageTrust;
      const stressDelta = nextMetrics.peakStress - previousMetrics.peakStress;
      if (Math.abs(trustDelta) > 0.005) {
        shifts.push("Trust " + (trustDelta > 0 ? "rose" : "fell") + " slightly.");
      }
      if (Math.abs(stressDelta) > 0.005) {
        shifts.push("Peak stress " + (stressDelta > 0 ? "rose" : "eased") + " slightly.");
      } else if (!hasBackendEvent) {
        shifts.push("Peak stress stayed broadly steady because no new interaction landed.");
      }
      if (ended) {
        shifts.push("The run ended as " + titleCase(endReason || "complete") + ".");
      }

      return shifts.join(" ");
    }

    function initialSnapshotFromStatus(status) {
      return {
        tick: 0,
        agents: status.agents || [],
        ties: status.ties || [],
        events: [],
        metrics: status.metrics || {},
        group_state: status.group_state || {},
        scenario: status.scenario || {},
        ended: status.ended || false,
        end_reason: status.end_reason || ""
      };
    }

    function buildScenarioDisplay(status, scenarioKey) {
      const template = SCENARIOS[scenarioKey] || SCENARIOS.office;
      return {
        key: scenarioKey,
        label: status?.scenario?.name || template.label,
        sceneTitle: status?.scenario?.name || template.sceneTitle,
        intro: status?.scenario?.description || template.intro,
        goal: formatGoal(status?.config?.goal, scenarioKey),
        coordinator: template.coordinator,
        deputy: template.deputy
      };
    }

    function buildStep(snapshot, previousSnapshot, snapshots, stepIndex, scenarioDisplay, isSyntheticPreStart = false) {
      const isPreStart = isSyntheticPreStart;
      const scenarioKey = scenarioDisplay.key;
      const tasks = buildTaskRows(snapshot?.scenario?.tasks || {}, snapshot?.scenario?.knowledge_map || {}, scenarioKey);
      const previousTasks = previousSnapshot
        ? buildTaskRows(previousSnapshot?.scenario?.tasks || {}, previousSnapshot?.scenario?.knowledge_map || {}, scenarioKey)
        : [];
      const metrics = displayMetricsForSnapshot(snapshot, snapshots, stepIndex);
      const previousMetrics = previousSnapshot ? displayMetricsForSnapshot(previousSnapshot, snapshots, Math.max(0, stepIndex - 1)) : null;
      const stepEvents = snapshot?.events || [];
      const primaryEvent = pickPrimaryEvent(stepEvents);
      const eventContext = buildEventContext(stepEvents);
      const eventType = snapshot?.ended ? "wrap" : normalizeBackendEventType(primaryEvent?.type);
      const agentMap = buildAgentMap(snapshot?.agents || [], scenarioKey);
      const agentIds = Object.keys(agentMap);
      const actorId = primaryEvent?.actor || scenarioDisplay.coordinator || agentIds[0];
      const targetId = primaryEvent?.target || scenarioDisplay.deputy || agentIds.find((id) => id !== actorId) || actorId;
      const actor = agentMap[actorId] || agentMap[agentIds[0]];
      const target = agentMap[targetId] || actor;

      Object.values(agentMap).forEach((agent) => {
        agent.state = "idle";
      });
      if (actor) actor.state = eventType === "refuse" ? "refusing" : "speaking";
      if (target) target.state = eventType === "refuse" ? "waiting" : "listening";

      const completedTasks = previousSnapshot
        ? completedTasksBetween(previousTasks, tasks)
        : tasks.filter((task) => task.done);
      const blockerBeforeTask = firstIncompleteTask(previousTasks);
      const blockerAfterTask = firstIncompleteTask(tasks);
      const blockerBefore = blockerBeforeTask ? blockerBeforeTask.label : "Complete";
      const blockerAfter = blockerAfterTask ? blockerAfterTask.label : "Complete";
      const summaries = stepEvents.filter(Boolean).map((event) => summarizeEvent(event, agentMap)).filter(Boolean);
      const effectList = effectBullets(previousMetrics, metrics, completedTasks, snapshot?.ended, snapshot?.end_reason);

      // A step is "meaningful" for the Run Timeline if and only if it reflects a real
      // backend-observable moment: an actual event was emitted, a task was completed,
      // the run ended, or progress moved. Passive snapshots (no event, no task change,
      // no progress change) are still kept in RUN.steps so Play/Pause/Next/Prev and the
      // live tick counter stay faithful to the backend — but they are hidden from the
      // Run Timeline so cards like "No agent interaction recorded this step." don't
      // appear as standalone entries.
      const hasBackendEvent = Boolean(primaryEvent) || (snapshot?.events || []).length > 0;
      const progressChanged = previousMetrics ? (metrics.progress !== previousMetrics.progress) : (metrics.progress > 0);
      const taskStateChanged = previousSnapshot
        ? JSON.stringify(previousSnapshot?.scenario?.tasks || {}) !== JSON.stringify(snapshot?.scenario?.tasks || {})
        : false;
      const isMeaningful = Boolean(
        hasBackendEvent
        || completedTasks.length > 0
        || taskStateChanged
        || progressChanged
        || snapshot?.ended
      );

      return {
        tick: snapshot?.tick || 0,
        scenario: scenarioDisplay,
        metrics,
        previousMetrics,
        agents: agentMap,
        tasks,
        blockerBefore,
        blockerAfter,
        taskCompleted: completedTasks.length > 0,
        isMeaningful,
        hasBackendEvent,
        effectBullets: effectList,
        summaryLine: summaries.join(" · ") || (snapshot?.ended
          ? "Simulation complete."
          : isPreStart
            ? "Simulation ready. Press Play or Next to start."
            : "Agents held their positions this step."),
        eventLines: summaries,
        eventsRaw: stepEvents,
        whyTitle: whyTitle(eventType, actor, target, completedTasks, snapshot?.ended, scenarioDisplay, primaryEvent),
        whyTrigger: whyTrigger(blockerAfter, primaryEvent, eventContext, snapshot?.ended, scenarioDisplay, isPreStart),
        whyReasoning: whyReasoning(primaryEvent, eventContext, actor, target, isPreStart, agentMap),
        whyImpact: whyImpact(previousMetrics, metrics, completedTasks, snapshot?.ended, snapshot?.end_reason, hasBackendEvent),
        ended: Boolean(snapshot?.ended),
        endReason: snapshot?.end_reason || "",
        event: {
          type: eventType || "say",
          rawType: primaryEvent?.type || "",
          label: snapshot?.ended ? scenarioCompletionLabel(scenarioDisplay) : backendEventLabel(primaryEvent?.type, eventType),
          actorId: actor?.id || scenarioDisplay.coordinator,
          targetId: target?.id || scenarioDisplay.deputy,
          message: primaryEvent?.text || (snapshot?.ended
            ? scenarioWrapCopy(scenarioDisplay)
            : isPreStart
              ? "Waiting for the first agent interaction."
              : "No agent interaction recorded this step.")
        }
      };
    }

    function buildRunFromBackendStatus(status) {
      // Always reconcile CONFIG from backend truth before anything uses it, so every
      // scenario × team combination renders with its own templates. This closes the
      // pre-status window where CONFIG.scenarioKey could hold a stale default.
      reconcileConfigFromStatus(status);
      const scenarioKey = resolveScenarioKeyFromStatus(status);
      const teamKey = resolveTeamKeyFromStatus(status);
      const scenarioDisplay = buildScenarioDisplay(status, scenarioKey);
      const hasRealHistory = Boolean(status?.history?.length);
      const snapshots = hasRealHistory ? status.history : [initialSnapshotFromStatus(status)];
      const steps = snapshots.map((snapshot, index) => {
        const previousSnapshot = index > 0 ? snapshots[index - 1] : null;
        return buildStep(snapshot, previousSnapshot, snapshots, index, scenarioDisplay, !hasRealHistory && index === 0);
      });

      return {
        scenario: scenarioDisplay,
        team: TEAM_STYLES[teamKey] || TEAM_STYLES.smooth,
        seed: status?.seed,
        runId: status?.run_id || runId,
        mode: CONFIG.mode,
        status: status?.status || "idle",
        ended: Boolean(status?.ended || steps[steps.length - 1]?.ended),
        endReason: status?.end_reason || steps[steps.length - 1]?.endReason || "",
        savedToHistory: Boolean(status?.saved_to_history),
        steps,
        scenarioKey,
        teamKey,
        personalityTestResults: null,
        personalityResultsKey: ""
      };
    }

    function personalityTeamStyle(teamKey) {
      const map = {
        smooth: "smooth_team",
        tension: "tension_team",
        creative: "creative_team",
        pressure: "pressure_team"
      };
      return map[teamKey] || `${teamKey}_team`;
    }

    async function parseApiError(response) {
      const text = await response.text();
      if (!text) return `HTTP ${response.status}`;
      try {
        const data = JSON.parse(text);
        return data.detail || data.message || `HTTP ${response.status}`;
      } catch {
        return text;
      }
    }

    function setFooterMessage(message) {
      if (footerNote) footerNote.textContent = message;
    }

    async function fetchPersonalityTestResults(scenarioKey, teamKey, seed) {
      const teamStyle = personalityTeamStyle(teamKey);
      const params = new URLSearchParams();
      if (typeof seed === "number" && Number.isFinite(seed)) {
        params.set("seed", String(seed));
      }
      const suffix = params.toString() ? `?${params.toString()}` : "";
      const response = await fetch(`${API_BASE}/runs/personality-results/${scenarioKey}/${teamStyle}${suffix}`);
      if (!response.ok) {
        throw new Error(await parseApiError(response));
      }
      return response.json();
    }

    function rebuildRun(options = {}) {
      if (!rawRunState) return;
      const previousTick = RUN?.steps?.[currentIndex]?.tick;
      const previousResults = RUN?.personalityTestResults || null;
      const previousResultsKey = RUN?.personalityResultsKey || "";
      RUN = buildRunFromBackendStatus(rawRunState);
      if (!RUN?.steps?.length) return;
      RUN.personalityTestResults = previousResults;
      RUN.personalityResultsKey = previousResultsKey;

      const resultsKey = [RUN.scenarioKey, RUN.teamKey, RUN.seed].join("::");
      if (RUN.personalityResultsKey !== resultsKey) {
        RUN.personalityResultsKey = resultsKey;
        RUN.personalityTestResults = null;
        fetchPersonalityTestResults(RUN.scenarioKey, RUN.teamKey, RUN.seed)
          .then((results) => {
            if (!RUN || RUN.personalityResultsKey !== resultsKey) return;
            RUN.personalityTestResults = results;
            const step = currentStep();
            if (step) {
              renderWhy(step);
              renderMetrics(step);
            }
          })
          .catch((error) => {
            console.error("Could not fetch personality test results:", error);
            setFooterMessage("Live run loaded. Personality benchmark could not be loaded, but the dashboard is still showing real backend state.");
          });
      }

      if (options.forceLatest) {
        renderStep(RUN.steps.length - 1);
        return;
      }

      if (typeof previousTick === "number") {
        const matchingIndex = RUN.steps.findIndex((step) => step.tick === previousTick);
        if (matchingIndex >= 0) {
          renderStep(matchingIndex);
          return;
        }
      }

      renderStep(Math.min(currentIndex, RUN.steps.length - 1));
    }

    function mergeTickIntoStatus(diff) {
      if (!rawRunState) return;

      const history = Array.isArray(rawRunState.history) ? [...rawRunState.history] : [];
      if (history.length && history[history.length - 1]?.tick === diff.tick) {
        history[history.length - 1] = diff;
      } else {
        history.push(diff);
      }

      rawRunState = {
        ...rawRunState,
        tick: diff.tick,
        agents: diff.agents || rawRunState.agents,
        ties: diff.ties || rawRunState.ties,
        events: diff.events || rawRunState.events,
        metrics: diff.metrics || rawRunState.metrics,
        group_state: diff.group_state || rawRunState.group_state,
        scenario: diff.scenario || rawRunState.scenario,
        ended: diff.ended || false,
        end_reason: diff.end_reason || "",
        history,
        status: diff.ended ? "stopped" : rawRunState.status
      };
    }

    async function fetchRunStatus(activeRunId) {
      const response = await fetch(`${API_BASE}/runs/${activeRunId}`);
      if (!response.ok) {
        throw new Error(await parseApiError(response));
      }
      return response.json();
    }

    async function fetchSavedRunSummary(activeRunId) {
      const response = await fetch(`${API_BASE}/history/runs/${activeRunId}`);
      if (!response.ok) {
        throw new Error(await parseApiError(response));
      }
      return response.json();
    }

    async function fetchSavedRunReplay(activeRunId) {
      const response = await fetch(`${API_BASE}/history/runs/${activeRunId}/replay`);
      if (!response.ok) {
        throw new Error(await parseApiError(response));
      }
      return response.json();
    }

    function normalizeSavedReplayAgent(agent) {
      return {
        id: agent?.id || agent?.public_id || "Agent",
        name: agent?.name || agent?.id || agent?.public_id || "Agent",
        role: agent?.role || "Agent",
        trust: agent?.trust || {},
        stress: typeof agent?.stress === "number" ? agent.stress : (agent?.final_stress || 0),
        valence: typeof agent?.valence === "number" ? agent.valence : (agent?.final_valence || 0),
        mood: agent?.mood || { valence: typeof agent?.valence === "number" ? agent.valence : (agent?.final_valence || 0) },
        known_items: Array.isArray(agent?.known_items) ? agent.known_items : [],
        strategy: agent?.strategy || "steady"
      };
    }

    function adaptSavedRunToStatus(summary, replayPayload) {
      const history = Array.isArray(replayPayload?.history)
        ? replayPayload.history
        : (Array.isArray(summary?.history) ? summary.history : []);
      const lastSnapshot = history[history.length - 1] || {};
      const lastScenario = lastSnapshot?.scenario || {};
      const scenarioEnvironment = summary?.config?.environment
        || lastScenario?.environment
        || normalizeScenario(summary?.scenario_id);
      const topLevelAgents = Array.isArray(summary?.agents)
        ? summary.agents.map(normalizeSavedReplayAgent)
        : [];

      return {
        run_id: summary?.run_id || runId,
        status: "stopped",
        seed: summary?.seed,
        tick: summary?.ticks || lastSnapshot?.tick || history.length || 0,
        config: summary?.config || {},
        clients: 0,
        agents: Array.isArray(lastSnapshot?.agents) && lastSnapshot.agents.length
          ? lastSnapshot.agents
          : topLevelAgents,
        ties: lastSnapshot?.ties || [],
        events: lastSnapshot?.events || [],
        metrics: lastSnapshot?.metrics || summary?.metrics || {},
        group_state: lastSnapshot?.group_state || summary?.group_state || {},
        scenario: {
          id: summary?.scenario_id || lastScenario?.id || scenarioEnvironment,
          name: summary?.scenario_name || lastScenario?.name || titleCase(scenarioEnvironment),
          description: lastScenario?.description || "",
          environment: scenarioEnvironment,
          tasks: lastScenario?.tasks || summary?.tasks || {},
          knowledge_map: lastScenario?.knowledge_map || {},
          progress: typeof lastScenario?.progress === "number"
            ? lastScenario.progress
            : Number(summary?.final_progress || 1),
          outcome: lastScenario?.outcome || summary?.outcome || "",
          final_decision: lastScenario?.final_decision || null
        },
        history,
        ended: true,
        end_reason: summary?.outcome || lastSnapshot?.end_reason || "complete",
        saved_to_history: true
      };
    }

    async function fetchLiveOrSavedRunStatus(activeRunId) {
      try {
        return await fetchRunStatus(activeRunId);
      } catch (error) {
        if (!(error instanceof Error) || !error.message.includes("HTTP 404")) {
          throw error;
        }

        const [summary, replayPayload] = await Promise.all([
          fetchSavedRunSummary(activeRunId),
          fetchSavedRunReplay(activeRunId).catch(() => ({ history: [] }))
        ]);
        return adaptSavedRunToStatus(summary, replayPayload);
      }
    }

    async function createBackendRunFromLegacyParams() {
      const scenarioGoalMap = {
        office: "complete_proposal",
        cafe: "choose_restaurant",
        escape: "solve_puzzle"
      };
      const response = await fetch(`${API_BASE}/runs`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          environment: CONFIG.scenarioKey,
          goal: scenarioGoalMap[CONFIG.scenarioKey],
          team_type: CONFIG.teamKey
        })
      });

      if (!response.ok) {
        throw new Error(await parseApiError(response));
      }

      const data = await response.json();
      runId = data.run_id;
      const nextUrl = new URL(window.location.href);
      nextUrl.searchParams.set("run_id", runId);
      nextUrl.searchParams.set("mode", CONFIG.mode);
      window.history.replaceState({}, "", nextUrl);
      return runId;
    }

    async function ensureRunId() {
      if (runId) return runId;
      const hasLegacyScenario = PARAMS.has("scenario") || PARAMS.has("env");
      if (!hasLegacyScenario) {
        throw new Error("No backend run_id was provided. Start a run from Setup.");
      }
      return createBackendRunFromLegacyParams();
    }

    function websocketUrl(activeRunId) {
      return API_BASE.replace(/^http/, "ws") + `/runs/${activeRunId}/ws`;
    }

    function ensureSocket(activeRunId) {
      if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        return Promise.resolve(ws);
      }

      return new Promise((resolve, reject) => {
        ws = new WebSocket(websocketUrl(activeRunId));
        wsReady = false;

        ws.addEventListener("open", () => {
          wsReady = true;
          resolve(ws);
        }, { once: true });

        ws.addEventListener("error", () => {
          reject(new Error("Could not open live run socket."));
        }, { once: true });

        ws.addEventListener("message", async (messageEvent) => {
          let message;
          try {
            message = JSON.parse(messageEvent.data);
          } catch {
            return;
          }

          if (message.type === "tick") {
            const wasAtLatest = !RUN || currentIndex >= RUN.steps.length - 1 || playing;
            mergeTickIntoStatus(message.data);
            rebuildRun({ forceLatest: wasAtLatest });

            if (message.data.ended) {
              playing = false;
              playbackMode = "idle";
              playBtn.textContent = "Replay";
              try {
                rawRunState = await fetchRunStatus(runId);
                rebuildRun({ forceLatest: true });
              } catch {
                setFooterMessage("Run completed. Final state could not be refreshed — showing last known data.");
              }
            }
          }

          if (message.type === "status") {
            if (message.status === "auto_stopped") {
              playing = false;
              playbackMode = "idle";
              playBtn.textContent = RUN?.ended ? "Replay" : "Play";
              renderContext(currentStep());
            }
          }
        });

        ws.addEventListener("close", () => {
          wsReady = false;
        });
      });
    }

    function currentActionSupport(step) {
      if (step.event.type === "wrap") {
        return scenarioWrapCopy(step.scenario);
      }

      if (step.taskCompleted) {
        if (step.blockerAfter === "Complete") {
          return "That clears the last dependency and finishes the run.";
        }
        return "That clears this dependency and unlocks " + step.blockerAfter + ".";
      }

      if (step.event.type === "confirm") {
        return "No new task cleared on this step, but the team is more aligned.";
      }

      return "Progress is waiting on " + step.blockerAfter + ".";
    }

    function recentEventNote(step) {
      if (step.event.type === "wrap") return "Scenario finished.";
      if (step.taskCompleted) return "Progress moved to " + step.metrics.progress + "%.";
      if (step.event.type === "ask" || step.event.type === "refuse" || step.event.type === "challenge") {
        return "Progress stayed waiting.";
      }
      return "Team alignment changed on this step.";
    }

    function cloneAgents(agents) {
      const result = {};
      Object.keys(agents).forEach((id) => {
        result[id] = { ...agents[id] };
      });
      return result;
    }

    function cloneTasks(tasks) {
      return tasks.map((task) => ({ ...task }));
    }

    const contextScenario = document.getElementById("contextScenario");
    const contextTeam = document.getElementById("contextTeam");
    const contextTick = document.getElementById("contextTick");
    const contextStatus = document.getElementById("contextStatus");
    const contextNote = document.getElementById("contextNote");
    const runDetailsBtn = document.getElementById("runDetailsBtn");
    const modePill = document.getElementById("modePill");
    const taskProgressFill = document.getElementById("taskProgressFill");
    const progressHeroValue = document.getElementById("progressHeroValue");
    const progressHeroCount = document.getElementById("progressHeroCount");
    const taskList = document.getElementById("taskList");
    const blockerTitle = document.getElementById("blockerTitle");
    const blockerCopy = document.getElementById("blockerCopy");
    const logicLineA = document.getElementById("logicLineA");
    const logicLineB = document.getElementById("logicLineB");
    const sceneHeading = document.getElementById("sceneHeading");
    const sceneIntro = document.getElementById("sceneIntro");
    const sceneGoal = document.getElementById("sceneGoal");
    const sceneStage = document.getElementById("sceneStage");
    const sceneAgents = document.getElementById("sceneAgents");
    const sceneLinks = document.getElementById("sceneLinks");
    const sceneToken = document.getElementById("sceneToken");
    const eventStep = document.getElementById("eventStep");
    const eventSummary = document.getElementById("eventSummary");
    const eventType = document.getElementById("eventType");
    const eventMessage = document.getElementById("eventMessage");
    const eventEffects = document.getElementById("eventEffects");
    const whyTag = document.getElementById("whyTag");
    const whyTitleEl = document.getElementById("whyTitle");
    const whyTriggerEl = document.getElementById("whyTrigger");
    const whyReasoningEl = document.getElementById("whyReasoning");
    const whyImpactEl = document.getElementById("whyImpact");
    const whyEffects = document.getElementById("whyEffects");
    const agentFocus = document.getElementById("agentFocus");
    const logTimeline = document.getElementById("logTimeline");
    const timelineCounter = document.getElementById("timelineCounter");
    const timelinePrevBtn = document.getElementById("timelinePrev");
    const timelineNextBtn = document.getElementById("timelineNext");
    const metricProgressValue = document.getElementById("metricProgressValue");
    const metricProgressState = document.getElementById("metricProgressState");
    const metricProgressBar = document.getElementById("metricProgressBar");
    const metricProgressCopy = document.getElementById("metricProgressCopy");
    const metricTrustValue = document.getElementById("metricTrustValue");
    const metricTrustState = document.getElementById("metricTrustState");
    const metricTrustBar = document.getElementById("metricTrustBar");
    const metricTrustCopy = document.getElementById("metricTrustCopy");
    const metricStressValue = document.getElementById("metricStressValue");
    const metricStressState = document.getElementById("metricStressState");
    const metricStressBar = document.getElementById("metricStressBar");
    const metricStressCopy = document.getElementById("metricStressCopy");
    const metricAvgStressValue = document.getElementById("metricAvgStressValue");
    const metricAvgStressState = document.getElementById("metricAvgStressState");
    const metricAvgStressBar = document.getElementById("metricAvgStressBar");
    const metricAvgStressCopy = document.getElementById("metricAvgStressCopy");
    const metricConflictValue = document.getElementById("metricConflictValue");
    const metricConflictState = document.getElementById("metricConflictState");
    const metricConflictBar = document.getElementById("metricConflictBar");
    const metricConflictCopy = document.getElementById("metricConflictCopy");
    const metricTicksValue = document.getElementById("metricTicksValue");
    const metricTicksState = document.getElementById("metricTicksState");
    const metricTicksBar = document.getElementById("metricTicksBar");
    const metricTicksCopy = document.getElementById("metricTicksCopy");
    const footerNote = document.getElementById("footerNote");
    const viewSwitch = document.getElementById("viewSwitch");
    const viewLive = document.getElementById("viewLive");
    const viewLog = document.getElementById("viewLog");
    const playBtn = document.getElementById("playBtn");
    const exportResultsBtn = document.getElementById("exportResultsBtn");
    const doneExportBtn = document.getElementById("doneExportBtn");
    const historyLink = document.getElementById("historyLink");
    const doneHistoryBtn = document.getElementById("doneHistoryBtn");
    let runDetailsOpen = false;

    function totalRunTicks() {
      if (!RUN?.steps?.length) return 0;
      return RUN.steps[RUN.steps.length - 1].tick || 0;
    }

    function stepPositionLabel(step) {
      const totalTicks = totalRunTicks();
      if (step.tick === 0 && totalTicks === 0) return "Ready";
      if (step.tick === 0) return "Start";
      return "Step " + step.tick + " of " + Math.max(totalTicks, step.tick);
    }

    function syncRunDetails() {
      if (!RUN) return;
      const historyNote = RUN.savedToHistory ? " · Saved in History" : "";
      contextNote.textContent = "Run ID " + RUN.runId + " · Seed " + RUN.seed + historyNote;
      contextNote.classList.toggle("is-open", runDetailsOpen);
      runDetailsBtn.textContent = runDetailsOpen ? "Hide details" : "Run details";
      runDetailsBtn.setAttribute("aria-expanded", String(runDetailsOpen));
      historyLink.href = `history.html?run=${encodeURIComponent(RUN.runId)}`;
      doneHistoryBtn.disabled = !RUN.savedToHistory;
    }

    function buildRunExportPayload() {
      if (!RUN) return null;
      const finalStep = RUN.steps[RUN.steps.length - 1];
      return {
        export_type: "simulation_run",
        exported_at: new Date().toISOString(),
        source: "backend_dashboard",
        run: {
          run_id: RUN.runId,
          seed: RUN.seed,
          scenario: {
            id: RUN.scenario.key,
            name: RUN.scenario.label,
            title: RUN.scenario.sceneTitle
          },
          team_style: RUN.team.label,
          experience: RUN.mode,
          total_steps: finalStep.tick,
          progress: finalStep.metrics.progress,
          team_trust: finalStep.metrics.averageTrust,
          highest_stress: finalStep.metrics.peakStress,
          team_conflict: finalStep.metrics.conflict,
          outcome: outcomeLabel(),
          timeline_events: RUN.steps.map((step) => {
            const actor = step.agents[step.event.actorId];
            const target = step.agents[step.event.targetId];
            return {
              step: step.tick,
              action_type: step.event.type,
              action_label: step.event.label,
              speaker: actor ? actor.name : step.event.actorId,
              receiver: target ? target.name : step.event.targetId,
              message: step.event.message,
              summary: step.summaryLine,
              backend_events: step.eventsRaw,
              progress: step.metrics.progress,
              team_trust: step.metrics.averageTrust,
              highest_stress: step.metrics.peakStress,
              team_conflict: step.metrics.conflict,
              why: {
                trigger: step.whyTrigger,
                reason: step.whyReasoning,
                impact: step.whyImpact
              },
              effects: step.effectBullets
            };
          })
        }
      };
    }

    function exportCurrentRun() {
      if (!RUN) return;
      const payload = buildRunExportPayload();
      window.SimuVerseExport.downloadJson(
        `simuverse-run-${window.SimuVerseExport.slugify(RUN.scenario.label)}-${window.SimuVerseExport.timestamp()}.json`,
        payload
      );
    }

    function currentStep() {
      return RUN?.steps?.[currentIndex] || null;
    }

    function deriveStepMetrics(step, index = currentIndex) {
      if (!step) {
        return {
          progress: 0,
          averageTrust: 0,
          averageStress: 0,
          peakStress: 0,
          conflict: 0
        };
      }

      const tasks = Array.isArray(step.tasks) ? step.tasks : [];
      const agents = Object.values(step.agents || {});
      const progress = taskProgress(tasks);
      const averageTrust = agents.length
        ? average(agents.map((agent) => {
            if (typeof agent.trust_average === "number") return agent.trust_average;
            return averageTrustForAgent(agent);
          }))
        : (step.metrics?.averageTrust || 0);
      const averageStress = agents.length
        ? average(agents.map((agent) => agent.stress || 0))
        : (step.metrics?.averageStress || 0);

      const peakStress = agents.length
        ? agents.reduce((maxSeen, agent) => Math.max(maxSeen, agent.stress || 0), 0)
        : (step.metrics?.peakStress || 0);

      return {
        progress,
        averageTrust,
        averageStress,
        peakStress,
        conflict: typeof step.metrics?.conflict === "number" ? step.metrics.conflict : 0
      };
    }

    function statusLabel() {
      if (!RUN) return "Loading";
      if (playing && playbackMode === "backend-auto") return "Running";
      if (playing && playbackMode === "local-replay") return "Replaying";
      if (RUN.ended && currentIndex >= RUN.steps.length - 1) {
        return titleCase(RUN.endReason || "complete");
      }
      if (currentIndex < RUN.steps.length - 1) return "Reviewing";
      return "Paused";
    }

    function renderContext(step) {
      if (!RUN || !step) return;
      contextScenario.textContent = RUN.scenario.label;
      contextTeam.textContent = RUN.team.label;
      contextTick.textContent = stepPositionLabel(step);
      contextStatus.textContent = statusLabel();
      syncRunDetails();

      const pauseEl = document.getElementById("pauseBtn");
      if (RUN.ended) {
        if (!playing) playBtn.textContent = "Replay";
        if (pauseEl) pauseEl.style.display = "none";
      } else {
        if (!playing) playBtn.textContent = "Play";
        if (pauseEl) pauseEl.style.display = "";
      }
      modePill.textContent = "Mode: " + modeLabel(RUN.mode);
      sceneHeading.textContent = RUN.scenario.sceneTitle;
      sceneIntro.textContent = RUN.scenario.intro;
      sceneGoal.textContent = RUN.scenario.goal;
      footerNote.textContent = "Everything shown here is loaded from the real simulation state and its saved step history.";
    }

    function renderTasks(step) {
      if (!step) return;
      const currentMetrics = deriveStepMetrics(step);
      taskProgressFill.style.width = currentMetrics.progress + "%";
      const totalTasks = step.tasks.length;
      const doneTasks = step.tasks.filter((t) => t.done).length;
      if (progressHeroValue) progressHeroValue.textContent = String(currentMetrics.progress);
      if (progressHeroCount) {
        progressHeroCount.textContent =
          totalTasks > 0
            ? `${doneTasks} of ${totalTasks} ${totalTasks === 1 ? "task" : "tasks"}`
            : "No tasks yet";
      }
      taskList.innerHTML = step.tasks.map((task) => {
        const blockerClass = !task.done && task.label === step.blockerAfter ? "is-blocker" : "";
        const doneClass = task.done ? "is-done" : "";
        const taskName = taskDisplayLabel(task);
        const meta = taskStatusMeta(task, step);

        return `
          <div class="task-row ${doneClass} ${blockerClass}">
            <div class="task-bullet"></div>
            <div>
              <div class="task-topline">
                <div class="task-name">${taskName}</div>
                <div class="task-status ${meta.statusTone}">${meta.statusText}</div>
              </div>
              ${meta.detail ? `<div class="task-owner">${meta.detail}</div>` : ""}
            </div>
          </div>
        `;
      }).join("");

      if (step.blockerAfter === "Complete") {
        const key = RUN.scenario.key;
        if (key === "escape") {
          blockerTitle.textContent = "All Clues Confirmed";
          blockerCopy.textContent = "Every required clue is complete, so the team can escape the room.";
        } else if (key === "cafe") {
          blockerTitle.textContent = "All Plans Set";
          blockerCopy.textContent = "Every plan detail is confirmed, so the cafe is ready to open.";
        } else {
          blockerTitle.textContent = "All Tasks Complete";
          blockerCopy.textContent = "Every required task is done, so the project can ship.";
        }
      } else {
        const activeTask = step.tasks.find((task) => task.label === step.blockerAfter);
        // Find who needs to ACT NEXT: look at the latest event for this blocker
        const blockerEvents = (step.eventsRaw || []).filter((event) => event?.item === activeTask?.key);
        const latestEvent = blockerEvents.length ? blockerEvents[blockerEvents.length - 1] : null;
        let nextActor = null;
        let actionVerb = "resolve";

        if (latestEvent?.type === "share_info") {
          nextActor = step.agents?.[latestEvent.target];
          actionVerb = "confirm";
        } else if (latestEvent?.type === "ask_info") {
          nextActor = step.agents?.[latestEvent.actor];
          actionVerb = "provide";
        } else {
          nextActor = activeTask ? step.agents?.[activeTask.owner] : null;
        }

        const nextActorName = nextActor ? nextActor.name : "the team";
        blockerTitle.textContent = "NEXT REQUIRED ACTION";
        blockerCopy.textContent = nextActorName + " must " + actionVerb + " " + step.blockerAfter;
      }

      const previousMetrics = step.previousMetrics;
      const progressDelta = previousMetrics ? currentMetrics.progress - previousMetrics.progress : currentMetrics.progress;
      const trustDelta = previousMetrics ? currentMetrics.averageTrust - previousMetrics.averageTrust : 0;
      const stressDelta = previousMetrics ? currentMetrics.peakStress - previousMetrics.peakStress : 0;

      logicLineA.textContent = "Progress is " + currentMetrics.progress + "% with "
        + doneTasks + " of " + totalTasks + " "
        + (totalTasks === 1 ? "task" : "tasks")
        + " complete"
        + (previousMetrics
          ? " (" + (progressDelta >= 0 ? "+" : "") + progressDelta + "% this step)."
          : ".");
      logicLineB.textContent = "This step left trust at " + currentMetrics.averageTrust.toFixed(2)
        + " (" + formatDelta(trustDelta) + ") and peak stress at " + currentMetrics.peakStress.toFixed(2)
        + " (" + formatDelta(stressDelta) + ").";
    }

    function scenePosition(agent) {
      return {
        x: agent.x,
        y: Math.min(agent.y, 64)
      };
    }

    function drawLine(actor, target, event) {
      const type = event?.type || "say";
      if (!actor || !target || type === "wrap") {
        sceneLinks.innerHTML = "";
        return;
      }

      const typeColor = type === "share" || type === "confirm"
        ? "#1f8f83"
        : type === "ask" || type === "say"
          ? "#2a78c5"
          : type === "wrap" || type === "brainstorm"
            ? "#b97418"
            : "#c84a4a";

      const actorPos = scenePosition(actor);
      const targetPos = scenePosition(target);
      const x1 = actorPos.x * 10;
      const y1 = actorPos.y * 6.1;
      const x2 = targetPos.x * 10;
      const y2 = targetPos.y * 6.1;
      const curveY = Math.min(y1, y2) - 90;
      const path = `M${x1} ${y1} Q ${(x1 + x2) / 2} ${curveY} ${x2} ${y2}`;
      const labelX = (x1 + x2) / 2;
      const labelY = curveY - 14;
      const itemLabel = event?.item ? prettifyKey(event.item) : "";
      const agentLabel = actor.name + " → " + target.name;
      let actionLabel = "";

      if (itemLabel) {
        actionLabel = type === "share" || type === "confirm" ? itemLabel + " shared"
          : type === "ask" ? itemLabel + " requested"
          : type === "challenge" ? itemLabel + " checked"
          : "Interaction on " + itemLabel;
      }

      const lineLabel = itemLabel ? (agentLabel + ": " + actionLabel) : agentLabel;

      sceneLinks.innerHTML = `
        <defs>
          <filter id="line-glow" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="3" result="blur"></feGaussianBlur>
            <feMerge>
              <feMergeNode in="blur"></feMergeNode>
              <feMergeNode in="SourceGraphic"></feMergeNode>
            </feMerge>
          </filter>
          <marker id="arrow-head" markerWidth="18" markerHeight="18" refX="10" refY="9" orient="auto">
            <path d="M0 0 L18 9 L0 18 L4 9 Z" fill="${typeColor}"></path>
          </marker>
        </defs>
        <path d="${path}"
          fill="none"
          stroke="${typeColor}"
          stroke-opacity="0.18"
          stroke-width="11"
          stroke-linecap="round">
        </path>
        <path d="${path}"
          fill="none"
          stroke="${typeColor}"
          stroke-opacity="0.95"
          stroke-width="4.5"
          stroke-linecap="round"
          stroke-dasharray="${type === "share" || type === "confirm" ? "0" : "12 10"}"
          filter="url(#line-glow)"
          marker-end="url(#arrow-head)">
          <animate attributeName="stroke-dashoffset" from="22" to="0" dur="0.7s" repeatCount="indefinite"></animate>
        </path>
        <!-- Solid start dot marks the SPEAKER clearly -->
        <circle cx="${x1}" cy="${y1}" r="8" fill="${typeColor}" opacity="0.95" stroke="#fff" stroke-width="2"></circle>
        <!-- Receiver ring reinforces the end point -->
        <circle cx="${x2}" cy="${y2}" r="8" fill="#ffffff" opacity="0.98" stroke="${typeColor}" stroke-width="3"></circle>
        <!-- Travelling pulse conveys motion toward the receiver -->
        <circle r="6" fill="${typeColor}" opacity="0.95" stroke="#fff" stroke-width="1.5">
          <animateMotion dur="1.1s" repeatCount="indefinite" path="${path}"></animateMotion>
        </circle>
        <g>
          <rect x="${labelX - 74}" y="${labelY - 16}" width="148" height="24" rx="12" fill="rgba(255,255,255,0.94)" stroke="${typeColor}" stroke-opacity="0.22"></rect>
          <text x="${labelX}" y="${labelY}" text-anchor="middle" font-size="13" font-weight="800" fill="#17324d">${lineLabel.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")}</text>
        </g>
      `;
    }

    function renderScene(step) {
      if (!step) return;
      const event = step.event;
      const actor = step.agents[event.actorId];
      const target = step.agents[event.targetId];
      sceneStage.dataset.scenario = RUN.scenario.key;

      // A scene only shows speaker/receiver chips and a speech bubble when the
      // backend actually produced an event, or the run ended (which carries real
      // scenario completion copy). Passive snapshots render agents in idle state
      // with no bubble — so "No agent interaction recorded this step." never
      // appears in the animation either.
      const sceneHasAction = Boolean(step.hasBackendEvent) || event.type === "wrap";

      sceneAgents.innerHTML = Object.values(step.agents).map((agent, index) => {
        const mood = moodLabel(agent.mood);
        const pos = scenePosition(agent);
        const isActor = sceneHasAction && agent.id === event.actorId;
        const isTarget = sceneHasAction && agent.id === event.targetId;
        const isWrap = event.type === "wrap";
        const isCoordinator = agent.id === RUN.scenario.coordinator;
        const showDetail = !isWrap && (isActor || isTarget);
        const idleDelay = (-0.32 * index).toFixed(2);
        const bubbleTop = pos.y <= 50 ? 22 : 10;
        let bubbleLeft = 50;
        let bubbleTail = 50;
        if (pos.y <= 50) {
          bubbleLeft = pos.x < 50 ? 60 : 40;
          bubbleTail = pos.x < 50 ? 42 : 58;
        } else if (pos.x <= 28) {
          bubbleLeft = 34;
          bubbleTail = 28;
        } else if (pos.x >= 72) {
          bubbleLeft = 66;
          bubbleTail = 72;
        }
        const emphasisClass = isWrap
          ? (isActor ? "actor-focus" : "team-focus")
          : isActor
            ? "actor-focus"
            : isTarget
              ? "target-focus"
              : "dimmed";
        const receivingAction = event.type === "share" || event.type === "confirm" || event.type === "brainstorm" || event.type === "say" || event.type === "wrap";
        const stateChip = isWrap
          ? (isActor ? `<div class="agent-state-chip speaker">Team-wide</div>` : "")
          : isActor
            ? `<div class="agent-state-chip speaker">${agent.id} sends</div>`
            : isTarget
              ? `<div class="agent-state-chip ${receivingAction ? "receiver" : "waiting"}">${agent.id} receives</div>`
              : "";
        const bubble = (sceneHasAction && agent.id === event.actorId && event.message) ? `
          <div class="speech-bubble" style="left: ${bubbleLeft}%; top: ${bubbleTop}px; --bubble-tail:${bubbleTail}%;">
            <div class="speech-head"><span>${agent.name} · ${agent.role}</span><span class="speech-tag">${event.label}</span></div>
            <div>${event.message}</div>
          </div>
        ` : "";
        const skin = agent.skin || "#f3cfb2";
        const hair = agent.hair || "#5f4638";
        const shirt = agent.color;
        const eyeColour = agent.eyeColour || "#2c5fa8";
        const isFemale = agent.gender === "f";

        const hairBack = isFemale
          ? `<path d="M34 60 C34 28, 50 10, 70 10 C90 10, 106 28, 106 60 L106 104 Q99 101 95 106 L95 64 Q88 72, 70 72 Q52 72, 45 64 L45 106 Q41 101, 34 104 Z" fill="${hair}"/>`
          : `<path d="M40 52 C40 30, 54 16, 70 16 C86 16, 100 30, 100 52 L100 70 Q90 66, 70 66 Q50 66, 40 70 Z" fill="${hair}"/>`;

        const hairFront = isFemale
          ? `<path d="M46 45 C50 28, 60 18, 70 18 C84 18, 94 28, 97 45 C88 38, 79 40, 70 43 C61 40, 52 38, 46 45 Z" fill="${hair}"/>
             <path d="M52 31 Q61 24, 73 27" stroke="rgba(255,255,255,0.18)" stroke-width="2" fill="none" stroke-linecap="round"/>`
          : `<path d="M46 44 C50 30, 59 22, 70 22 C81 22, 90 30, 94 44 C86 38, 78 40, 70 42 C62 40, 54 38, 46 44 Z" fill="${hair}"/>
             <path d="M60 30 Q69 25, 80 31" stroke="rgba(255,255,255,0.16)" stroke-width="1.5" fill="none" stroke-linecap="round"/>`;

        const earrings = isFemale
          ? `<circle cx="43" cy="72" r="1.3" fill="#fff" stroke="rgba(0,0,0,0.18)" stroke-width="0.4"/>
             <circle cx="97" cy="72" r="1.3" fill="#fff" stroke="rgba(0,0,0,0.18)" stroke-width="0.4"/>`
          : "";

        const eyebrowStrokeW = isFemale ? 2.0 : 2.6;

        const mouthClosed = isFemale
          ? `<path class="mouth-closed" d="M62 84 Q70 88, 78 84 Q74 87, 70 87 Q66 87, 62 84 Z" fill="#c53030"/>`
          : `<path class="mouth-closed" d="M63 85 Q70 87, 77 85" stroke="#7a3b3b" stroke-width="2" fill="none" stroke-linecap="round"/>`;

        const mouthOpen = isFemale
          ? `<ellipse class="mouth-open" cx="70" cy="86" rx="5" ry="3.2" fill="#7a1d1d"/>`
          : `<ellipse class="mouth-open" cx="70" cy="86" rx="4.5" ry="2.8" fill="#5a1e1e"/>`;

        // Slight facial hair hint for males
        const stubble = !isFemale
          ? `<path d="M55 80 Q70 84, 85 80" stroke="${hair}" stroke-width="1" fill="none" opacity="0.22" stroke-linecap="round"/>`
          : "";

        const avatar = `
          <div class="agent-avatar" style="--avatar-shirt:${shirt}; --avatar-skin:${skin}; --avatar-hair:${hair}; --idle-delay:${idleDelay}s;">
            <svg class="avatar-portrait" viewBox="0 0 140 160" xmlns="http://www.w3.org/2000/svg">
              <!-- Shoulders / shirt -->
              <path d="M5 160 C5 118, 28 104, 70 104 C112 104, 135 118, 135 160 Z" fill="${shirt}"/>
              <path d="M55 104 Q70 128, 85 104 Z" fill="rgba(0,0,0,0.08)"/>
              <path d="M10 155 C14 130, 32 118, 55 116" stroke="rgba(255,255,255,0.22)" stroke-width="3" fill="none" stroke-linecap="round"/>

              <!-- Neck -->
              <path d="M59 92 L59 112 Q70 118, 81 112 L81 92 Z" fill="${skin}"/>
              <path d="M59 104 Q70 112, 81 104 L81 110 Q70 116, 59 110 Z" fill="rgba(0,0,0,0.12)"/>

              <!-- Hair back (gender specific) -->
              ${hairBack}

              <!-- Face -->
              <ellipse cx="70" cy="62" rx="27" ry="33" fill="${skin}"/>

              <!-- Ears -->
              <ellipse cx="43" cy="66" rx="4" ry="7" fill="${skin}"/>
              <ellipse cx="97" cy="66" rx="4" ry="7" fill="${skin}"/>
              ${earrings}

              <!-- Hair front (gender specific) -->
              ${hairFront}

              <!-- Eyebrows -->
              <path d="M50 54 Q57 50, 64 54" stroke="#3b2a1a" stroke-width="${eyebrowStrokeW}" fill="none" stroke-linecap="round"/>
              <path d="M76 54 Q83 50, 90 54" stroke="#3b2a1a" stroke-width="${eyebrowStrokeW}" fill="none" stroke-linecap="round"/>

              <!-- Eyes -->
              <g class="eyes">
                <ellipse cx="57" cy="62" rx="3.8" ry="4.6" fill="#fff" stroke="rgba(0,0,0,0.35)" stroke-width="0.6"/>
                <ellipse cx="83" cy="62" rx="3.8" ry="4.6" fill="#fff" stroke="rgba(0,0,0,0.35)" stroke-width="0.6"/>
                <circle cx="57" cy="63" r="2.4" fill="${eyeColour}"/>
                <circle cx="83" cy="63" r="2.4" fill="${eyeColour}"/>
                <circle cx="58" cy="62" r="0.8" fill="#fff"/>
                <circle cx="84" cy="62" r="0.8" fill="#fff"/>
              </g>

              <!-- Nose -->
              <path d="M70 68 Q67 76, 70 78 Q73 76, 70 68" stroke="#d49c82" stroke-width="1" fill="none" stroke-linecap="round"/>

              <!-- Blush -->
              <ellipse cx="52" cy="76" rx="4" ry="2.4" fill="#f4a5a5" opacity="${isFemale ? 0.45 : 0.22}"/>
              <ellipse cx="88" cy="76" rx="4" ry="2.4" fill="#f4a5a5" opacity="${isFemale ? 0.45 : 0.22}"/>

              ${stubble}

              <!-- Mouth variants -->
              ${mouthClosed}
              ${mouthOpen}
            </svg>
          </div>
        `;

        return `
          <div class="agent-node ${agent.state} ${emphasisClass}" style="left:${pos.x}%; top:${pos.y}%; --agent-accent:${agent.color};">
            <div class="agent-card-visual">
              ${bubble}
              ${showDetail ? `<div class="agent-badge">${mood}</div>` : ""}
              <div class="agent-ring"></div>
              ${avatar}
            </div>
            <div class="agent-nameplate">
              <div class="agent-name">${agent.name}${isCoordinator ? ' <span class="coordinator-badge">Lead</span>' : ''}</div>
              <div class="agent-role">${agent.role}</div>
              ${stateChip ? `<div class="agent-state-line">${stateChip}</div>` : ""}
              ${agent.personality ? `<div class="agent-personality">${agent.personality}</div>` : ""}
              ${showDetail ? `<div class="agent-stats">Stress ${(agent.stress || 0).toFixed(2)} · Trust ${(agent.trust_average || 0).toFixed(2)}</div>` : ""}
            </div>
          </div>
        `;
      }).join("");

      drawLine(actor, target, event);

      sceneToken.style.display = "none";
    }

    function renderEventStrip(step) {
      if (!step) return;
      const sceneHasAction = Boolean(step.hasBackendEvent) || step.event.type === "wrap";
      const actionLabel = step.event.type === "wrap" ? scenarioCompletionLabel(step.scenario) : step.event.label;

      // Header: "CURRENT STEP — Step N of M"
      eventStep.textContent = "CURRENT STEP — " + stepPositionLabel(step);

      // Action type badge + explanation
      if (sceneHasAction) {
        eventSummary.textContent = actionLabel;
        eventType.textContent = actionLabel;
        eventType.className = "event-type " + step.event.type;

        // Build rich event description
        let eventDesc = renderEventMessageHtml(step);
        const primaryEvent = step.eventsRaw?.[0];
        const actor = step.agents?.[primaryEvent?.actor];
        const target = step.agents?.[primaryEvent?.target];

        // If no raw event text, construct description from event type + item
        if (!primaryEvent?.text && actor && target && primaryEvent?.item) {
          const itemLabel = prettifyKey(primaryEvent.item);
          if (primaryEvent.type === "share_info") {
            eventDesc = `<div class="event-message-text">${actor.name} shares the ${itemLabel} with ${target.name}. The information has been delivered, but progress will only advance once ${target.name} confirms it.</div>`;
          } else if (primaryEvent.type === "ask_info") {
            eventDesc = `<div class="event-message-text">${actor.name} requests the ${itemLabel} from ${target.name}. The team is waiting for the missing detail needed to continue.</div>`;
          } else if (primaryEvent.type === "agree") {
            eventDesc = `<div class="event-message-text">${actor.name} confirms the ${itemLabel} with ${target.name}. This locks in the clue and moves progress forward.</div>`;
          } else if (primaryEvent.type === "challenge") {
            eventDesc = `<div class="event-message-text">${actor.name} questions the ${itemLabel} with ${target.name}. The team is testing whether the current answer is reliable enough.</div>`;
          }
        }

        eventMessage.innerHTML = eventDesc;
      } else {
        eventSummary.textContent = "Holding";
        eventType.textContent = "HOLD";
        eventType.className = "event-type hold";
        eventMessage.innerHTML = `<div class="event-message-text">No new interaction this step — team alignment remained steady.</div>`;
      }

      // Effect badges showing what changed
      eventEffects.innerHTML = step.effectBullets.map((bullet) => (
        `<span class="effect-chip ${bullet.tone}">${bullet.text}</span>`
      )).join("");
    }

    function renderLiveTimeline(stepIndex) {
      if (!document.getElementById("liveTimeline")) return;
      const liveTimeline = document.getElementById("liveTimeline");
      const items = RUN.steps.slice(Math.max(0, stepIndex - 2), stepIndex + 1);
      liveTimeline.innerHTML = items.map((step, index) => `
        <article class="live-timeline-item ${index === items.length - 1 ? "active" : ""}">
          <div class="live-timeline-top">
            <div class="live-timeline-tick">${stepPositionLabel(step)}</div>
            <div class="live-timeline-type">${step.event.label}</div>
          </div>
          <div class="live-timeline-text">${step.summaryLine}</div>
          <div class="live-timeline-note">${recentEventNote(step)}</div>
        </article>
      `).join("");
    }

    function renderWhy(step) {
      if (!step) return;
      const index = RUN?.steps?.indexOf(step) ?? currentIndex;
      const previousStep = index > 0 ? RUN.steps[index - 1] : null;
      const primaryEvent = pickPrimaryEvent(step.eventsRaw || []);
      const eventContext = buildEventContext(step.eventsRaw || []);
      const eventType = step.ended ? "wrap" : normalizeBackendEventType(primaryEvent?.type);
      const completedTasks = previousStep
        ? completedTasksBetween(previousStep.tasks || [], step.tasks || [])
        : (step.tasks || []).filter((task) => task.done);
      const actor = step.agents && step.event ? step.agents[step.event.actorId] : null;
      const target = step.agents && step.event ? step.agents[step.event.targetId] : null;
      const currentMetrics = deriveStepMetrics(step, index);
      const previousMetrics = step.previousMetrics || (previousStep ? deriveStepMetrics(previousStep, index - 1) : null);

      const liveWhyTitle = whyTitle(eventType, actor, target, completedTasks, step.ended, step.scenario, primaryEvent);
      const liveWhyTrigger = whyTrigger(step.blockerAfter, primaryEvent, eventContext, step.ended, step.scenario, step.tick === 0);
      const liveWhyReasoning = whyReasoning(primaryEvent, eventContext, actor, target, step.tick === 0, step.agents || {});
      const liveWhyImpact = whyImpact(previousMetrics, currentMetrics, completedTasks, step.ended, step.endReason, step.hasBackendEvent);
      const liveEffects = effectBullets(previousMetrics, currentMetrics, completedTasks, step.ended, step.endReason);

      if (whyTag) whyTag.textContent = stepPositionLabel(step) + " · " + ((step.event && step.event.label) || "");
      if (whyTitleEl) whyTitleEl.textContent = liveWhyTitle || "";
      if (whyTriggerEl) whyTriggerEl.textContent = liveWhyTrigger || "";
      if (whyReasoningEl) whyReasoningEl.textContent = liveWhyReasoning || "";
      if (whyImpactEl) {
        whyImpactEl.textContent = liveWhyImpact || "";
      }
      if (whyEffects) whyEffects.innerHTML = liveEffects.map((bullet) => (
        `<div class="log-effect ${bullet.tone}">${bullet.text}</div>`
      )).join("");
    }

    function focusCard(agent, roleLabel, contextCopy) {
      if (!agent) return "";
      return `
        <div class="focus-card">
          <div class="focus-role">${roleLabel}</div>
          <div class="focus-name">${agent.name} · ${agent.role}</div>
          <div class="focus-stat">${contextCopy}</div>
          <div class="focus-stats">
            <div class="focus-stat"><strong>Trust</strong> ${(agent.trust_average || 0).toFixed(2)} · <strong>Stress</strong> ${(agent.stress || 0).toFixed(2)} · <strong>Mood</strong> ${moodLabel(agent.mood)}</div>
          </div>
        </div>
      `;
    }

    function renderFocus(step) {
      const actor = step.agents && step.event && step.agents[step.event.actorId];
      const target = step.agents && step.event && step.agents[step.event.targetId];
      if (!actor && !target) {
        if (agentFocus) agentFocus.innerHTML = "";
        return;
      }
      const actorCopy = !actor ? "" : step.event.type === "share"
        ? actor.name + " is sending the missing input."
        : step.event.type === "refuse"
          ? actor.name + " is holding the dependency."
          : actor.name + " is leading this step.";
      const targetCopy = !target ? "" : step.event.type === "share"
        ? target.name + " receives the handoff."
        : target.name + " is the other active agent.";

      if (agentFocus) agentFocus.innerHTML =
        focusCard(actor, "Driving", actorCopy) +
        focusCard(target, "Receiving", targetCopy);
    }

    function renderMetrics(step) {
      if (!step) return;
      const currentMetrics = deriveStepMetrics(step);
      const previousMetrics = step.previousMetrics || null;
      const progressDelta = previousMetrics ? currentMetrics.progress - previousMetrics.progress : 0;
      const trustDelta = previousMetrics ? currentMetrics.averageTrust - previousMetrics.averageTrust : 0;
      const avgStressDelta = previousMetrics ? currentMetrics.averageStress - previousMetrics.averageStress : 0;
      const peakStressDelta = previousMetrics ? currentMetrics.peakStress - previousMetrics.peakStress : 0;
      const conflictDelta = previousMetrics ? currentMetrics.conflict - (previousMetrics.conflict || 0) : 0;
      const progressInfo = progressMeaning(currentMetrics.progress);
      const trustInfo = trustMeaning(currentMetrics.averageTrust);
      const avgStressInfo = stressMeaning(currentMetrics.averageStress);
      const peakStressInfo = stressMeaning(currentMetrics.peakStress);
      const conflictInfo = conflictMeaning(currentMetrics.conflict);
      const totalTicks = Math.max(totalRunTicks(), 1);
      const ticksInfo = ticksMeaning(step.tick, totalTicks);

      metricProgressValue.textContent = currentMetrics.progress + "%";
      metricProgressState.textContent = progressInfo.label;
      metricProgressBar.style.width = currentMetrics.progress + "%";
      metricProgressCopy.textContent = previousMetrics
        ? `Progress ${progressDelta === 0 ? "held steady" : `changed by ${(progressDelta >= 0 ? "+" : "") + progressDelta}%`} this step.`
        : "Tasks completed so far in this run.";

      metricTrustValue.textContent = currentMetrics.averageTrust.toFixed(2);
      metricTrustState.textContent = trustInfo.label;
      metricTrustBar.style.width = (currentMetrics.averageTrust * 100).toFixed(1) + "%";
      metricTrustCopy.textContent = previousMetrics
        ? `Team trust ${Math.abs(trustDelta) > 0.005 ? `changed ${formatDelta(trustDelta)}` : "held steady"} this step.`
        : "Average trust across all agents at this step.";

      if (metricAvgStressValue) metricAvgStressValue.textContent = currentMetrics.averageStress.toFixed(2);
      if (metricAvgStressState) metricAvgStressState.textContent = avgStressInfo.label;
      if (metricAvgStressBar) metricAvgStressBar.style.width = (currentMetrics.averageStress * 100).toFixed(1) + "%";
      if (metricAvgStressCopy) metricAvgStressCopy.textContent = previousMetrics
        ? `Team stress ${Math.abs(avgStressDelta) > 0.005 ? `changed ${formatDelta(avgStressDelta)}` : "held steady"} this step.`
        : "Average emotional load across all agents at this step.";

      metricStressValue.textContent = currentMetrics.peakStress.toFixed(2);
      metricStressState.textContent = peakStressInfo.label;
      metricStressBar.style.width = (currentMetrics.peakStress * 100).toFixed(1) + "%";
      metricStressCopy.textContent = previousMetrics
        ? `Peak stress ${Math.abs(peakStressDelta) > 0.005 ? `changed ${formatDelta(peakStressDelta)}` : "held steady"} this step.`
        : "Highest individual stress reached so far.";

      if (metricConflictValue) metricConflictValue.textContent = currentMetrics.conflict.toFixed(2);
      if (metricConflictState) metricConflictState.textContent = conflictInfo.label;
      if (metricConflictBar) metricConflictBar.style.width = (currentMetrics.conflict * 100).toFixed(1) + "%";
      if (metricConflictCopy) metricConflictCopy.textContent = previousMetrics
        ? `Friction ${Math.abs(conflictDelta) > 0.005 ? `changed ${formatDelta(conflictDelta)}` : "held steady"} this step.`
        : "Team friction and coordination pressure at this step.";

      metricTicksValue.textContent = step.tick === 0 && totalRunTicks() === 0 ? "Ready" : step.tick + "/" + totalTicks;
      metricTicksState.textContent = ticksInfo.label;
      metricTicksBar.style.width = ((step.tick / totalTicks) * 100).toFixed(1) + "%";
      metricTicksCopy.textContent = "Current step out of the full run.";
    }

    function renderLog(stepIndex) {
      if (!RUN) return;
      // Run Timeline shows only meaningful steps (real backend events, task changes,
      // progress changes, or the final outcome). Passive snapshots are filtered so the
      // timeline reads as a faithful inspection of the backend run rather than a frame
      // dump. RUN.steps itself is untouched so playback controls still traverse every
      // tick the backend actually produced.
      const visibleSteps = RUN.steps
        .slice(0, stepIndex + 1)
        .map((step, originalIndex) => ({ step, originalIndex }))
        .filter(({ step }) => step.isMeaningful);

      // If the current step is itself passive, highlight the most recent meaningful
      // step before it. If nothing meaningful has happened yet, render nothing.
      let activeOriginalIndex = stepIndex;
      if (!RUN.steps[stepIndex]?.isMeaningful) {
        for (let i = stepIndex - 1; i >= 0; i--) {
          if (RUN.steps[i]?.isMeaningful) { activeOriginalIndex = i; break; }
        }
      }

      if (!visibleSteps.length) {
        logTimeline.innerHTML = "";
        return;
      }

      logTimeline.innerHTML = visibleSteps.map(({ step, originalIndex }) => {
        const isActive = originalIndex === activeOriginalIndex;
        // Render the real backend event text verbatim. Only fall back when the backend
        // genuinely produced no event for this step (meaningful steps may still have an
        // empty event array if e.g. a task completed as a side-effect of a prior tick —
        // rare, but handled explicitly rather than silently).
        const hasBackendText = Boolean(step.hasBackendEvent && step.event.message);
        const quoteText = hasBackendText ? step.event.message : "";

        // Speaker → receiver attribution, pulled from the same maps the export uses.
        // Falls back to raw IDs if an agent is missing (defensive).
        const actor = step.agents && step.event.actorId ? step.agents[step.event.actorId] : null;
        const target = step.agents && step.event.targetId ? step.agents[step.event.targetId] : null;
        const actorLabel = actor ? actor.name : (step.event.actorId || "");
        const targetLabel = target ? target.name : (step.event.targetId || "");
        const attributionBlock = (actorLabel || targetLabel)
          ? `<div class="log-attribution">
              <span>${actorLabel}</span>
              ${targetLabel ? `<span class="log-arrow">→</span><span>${targetLabel}</span>` : ""}
            </div>`
          : "";

        // Hero content: prefer the real dialogue verbatim; fall back to the
        // pre-formatted eventLines (which include the "actor -> target:" prefix).
        let heroBlock = "";
        if (quoteText) {
          heroBlock = `<p class="log-hero">${quoteText}</p>`;
        } else if (step.eventLines.length) {
          heroBlock = step.eventLines.map((line) => `<div class="log-line">${line}</div>`).join("");
        }

        const kind = (step.event.type || "").toLowerCase();

        return `
            <article class="log-card ${isActive ? "active" : ""}" data-step-index="${originalIndex}" data-kind="${kind}">
            <div class="log-head">
              <div class="log-tick">${stepPositionLabel(step)}</div>
              <div class="event-type ${step.event.type}">${step.event.label}</div>
            </div>
            ${attributionBlock}
            ${heroBlock}
            <div class="log-effects">
              ${step.effectBullets.map((bullet) => `<div class="log-effect ${bullet.tone}">${bullet.text}</div>`).join("")}
            </div>
            <div class="log-why"><strong>Why this matters</strong>${step.whyImpact}</div>
          </article>
        `;
      }).join("");

      // Update the "Step N of M" counter using the MEANINGFUL step count,
      // not the raw tick index — this is what the user actually sees on screen.
      if (timelineCounter) {
        const activeVisibleIndex = visibleSteps.findIndex(
          (entry) => entry.originalIndex === activeOriginalIndex
        );
        const shown = activeVisibleIndex >= 0 ? activeVisibleIndex + 1 : visibleSteps.length;
        timelineCounter.textContent = `Step ${shown} of ${visibleSteps.length}`;
      }

      // Keep the active card in view so the timeline always reveals "where we are"
      // without the user hunting for it. Only auto-scrolls when the Run Timeline view
      // is visible; runs after the DOM is painted.
      if (currentView === "log") {
        const activeEl = logTimeline.querySelector(".log-card.active");
        if (activeEl) {
          requestAnimationFrame(() => {
            activeEl.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
            updateTimelineNavState();
          });
        } else {
          updateTimelineNavState();
        }
      } else {
        updateTimelineNavState();
      }
    }

    // Enables/disables prev & next nav arrows and toggles edge-fade opacity
    // based on the scroll position. Called on scroll, resize, and renderLog.
    function updateTimelineNavState() {
      if (!logTimeline) return;
      const max = logTimeline.scrollWidth - logTimeline.clientWidth;
      const left = logTimeline.scrollLeft;
      const atStart = left <= 2;
      const atEnd = left >= max - 2 || max <= 0;
      const track = logTimeline.parentElement;
      if (track) {
        track.dataset.atStart = String(atStart);
        track.dataset.atEnd = String(atEnd);
      }
      if (timelinePrevBtn) timelinePrevBtn.disabled = atStart;
      if (timelineNextBtn) timelineNextBtn.disabled = atEnd;
    }

    function safeRender(fn, label) {
      try { fn(); } catch (err) { console.error("[renderStep] " + label + " threw:", err); }
    }

    function renderStep(index) {
      if (!RUN?.steps?.length) return;
      currentIndex = clamp(index, 0, RUN.steps.length - 1);
      const step = currentStep();
      safeRender(() => renderContext(step),             "renderContext");
      safeRender(() => renderTasks(step),               "renderTasks");
      safeRender(() => renderScene(step),               "renderScene");
      safeRender(() => renderEventStrip(step),          "renderEventStrip");
      safeRender(() => renderLiveTimeline(currentIndex),"renderLiveTimeline");
      safeRender(() => renderWhy(step),                 "renderWhy");
      safeRender(() => renderFocus(step),               "renderFocus");
      safeRender(() => renderMetrics(step),             "renderMetrics");
      safeRender(() => renderLog(currentIndex),         "renderLog");
    }

    function setView(view) {
      currentView = view;
      viewLive.classList.toggle("active", view === "live");
      viewLog.classList.toggle("active", view === "log");
      viewSwitch.querySelectorAll("button").forEach((button) => {
        button.classList.toggle("active", button.dataset.view === view);
      });
    }

    function pausePlayback() {
      if (!RUN) return Promise.resolve();
      window.clearInterval(timer);
      timer = null;
      const wasBackendAuto = playbackMode === "backend-auto" && wsReady;
      playing = false;
      playbackMode = "idle";
      playBtn.textContent = RUN.ended ? "Replay" : "Play";
      if (wasBackendAuto) {
        ws.send(JSON.stringify({ cmd: "auto_stop" }));
      }
      renderContext(currentStep());
      return Promise.resolve();
    }

    async function nextStep() {
      if (!RUN) return;
      if (currentIndex < RUN.steps.length - 1) {
        renderStep(currentIndex + 1);
        return;
      }
      if (RUN.ended) {
        return;
      }
      try {
        const socket = await ensureSocket(runId);
        if (socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ cmd: "step" }));
        } else {
          setFooterMessage("Could not advance — backend connection lost. Try refreshing.");
        }
      } catch {
        setFooterMessage("Could not connect to the backend to advance the run.");
      }
    }

    function previousStep() {
      if (!RUN) return;
      window.clearInterval(timer);
      timer = null;
      playing = false;
      playbackMode = "idle";
      playBtn.textContent = RUN.ended ? "Replay" : "Play";
      renderStep(currentIndex - 1);
    }

    function playLocalReplay() {
      if (!RUN || playing) return;
      if (currentIndex >= RUN.steps.length - 1) renderStep(0);
      playing = true;
      playbackMode = "local-replay";
      playBtn.textContent = "Playing";
      renderContext(currentStep());
      timer = window.setInterval(() => {
        if (currentIndex >= RUN.steps.length - 1) {
          pausePlayback();
          return;
        }
        renderStep(currentIndex + 1);
        if (currentIndex >= RUN.steps.length - 1) {
          pausePlayback();
        }
      }, 1700);
    }

    async function playPlayback() {
      if (!RUN || playing) return;
      if (RUN.ended) {
        playLocalReplay();
        return;
      }
      if (currentIndex < RUN.steps.length - 1) {
        renderStep(RUN.steps.length - 1);
      }
      let socket;
      try {
        socket = await ensureSocket(runId);
      } catch {
        setFooterMessage("Could not connect to the backend to start auto-play.");
        return;
      }
      if (socket.readyState !== WebSocket.OPEN) {
        setFooterMessage("Backend connection not ready. Try again in a moment.");
        return;
      }
      playing = true;
      playbackMode = "backend-auto";
      playBtn.textContent = "Playing";
      renderContext(currentStep());
      socket.send(JSON.stringify({ cmd: "auto", tick_hz: 1.5 }));
    }

    function resetPlayback() {
      if (!RUN) return;
      window.clearInterval(timer);
      timer = null;
      if (playbackMode === "backend-auto" && wsReady) {
        ws.send(JSON.stringify({ cmd: "auto_stop" }));
      }
      playing = false;
      playbackMode = "idle";
      playBtn.textContent = RUN.ended ? "Replay" : "Play";
      renderStep(0);
    }

    viewSwitch.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-view]");
      if (!button) return;
      setView(button.dataset.view);
    });

    document.getElementById("playBtn").addEventListener("click", playPlayback);
    document.getElementById("pauseBtn").addEventListener("click", pausePlayback);
    document.getElementById("nextBtn").addEventListener("click", async () => {
      await pausePlayback();
      await nextStep();
    });
    document.getElementById("prevBtn").addEventListener("click", previousStep);
    document.getElementById("resetBtn").addEventListener("click", resetPlayback);
    runDetailsBtn.addEventListener("click", () => {
      runDetailsOpen = !runDetailsOpen;
      syncRunDetails();
    });
    exportResultsBtn.addEventListener("click", exportCurrentRun);

    // Run Timeline sideways navigation — arrows scroll by roughly one card
    // width per click. Scroll events (user drag / wheel) refresh the nav state
    // so the arrows hide cleanly at the ends and the edge fades dim.
    function scrollTimelineByCard(direction) {
      if (!logTimeline) return;
      const firstCard = logTimeline.querySelector(".log-card");
      const step = firstCard ? firstCard.getBoundingClientRect().width + 14 : 340;
      logTimeline.scrollBy({ left: step * direction, behavior: "smooth" });
    }

    if (timelinePrevBtn) {
      timelinePrevBtn.addEventListener("click", () => scrollTimelineByCard(-1));
    }
    if (timelineNextBtn) {
      timelineNextBtn.addEventListener("click", () => scrollTimelineByCard(1));
    }
    if (logTimeline) {
      logTimeline.addEventListener("scroll", () => updateTimelineNavState(), { passive: true });
    }

    window.addEventListener("resize", () => {
      if (RUN) renderStep(currentIndex);
      updateTimelineNavState();
    });

    // ── completion modal ──────────────────────────────────────────
    let completionShown = false;

    function fmtNum(n, dp = 2) {
      if (typeof n !== "number" || !isFinite(n)) return "—";
      return n.toFixed(dp);
    }

    function trustBand(v) {
      if (v >= 0.66) return "High cooperation";
      if (v >= 0.45) return "Steady cooperation";
      if (v >= 0.30) return "Guarded cooperation";
      return "Low cooperation";
    }
    function stressBand(v) {
      if (v > 0.55) return "High pressure";
      if (v > 0.25) return "Moderate pressure";
      return "Low pressure";
    }
    function outcomeLabel() {
      if (!RUN) return "Unknown";
      const endReason = RUN.endReason || RUN.steps[RUN.steps.length - 1]?.endReason || "";
      if (!endReason) return RUN.ended ? "Complete" : "In progress";
      return titleCase(endReason);
    }

    function buildInsight(finalStep) {
      const m = finalStep.metrics;
      const scenLabel = RUN.scenario.key === "cafe" ? "the cafe plan"
                      : RUN.scenario.key === "escape" ? "the escape room"
                      : "the office project";
      const trustPart = m.averageTrust >= 0.50
        ? "trust stayed stable"
        : "trust remained guarded";
      const stressPart = m.peakStress >= 0.45
        ? "Stress rose during the hardest requests"
        : m.peakStress >= 0.25
          ? "Stress rose while missing details were being requested"
          : "Stress stayed calm throughout";
      return `The team completed ${scenLabel}. ${stressPart}, and ${trustPart}.`;
    }

    function completionSubtitle(finalStep) {
      if (RUN.scenario.key === "cafe") {
        return `The cafe plan was completed in ${finalStep.tick} step${finalStep.tick === 1 ? "" : "s"}.`;
      }
      if (RUN.scenario.key === "escape") {
        return `The escape room was completed in ${finalStep.tick} step${finalStep.tick === 1 ? "" : "s"}.`;
      }
      return `The office project was completed in ${finalStep.tick} step${finalStep.tick === 1 ? "" : "s"}.`;
    }

    function showCompletionModal() {
      if (completionShown) return;
      completionShown = true;

      const finalStep = RUN.steps[RUN.steps.length - 1];
      const m = finalStep.metrics;

      document.getElementById("doneTitle").textContent = "Simulation Complete";
      document.getElementById("doneSub").textContent = completionSubtitle(finalStep);

      document.getElementById("doneOutcomeValue").textContent = `${m.progress || 0}%`;
      document.getElementById("doneOutcomeSub").textContent = outcomeLabel();

      document.getElementById("doneTrustValue").textContent = fmtNum(m.averageTrust);
      document.getElementById("doneTrustSub").textContent = trustBand(m.averageTrust);

      document.getElementById("doneStressValue").textContent = fmtNum(m.peakStress);
      document.getElementById("doneStressSub").textContent = stressBand(m.peakStress);

      document.getElementById("doneInsight").textContent = buildInsight(finalStep);

      document.getElementById("doneOverlay").classList.add("is-open");
    }

    function hideCompletionModal() {
      document.getElementById("doneOverlay").classList.remove("is-open");
    }

    document.getElementById("doneOverlay").addEventListener("click", (e) => {
      if (e.target.id === "doneOverlay") hideCompletionModal();
    });
    document.getElementById("doneCloseBtn").addEventListener("click", hideCompletionModal);
    document.getElementById("doneReplayBtn").addEventListener("click", () => {
      hideCompletionModal();
      completionShown = false; // allow modal to fire again when replay finishes
      resetPlayback();
      window.setTimeout(playPlayback, 200);
    });
    document.getElementById("doneTimelineBtn").addEventListener("click", () => {
      hideCompletionModal();
      setView("log");
    });
    document.getElementById("doneHistoryBtn").addEventListener("click", () => {
      if (!RUN?.savedToHistory) return;
      window.location.href = `history.html?run=${encodeURIComponent(RUN.runId)}`;
    });
    document.getElementById("doneExportBtn").addEventListener("click", exportCurrentRun);
    document.getElementById("doneNewSetupBtn").addEventListener("click", () => {
      window.location.href = "setup.html";
    });

    // Hook into renderContext: when the last step is reached, surface the modal
    // once. We wrap renderContext rather than editing its body so the original
    // rendering logic stays untouched.
    const _origRenderContext = renderContext;
    renderContext = function(step) {
      _origRenderContext(step);
      if (RUN?.ended && currentIndex >= RUN.steps.length - 1) {
        // small delay so the user sees the final step land before the modal
        window.setTimeout(showCompletionModal, 450);
      }
    };

    function showDashboardError(message) {
      contextScenario.textContent = "Backend Run";
      contextTeam.textContent = "Unavailable";
      contextTick.textContent = "—";
      contextStatus.textContent = "Error";
      eventStep.textContent = "Run not available";
      eventSummary.textContent = "Could not load the backend simulation.";
      eventMessage.textContent = message;
      eventType.textContent = "ERROR";
      eventType.className = "event-type challenge";
      eventEffects.innerHTML = "";
      sceneHeading.textContent = "Backend run unavailable";
      sceneIntro.textContent = "The dashboard only renders real backend state. No local fallback run was created.";
      sceneGoal.textContent = "Start a run from Setup so the backend can create the run ID.";
      taskList.innerHTML = "";
      logTimeline.innerHTML = "";
      setFooterMessage("This dashboard needs a valid backend run. Start a run from Setup or reopen a saved replay from History.");
    }

    async function initialiseDashboard() {
      setView("live");
      contextStatus.textContent = "Loading";
      eventStep.textContent = "CURRENT STEP — Loading…";
      eventSummary.textContent = "Initializing";
      eventMessage.textContent = "";

      try {
        await ensureRunId();
        rawRunState = await fetchLiveOrSavedRunStatus(runId);
        rebuildRun({ forceLatest: true });

        if (!RUN?.ended) {
          await ensureSocket(runId);
        }

        if (RUN?.mode === "auto" && !RUN.ended && totalRunTicks() === 0) {
          window.setTimeout(() => {
            playPlayback();
          }, 350);
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        console.error(error);
        showDashboardError(message);
      }
    }

    window.addEventListener("beforeunload", () => {
      if (ws) ws.close();
    });

    initialiseDashboard();
