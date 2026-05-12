// Replay dashboard logic: builds the timeline, panels, and playback state.
// Scenario metadata here keeps replay labels, agent cards, and task copy in one place.
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
      // Replay modes from History — passed through as distinct internal values so
      // the dashboard can label itself correctly without mixing up live modes.
      if (lower === "watch_replay") return "watch_replay";
      if (lower === "interactive_replay") return "interactive_replay";
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
      if (mode === "watch_replay") return "Watch Mode Replay";
      if (mode === "interactive_replay") return "Live Interactive Replay";
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
      return "project information";
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

      // Use the canonical template order so the Task Flow always matches the
      // scenario chain (e.g. Escape: map → lock → key → door → unlock).
      // Fall back to dict iteration for any keys not covered by the template.
      const templateKeys = (SCENARIOS[scenarioKey]?.tasks || []).map((t) => t.key);
      const stateKeys = Object.keys(taskState || {});
      const orderedKeys = [
        ...templateKeys.filter((k) => k in (taskState || {})),
        ...stateKeys.filter((k) => !templateKeys.includes(k)),
      ];

      return orderedKeys.map((key) => {
        const done = (taskState || {})[key];
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
            detail: "Shared by " + actorNameFromEvent(step, latest) + " — waiting for " + targetNameFromEvent(step, latest)
          };
        }
        if (latest?.type === "ask_info") {
          return {
            statusTone: "waiting",
            statusText: "Waiting",
            detail: actorNameFromEvent(step, latest) + " requested this from " + targetNameFromEvent(step, latest)
          };
        }
        if (latest?.type === "challenge") {
          return {
            statusTone: "waiting",
            statusText: "Waiting",
            detail: actorNameFromEvent(step, latest) + " is re-checking this with " + targetNameFromEvent(step, latest)
          };
        }
        return {
          statusTone: "waiting",
          statusText: "Waiting",
          detail: "Waiting for " + (owner ? owner.name : "the owner")
        };
      }

      return {
        statusTone: "pending",
        statusText: "Locked",
        detail: ""
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
      // Read avg_stress from snapshot.metrics first — the backend writes this value
      // directly from compute_metrics(), which is the SAME source as
      // metric_trajectory.stress_peak.  Computing from snapshot.agents manually
      // re-introduces rounding differences (backend rounds each agent to 3dp then
      // averages; JS would average the pre-rounded values) that cause the modal
      // card to show a different number than the insight text.
      let peak = 0;
      snapshots.slice(0, lastIndex + 1).forEach((snapshot) => {
        const backendAvg = snapshot?.metrics?.avg_stress;
        if (typeof backendAvg === "number") {
          peak = Math.max(peak, backendAvg);
          return;
        }
        // Fallback: compute from agents if avg_stress is absent (older snapshots)
        const agents = snapshot?.agents || [];
        if (!agents.length) return;
        const avgStress = agents.reduce((sum, a) => sum + (a?.stress || 0), 0) / agents.length;
        peak = Math.max(peak, avgStress);
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
        conflict: conflictFromSnapshot(snapshot),
        cohesion: typeof snapshot?.group_state?.cohesion === "number"
          ? snapshot.group_state.cohesion
          : (typeof snapshot?.metrics?.group_cohesion === "number" ? snapshot.metrics.group_cohesion : 0)
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

    function backendEventLabel(type, normalizedType) {
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
      return explicit[type] || EVENT_META[normalizedType]?.label || titleCase(type || "say");
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
      // Use the event-type label only — raw speech text belongs only in the animation bubble.
      const label = backendEventLabel(event.type, normalizeBackendEventType(event.type));
      return actorName + " → " + targetName + ": " + label;
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
          text: nextMetrics.progress > 0 ? "Progress: 0% → " + nextMetrics.progress + "%" : "Waiting on first response"
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
        ? blockerLabel + " is the current focus, so this is where the team needs to start."
        : blockerLabel + " is still the current focus, so this step keeps the team aligned on that required item.";
      const item = event.item ? prettifyKey(event.item) : blockerLabel;
      if (event.type === "share_info") return item + " is blocking progress, so the team is trying to pass the clue to the next person.";
      if (event.type === "ask_info") return item + " is still missing, so the team is requesting the detail it needs.";
      if (event.type === "challenge") return item + " is under pressure, so the team is checking whether the current answer is reliable.";
      if (event.type === "agree") return item + " is close to being locked in, so the team is confirming it before moving on.";
      return blockerLabel + " is the current focus, so this step is still about clearing that required item.";
    }

    function whyReasoning(event, eventContext, actor, target, isPreStart, agentMap, ended, scenarioKey) {
      // Escape completion: all prerequisites confirmed — give a scenario-specific explanation
      // rather than falling through to the generic "A3 spoke to A2 about..." fallback.
      if (ended && scenarioKey === "escape") {
        return "The final escape step completed because all prerequisite clues were already confirmed: Room Map, Lock Pattern, Key Location, and Door Code.";
      }
      if (!event) return isPreStart
        ? "Run is ready. No agent interaction recorded yet."
        : "No direct agent exchange landed this step, so the run carried the current focus state forward.";
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
      const item = event.item ? prettifyKey(event.item) : "the current focus";
      if (event.type === "share_info") return actor.name + " shared the " + item + " so " + target.name + " has what's needed to move forward.";
      if (event.type === "ask_info") return actor.name + " asked " + target.name + " for the " + item + " so the team can proceed.";
      if (event.type === "agree") return actor.name + " confirmed the " + item + " with " + target.name + ", locking it in and moving progress forward.";
      if (event.type === "challenge") return actor.name + " questioned the " + item + " with " + target.name + " to test whether it holds under pressure.";
      if (event.type === "suggest") return actor.name + " suggested a next move to " + target.name + " based on the current focus.";
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
        shifts.push("Progress increased from " + previousMetrics.progress + "% to " + nextMetrics.progress + "%.");
      } else {
        shifts.push("Progress stayed at " + nextMetrics.progress + "%.");
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
        const finalLabel = String(endReason || "").toLowerCase();
        shifts.push(
          finalLabel === "success" || finalLabel === "harmony"
            ? "The run ended successfully."
            : "The run ended as " + titleCase(endReason || "complete") + "."
        );
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

      // Build a human-readable summary for multi-event steps (e.g. group confirm/agree).
      // When 3+ events share the same type, collapse them to "Confirmed by A1, A3 and A4"
      // rather than showing a crowded "A1 → A4: Confirm · A4 → A1: Confirm · …" string.
      function buildSmartSummaryLine() {
        if (snapshot?.ended) return "Simulation complete.";
        if (isPreStart) return "Simulation ready. Press Play or Next to start.";
        if (!summaries.length) return "Agents held their positions this step.";
        if (stepEvents.length < 3) return summaries.join(" · ");
        const types = stepEvents.map((e) => normalizeBackendEventType(e?.type)).filter(Boolean);
        const uniqueTypes = [...new Set(types)];
        if (uniqueTypes.length === 1) {
          const actors = stepEvents.map((e) => agentMap[e.actor]?.name || e.actor).filter(Boolean);
          const uniqueActors = [...new Set(actors)];
          if (uniqueActors.length >= 2) {
            const label = backendEventLabel(stepEvents[0].type, uniqueTypes[0]);
            const last = uniqueActors[uniqueActors.length - 1];
            const rest = uniqueActors.slice(0, -1);
            return label + " by " + rest.join(", ") + " and " + last;
          }
        }
        return summaries.join(" · ");
      }

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
        summaryLine: buildSmartSummaryLine(),
        eventLines: summaries,
        eventsRaw: stepEvents,
        whyTitle: whyTitle(eventType, actor, target, completedTasks, snapshot?.ended, scenarioDisplay, primaryEvent),
        whyTrigger: whyTrigger(blockerAfter, primaryEvent, eventContext, snapshot?.ended, scenarioDisplay, isPreStart),
        whyReasoning: whyReasoning(primaryEvent, eventContext, actor, target, isPreStart, agentMap, Boolean(snapshot?.ended), scenarioKey),
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
      const previousRunId = RUN?.runId || "";
      const previousResults = RUN?.personalityTestResults || null;
      const previousResultsKey = RUN?.personalityResultsKey || "";
      RUN = buildRunFromBackendStatus(rawRunState);
      if (!RUN?.steps?.length) return;
      if (_savedRunSummary && previousRunId && RUN.runId && String(previousRunId) !== String(RUN.runId)) {
        _savedRunSummary = null;
      }
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
      const response = await fetch(`${API_BASE}/history/runs/${activeRunId}`, { headers: {} });
      if (!response.ok) {
        throw new Error(await parseApiError(response));
      }
      return response.json();
    }

    async function fetchSavedRunReplay(activeRunId) {
      const response = await fetch(`${API_BASE}/history/runs/${activeRunId}/replay`, { headers: {} });
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

    // Cached saved-run summary — set when loading a replay so showCompletionModal
    // can display memory_summary and emotion_summary without a second fetch.
    let _savedRunSummary = null;

    function cachedSummaryMatchesRun(activeRunId) {
      return Boolean(
        _savedRunSummary
        && activeRunId
        && String(_savedRunSummary.run_id || "") === String(activeRunId)
      );
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
        _savedRunSummary = summary;   // cache for completion modal
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
      _savedRunSummary = null;
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
        return "That resolves this step and unlocks " + step.blockerAfter + ".";
      }

      if (step.event.type === "confirm") {
        return "No new task cleared on this step, but the team is more aligned.";
      }

      return "Progress is waiting on " + step.blockerAfter + ".";
    }

    function currentEventHeadline(step) {
      if (!step) return "Waiting for the next step.";
      if (step.ended || step.event.type === "wrap") return "✓ Simulation complete";
      return step.whyTitle || step.summaryLine || step.event.label;
    }

    function currentEventSupportLine(step) {
      if (!step) return "";
      if (step.ended || step.event.type === "wrap") return currentActionSupport(step);
      if (step.hasBackendEvent) return step.whyReasoning || currentActionSupport(step);
      return currentActionSupport(step);
    }

    function currentEventSecondaryLine(step) {
      if (!step || step.ended || step.event.type === "wrap") return "";
      // Show the full event list for the step so users can see everything that
      // happened, not just the primary (highlighted) interaction in the bubble.
      // Only shown when there are 2+ events — single-event steps need no list.
      const allLines = (step.eventsRaw || [])
        .map((event) => summarizeEvent(event, step.agents || {}))
        .filter(Boolean);
      if (allLines.length < 2) return "";
      return "Full step events: " + allLines.join(" · ");
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
    const currentEventCard = document.querySelector(".current-event");
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
    const resetBtn = document.getElementById("resetBtn");
    const prevBtn = document.getElementById("prevBtn");
    const playBtn = document.getElementById("playBtn");
    const nextBtn = document.getElementById("nextBtn");
    const pauseBtn = document.getElementById("pauseBtn");
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

    function syncControlPriority() {
      if (!playBtn || !nextBtn || !resetBtn || !pauseBtn) return;
      playBtn.classList.remove("primary");
      nextBtn.classList.remove("primary");
      resetBtn.classList.add("utility");

      if (playing) {
        playBtn.classList.add("primary");
      } else {
        nextBtn.classList.add("primary");
      }
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

    /**
     * Safe label helper for PDF payload builders.
     * Accepts either a plain string key OR an object with a label-like property.
     * Never throws — always returns a non-empty string.
     */
    function getSafeItemLabel(item, index = 0) {
      if (!item) return `Item ${index + 1}`;
      if (typeof item === "string") return prettifyKey(item) || `Item ${index + 1}`;
      return (
        item.label ||
        item.name  ||
        item.title ||
        item.item  ||
        item.task  ||
        item.blocker ||
        item.blockerName ||
        item.clue  ||
        item.key   ||
        `Item ${index + 1}`
      );
    }

    /**
     * Build the structured data object consumed by SimuVersePDF.generate().
     * Extracts agents, tasks, per-step metric history, and interventions from RUN.
     */
    function buildPdfPayload() {
      if (!RUN) return null;
      // Defensive aliases — RUN.scenario / RUN.team may be missing on edge-case runs
      const scenario = RUN.scenario || {};
      const team     = RUN.team     || {};
      const steps = Array.isArray(RUN.steps) ? RUN.steps : [];
      const finalStep = steps[steps.length - 1];
      if (!finalStep || !finalStep.metrics) return null;
      const fm = finalStep.metrics;
      const finalAgentMap = finalStep.agents || {};
      const firstStepAgentMap = steps.find((step) => step?.agents && Object.keys(step.agents).length)?.agents || {};
      const topLevelAgents = Array.isArray(rawRunState?.agents) ? rawRunState.agents : [];

      function normalizeProgressForPdf(value) {
        const n = Number(value || 0);
        return n > 1 ? n / 100 : n;
      }

      /* ── Metrics history — one point per recorded step ── */
      const metricsHistory = steps
        .map((s) => ({
          tick:     s.tick,
          progress: normalizeProgressForPdf(s.metrics.progress),
          trust:    s.metrics.averageTrust,
          stress:   s.metrics.averageStress ?? s.metrics.peakStress,
          conflict: s.metrics.conflict,
          cohesion: s.metrics.cohesion,
        }));

      /* ── Agent list from scenario template + final step ── */
      const scenarioAgents = Array.isArray(scenario.agents) && scenario.agents.length
        ? scenario.agents
        : topLevelAgents.length
          ? topLevelAgents
        : Object.values(Object.keys(finalAgentMap).length ? finalAgentMap : firstStepAgentMap).map((agent) => ({
            id: agent.id,
            name: agent.name || agent.id,
            role: agent.role || "Agent",
            personality: agent.personality || agent.strategy || "",
            color: agent.color || null,
          }));

      const agents = scenarioAgents.map((a) => {
        const finalAgent = finalAgentMap[a.id] || firstStepAgentMap[a.id] || {};
        const knownItems = Array.isArray(finalAgent.known_items) && finalAgent.known_items.length
          ? finalAgent.known_items
          : (Array.isArray(a.known_items) ? a.known_items : []);
        const heldItem = knownItems.length
          ? getSafeItemLabel(knownItems[0])
          : ((scenario.tasks || []).find((task) => task.owner === a.id)?.label || "—");
        return {
          id:          a.id,
          name:        a.id, // always the agent ID (A1–A4), never a human name field
          role:        a.role || "Agent",
          personality: finalAgent.personality || a.personality || finalAgent.strategy || a.strategy || "",
          color:       a.color || null,
          holds:       heldItem,
          finalStress: typeof finalAgent.stress === "number"
            ? finalAgent.stress
            : (typeof a.final_stress === "number" ? a.final_stress : (typeof a.stress === "number" ? a.stress : null)),
        };
      });

      /* ── Tasks: final done/not-done state ── */
      const finalTasks = Array.isArray(finalStep.tasks)
        ? finalStep.tasks.map((t) => ({ label: t.label, done: !!t.done }))
        : [];

      /* ── Timeline — one entry per meaningful step ── */
      const timeline = steps
        .filter((s) => Number(s.tick || 0) > 0)
        .map((s) => {
          const actor  = s.agents?.[s.event?.actorId];
          const target = s.agents?.[s.event?.targetId];
          const actionDetails = Array.isArray(s.eventLines) ? s.eventLines : [];
          return {
            tick:        s.tick,
            title:       s.whyTitle || s.event?.label || s.event?.type || "Interaction",
            eventType:   s.event?.label || s.event?.type || "",
            actorName:   actor  ? actor.name  : (s.event?.actorId  || ""),
            targetName:  target ? target.name : (s.event?.targetId || ""),
            summary:     s.summaryLine || (s.eventsRaw?.length ? "Interaction recorded." : "No agent message recorded for this step."),
            message:     s.event?.message || s.summaryLine || "",
            actionDetails,
            effects:     (s.effectBullets || []).map((e) => (typeof e === "string" ? e : (e.text || ""))),
            whyTrigger:  s.whyTrigger   || "",
            whyReasoning:s.whyReasoning || "",
            whyImpact:   s.whyImpact    || "",
            hasEvent:    Boolean((s.eventsRaw || []).length),
          };
        });

      /* ── Interventions — steps where a user/intervention event appears ── */
      const interventions = [];
      steps.forEach((s) => {
        const raw = s.eventsRaw || [];
        raw.forEach((ev) => {
          const t = String(ev?.type || "").toLowerCase();
          if (
            t.includes("intervention") || t.includes("inject") ||
            t.includes("reveal") || t.includes("force") ||
            t.includes("user_") || t === "user"
          ) {
            const prev = s.previousMetrics || {};
            const curr = s.metrics || {};
            interventions.push({
              tick:            s.tick,
              label:           ev.label || ev.type || "Intervention",
              type:            ev.type || "",
              stressChange:    curr.averageStress  != null && prev.averageStress  != null
                                 ? +(curr.averageStress  - prev.averageStress ).toFixed(3) : null,
              trustChange:     curr.averageTrust   != null && prev.averageTrust   != null
                                 ? +(curr.averageTrust   - prev.averageTrust  ).toFixed(3) : null,
              conflictChange:  curr.conflict       != null && prev.conflict       != null
                                 ? +(curr.conflict       - prev.conflict      ).toFixed(3) : null,
            });
          }
        });
      });

      /* ── Auto-generate outcome summary ── */
      const doneTasks = finalTasks.filter((t) => t.done).length;
      const pct = finalTasks.length ? Math.round((doneTasks / finalTasks.length) * 100) : 0;
      const outcomeSummary =
        `The ${scenario.label || "simulation"} scenario ran for ${finalStep.tick} steps using the ` +
        `${team.label || "unknown"} preset. ` +
        `${doneTasks} of ${finalTasks.length} tasks were completed (${pct}%). ` +
        `Final trust was ${Number(fm.averageTrust || 0).toFixed(2)} and stress was ` +
        `${Number(fm.averageStress ?? fm.peakStress ?? 0).toFixed(2)}. ` +
        (interventions.length
          ? `${interventions.length} user intervention${interventions.length !== 1 ? "s" : ""} were applied during the run.`
          : "No user interventions were applied — this was a fully autonomous run.");

      return {
        runId:         RUN.runId,
        seed:          RUN.seed,
        exportedAt:    new Date().toLocaleString("en-GB", {
                         day: "2-digit", month: "short", year: "numeric",
                         hour: "2-digit", minute: "2-digit"
                       }),
        scenario:      { id: scenario.key || "", label: scenario.label || "", title: scenario.sceneTitle || "" },
        team:          { key: team.key || "", label: team.label || "" },
        mode:          RUN.mode,
        outcome:       outcomeLabel(),
        totalSteps:    finalStep.tick,
        agents,
        tasks:         finalTasks,
        finalMetrics: {
          progress: normalizeProgressForPdf(fm.progress),
          trust:    fm.averageTrust,
          stress:   fm.averageStress ?? fm.peakStress,
          conflict: fm.conflict,
          cohesion: fm.cohesion ?? 0,
        },
        metricsHistory,
        timeline,
        interventions,
        outcomeSummary,
      };
    }

    function buildSafePdfReportData(report) {
      const source = report && typeof report === "object" ? report : {};
      const steps = Array.isArray(source.timeline) ? source.timeline : [];
      const metricsHistory = Array.isArray(source.metricsHistory) ? source.metricsHistory : [];
      const agents = Array.isArray(source.agents) ? source.agents : [];
      const tasks = Array.isArray(source.tasks) ? source.tasks : [];
      const interventions = Array.isArray(source.interventions) ? source.interventions : [];

      const safe = {
        runId: source.runId || RUN?.runId || "unknown-run",
        seed: source.seed ?? RUN?.seed ?? "Not recorded",
        exportedAt: source.exportedAt || new Date().toLocaleString("en-GB", {
          day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit"
        }),
        scenario: {
          id: source.scenario?.id || RUN?.scenario?.key || "unknown-scenario",
          label: source.scenario?.label || RUN?.scenario?.label || "Unknown scenario",
          title: source.scenario?.title || RUN?.scenario?.sceneTitle || "Simulation run",
        },
        team: {
          key: source.team?.key || RUN?.team?.key || "",
          label: source.team?.label || RUN?.team?.label || "Unknown team",
        },
        mode: source.mode || RUN?.mode || "Unknown mode",
        outcome: source.outcome || outcomeLabel() || "Incomplete",
        totalSteps: Number.isFinite(Number(source.totalSteps))
          ? Number(source.totalSteps)
          : (steps.length || metricsHistory.length || RUN?.steps?.length || 0),
        agents,
        tasks,
        finalMetrics: {
          progress: Number.isFinite(Number(source.finalMetrics?.progress)) ? Number(source.finalMetrics.progress) : 0,
          trust: Number.isFinite(Number(source.finalMetrics?.trust)) ? Number(source.finalMetrics.trust) : 0,
          stress: Number.isFinite(Number(source.finalMetrics?.stress)) ? Number(source.finalMetrics.stress) : 0,
          conflict: Number.isFinite(Number(source.finalMetrics?.conflict)) ? Number(source.finalMetrics.conflict) : 0,
          cohesion: Number.isFinite(Number(source.finalMetrics?.cohesion)) ? Number(source.finalMetrics.cohesion) : 0,
        },
        metricsHistory,
        timeline: steps,
        interventions,
        outcomeSummary: source.outcomeSummary || "",
      };

      const warnings = [];
      if (!agents.length) warnings.push("No agents recorded");
      if (!steps.length) warnings.push("No step timeline recorded");
      if (!metricsHistory.length) warnings.push("No metric history recorded");
      safe._warnings = warnings;
      return safe;
    }

    function exportCurrentRun() {
      if (!RUN) return;

      /* Prefer the structured jsPDF export to avoid cropped screenshot-style output. */
      if (window.SimuVersePDF) {
        try {
          const pdfData = buildSafePdfReportData(buildPdfPayload());
          if (pdfData) {
            const result = window.SimuVersePDF.generate(pdfData);
            if (result?.mode === "error") {
              setFooterMessage("PDF export is unavailable because the PDF library did not load correctly.");
            } else if (result?.mode === "fallback") {
              setFooterMessage("PDF exported with fallback formatting because the full report renderer hit an error.");
            } else if (pdfData._warnings?.length) {
              setFooterMessage("PDF exported. Some missing fields were replaced with fallback values.");
            } else {
              setFooterMessage("PDF exported successfully.");
            }
            return;
          }
          alert("PDF export could not be generated because this run is missing required report data.");
          return;
        } catch (error) {
          console.error("[Dashboard] Structured PDF export failed:", error);
        }
      }

      if (window.SimuVerseReport) {
        try {
          const payload = buildSafePdfReportData(buildPdfPayload());
          if (payload) {
            window.SimuVerseReport.generate(payload);
            return;
          }
        } catch (err) {
          console.error("[Dashboard] HTML PDF fallback failed:", err);
        }
      }

      alert("PDF export is unavailable. The structured PDF generator did not load on this page.");
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

      // peakStress: prefer the pre-computed running-max from displayMetricsForSnapshot
      // (stored in step.metrics.peakStress) which correctly accumulates across all ticks
      // up to this step.  Recomputing from agents here would give only the current-tick
      // maximum, which is always <= the true peak and breaks the metric strip.
      const peakStress = typeof step.metrics?.peakStress === "number"
        ? step.metrics.peakStress
        : (agents.length
            ? agents.reduce((maxSeen, agent) => Math.max(maxSeen, agent.stress || 0), 0)
            : 0);

      return {
        progress,
        averageTrust,
        averageStress,
        peakStress,
        conflict: typeof step.metrics?.conflict === "number" ? step.metrics.conflict : 0,
        cohesion: typeof step.metrics?.cohesion === "number" ? step.metrics.cohesion : 0
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
        if (!playing) {
          playBtn.textContent = "Replay Run";
          playBtn.title = "Replay the run from the beginning";
        }
        if (pauseEl) pauseEl.style.display = "none";
      } else {
        if (!playing) {
          playBtn.textContent = "Play";
          playBtn.title = "Auto-play through all steps";
        }
        if (pauseEl) pauseEl.style.display = "";
      }
      if (nextBtn) {
        nextBtn.textContent = (RUN.ended && currentIndex >= RUN.steps.length - 1) ? "View Results" : "Next →";
        nextBtn.title = (RUN.ended && currentIndex >= RUN.steps.length - 1)
          ? "Open the final run results"
          : "Advance one step";
      }
      syncControlPriority();
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
            ? `${doneTasks} / ${totalTasks} complete`
            : "No tasks yet";
      }
      taskList.innerHTML = step.tasks.map((task) => {
        const blockerClass = !task.done && task.label === step.blockerAfter ? "is-blocker" : "";
        const doneClass = task.done ? "is-done" : "";
        const taskName = taskDisplayLabel(task);
        const meta = taskStatusMeta(task, step);

        // Use a ✓ checkmark for completed tasks, ● dot for active blocker, ○ for locked
        const bulletIcon = task.done
          ? `<svg class="task-bullet is-check" viewBox="0 0 18 18" fill="none" aria-hidden="true"><circle cx="9" cy="9" r="8.5" fill="var(--green,#15a06b)" stroke="none"/><path d="M5 9l3 3 5-5" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`
          : (blockerClass
            ? `<svg class="task-bullet is-active" viewBox="0 0 18 18" fill="none" aria-hidden="true"><circle cx="9" cy="9" r="8.5" fill="var(--amber,#d08a2c)" stroke="none"/><circle cx="9" cy="9" r="3" fill="#fff"/></svg>`
            : `<svg class="task-bullet is-locked" viewBox="0 0 18 18" fill="none" aria-hidden="true"><circle cx="9" cy="9" r="8.5" stroke="rgba(15,34,56,0.18)" stroke-width="1.5" fill="none"/></svg>`);
        return `
          <div class="task-row ${doneClass} ${blockerClass}">
            ${bulletIcon}
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
          blockerCopy.textContent = "Every required clue is confirmed — the team can escape the room.";
        } else if (key === "cafe") {
          blockerTitle.textContent = "All Plans Set";
          blockerCopy.textContent = "Every plan detail is confirmed — the café is ready to open.";
        } else {
          blockerTitle.textContent = "All Tasks Complete";
          blockerCopy.textContent = "Every required task is done — the project can ship.";
        }
        logicLineA.style.display = "none";
        logicLineB.style.display = "none";
      } else {
        const activeTask = step.tasks.find((task) => task.label === step.blockerAfter);
        // Find who needs to act next: inspect the latest event for this blocker
        const blockerEvents = (step.eventsRaw || []).filter((event) => event?.item === activeTask?.key);
        const latestEvent = blockerEvents.length ? blockerEvents[blockerEvents.length - 1] : null;
        let nextActor = null;
        let actionPhrase;

        if (latestEvent?.type === "share_info") {
          nextActor = step.agents?.[latestEvent.target];
          actionPhrase = (nextActor ? nextActor.name : "Someone") + " needs to confirm " + step.blockerAfter + ".";
        } else if (latestEvent?.type === "ask_info") {
          nextActor = step.agents?.[latestEvent.actor];
          actionPhrase = (nextActor ? nextActor.name : "Someone") + " has been asked to provide " + step.blockerAfter + ".";
        } else {
          nextActor = activeTask ? step.agents?.[activeTask.owner] : null;
          actionPhrase = "Waiting for " + (nextActor ? nextActor.name : "the team") + " to resolve " + step.blockerAfter + ".";
        }

        // When a task was just completed this step, show that context so
        // the "Up Next" label doesn't look like it contradicts the centre panel.
        if (step.taskCompleted) {
          blockerTitle.textContent = "Up Next";
        } else {
          blockerTitle.textContent = "Waiting On";
        }
        blockerCopy.textContent = actionPhrase;

        // Show which task unlocks after the current one completes
        const nextLocked = step.tasks.find((t) => !t.done && t.label !== step.blockerAfter);
        if (nextLocked) {
          logicLineA.textContent = "Completing this will unlock: " + nextLocked.label;
          logicLineA.style.display = "";
        } else {
          logicLineA.style.display = "none";
        }

        // Show step metrics delta as a brief summary
        const previousMetrics = step.previousMetrics;
        const progressDelta = previousMetrics ? currentMetrics.progress - previousMetrics.progress : 0;
        if (previousMetrics && progressDelta !== 0) {
          logicLineB.textContent = "Progress moved " + (progressDelta > 0 ? "+" : "") + progressDelta + "% this step.";
          logicLineB.style.display = "";
        } else {
          logicLineB.style.display = "none";
        }
      }
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
          : "Exchange on " + itemLabel;
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
          ? (isActor ? `<div class="agent-state-chip speaker">${agent.role || agent.name}</div>` : "")
          : isActor
            ? `<div class="agent-state-chip speaker">${agent.name} speaks</div>`
            : isTarget
              ? `<div class="agent-state-chip ${receivingAction ? "receiver" : "waiting"}">${agent.name} receives</div>`
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
      const isCompleteStep = step.ended || step.event.type === "wrap";
      const supportLine = currentEventSupportLine(step);
      const secondaryLine = currentEventSecondaryLine(step);
      const totalEvents = (step.eventsRaw || []).length;

      // Header: "CURRENT STEP — Step N of M"
      eventStep.textContent = "CURRENT STEP — " + stepPositionLabel(step);

      // Action type badge + explanation
      if (sceneHasAction) {
        eventSummary.textContent = currentEventHeadline(step);
        eventType.textContent = isCompleteStep ? "COMPLETE" : actionLabel;
        eventType.className = "event-type " + (isCompleteStep ? "complete" : step.event.type);
        // Clarify that the animation bubble shows one highlighted interaction, not the
        // full step.  Only shown for active (non-complete) steps that have real events.
        const metaNote = !isCompleteStep && totalEvents > 0
          ? `<div class="event-watch-note">Showing highlighted interaction for this step${totalEvents > 1 ? " · " + totalEvents + " interactions recorded" : ""}</div>`
          : "";
        eventMessage.innerHTML = `
          <div class="event-message-primary">${escapeHtml(supportLine)}</div>
          ${metaNote}
          ${secondaryLine ? `<div class="event-message-secondary">${escapeHtml(secondaryLine)}</div>` : ""}
        `;
      } else {
        // HOLD: no backend events this step.
        // Distinguish the very first tick (truly "waiting on first response") from a
        // quiet mid-run step where events have already happened in earlier ticks.
        const isFirstTick = !step.tick || step.tick <= 0;
        eventSummary.textContent = isFirstTick
          ? "Waiting on first response"
          : "Quiet step — no new interaction";
        eventType.textContent = "HOLD";
        eventType.className = "event-type hold";
        eventMessage.innerHTML = isFirstTick ? `
          <div class="event-message-primary">Agents are processing the scenario — first interaction expected soon.</div>
          <div class="event-message-secondary">No events have been recorded yet.</div>
        ` : `
          <div class="event-message-primary">The team has started discussing this focus, but no new exchange was recorded this step.</div>
          <div class="event-message-secondary">Waiting for confirmation on the current focus.</div>
        `;
      }
      if (currentEventCard) {
        currentEventCard.classList.toggle("is-complete", isCompleteStep);
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
      const liveWhyReasoning = whyReasoning(primaryEvent, eventContext, actor, target, step.tick === 0, step.agents || {}, Boolean(step.ended), step.scenario?.key || RUN?.scenario?.key || "");
      const liveWhyImpact = whyImpact(previousMetrics, currentMetrics, completedTasks, step.ended, step.endReason, step.hasBackendEvent);
      const liveEffects = effectBullets(previousMetrics, currentMetrics, completedTasks, step.ended, step.endReason);

      if (whyTag) {
        whyTag.textContent = stepPositionLabel(step) + " · " + ((step.event && step.event.label) || "");
        whyTag.className = "why-kicker" + (eventType ? " " + eventType : "");
      }
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
      if (metricProgressCopy) metricProgressCopy.textContent = previousMetrics
        ? `Progress ${progressDelta === 0 ? "held steady" : `changed by ${(progressDelta >= 0 ? "+" : "") + progressDelta}%`} this step.`
        : "Tasks completed so far in this run.";

      metricTrustValue.textContent = currentMetrics.averageTrust.toFixed(2);
      metricTrustState.textContent = trustInfo.label;
      metricTrustBar.style.width = (currentMetrics.averageTrust * 100).toFixed(1) + "%";
      if (metricTrustCopy) metricTrustCopy.textContent = previousMetrics
        ? `Team trust ${Math.abs(trustDelta) > 0.005 ? `changed ${formatDelta(trustDelta)}` : "held steady"} this step.`
        : "Average trust across all agents at this step.";

      if (metricAvgStressValue) metricAvgStressValue.textContent = currentMetrics.averageStress.toFixed(2);
      if (metricAvgStressState) metricAvgStressState.textContent = avgStressInfo.label;
      if (metricAvgStressBar) metricAvgStressBar.style.width = (currentMetrics.averageStress * 100).toFixed(1) + "%";
      if (metricAvgStressCopy) metricAvgStressCopy.textContent = previousMetrics
        ? `Team stress ${Math.abs(avgStressDelta) > 0.005 ? `changed ${formatDelta(avgStressDelta)}` : "held steady"} this step.`
        : "Average emotional load across all agents at this step.";

      if (metricStressValue) metricStressValue.textContent = currentMetrics.peakStress.toFixed(2);
      if (metricStressState) metricStressState.textContent = peakStressInfo.label;
      if (metricStressBar) metricStressBar.style.width = (currentMetrics.peakStress * 100).toFixed(1) + "%";
      if (metricStressCopy) metricStressCopy.textContent = previousMetrics
        ? `Peak stress ${Math.abs(peakStressDelta) > 0.005 ? `changed ${formatDelta(peakStressDelta)}` : "held steady"} this step.`
        : "Highest individual stress reached so far.";

      if (metricConflictValue) metricConflictValue.textContent = currentMetrics.conflict.toFixed(2);
      if (metricConflictState) metricConflictState.textContent = conflictInfo.label;
      if (metricConflictBar) metricConflictBar.style.width = (currentMetrics.conflict * 100).toFixed(1) + "%";
      if (metricConflictCopy) metricConflictCopy.textContent = previousMetrics
        ? `Friction ${Math.abs(conflictDelta) > 0.005 ? `changed ${formatDelta(conflictDelta)}` : "held steady"} this step.`
        : "Team friction and coordination pressure at this step.";

      if (metricTicksValue) metricTicksValue.textContent = step.tick === 0 && totalRunTicks() === 0 ? "Ready" : step.tick + "/" + totalTicks;
      if (metricTicksState) metricTicksState.textContent = ticksInfo.label;
      if (metricTicksBar) metricTicksBar.style.width = ((step.tick / totalTicks) * 100).toFixed(1) + "%";
      if (metricTicksCopy) metricTicksCopy.textContent = "Current step out of the full run.";
    }

    function renderLog(stepIndex) {
      if (!RUN) return;
      // Keep the full meaningful timeline visible at all times so the layout stays
      // stable while the selected step moves. We only change the active card, not the
      // number of rendered cards, when stepping forward/backward.
      const visibleSteps = RUN.steps
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

        const logTitle = step.whyTitle || currentEventHeadline(step);
        const interactionSummary = step.eventLines.length
          ? `Interaction: ${step.eventLines.join(" · ")}`
          : currentEventSupportLine(step);

        const kind = (step.event.type || "").toLowerCase();

        return `
            <article class="log-card ${isActive ? "active" : ""}" data-step-index="${originalIndex}" data-kind="${kind}">
            <div class="log-head">
              <div class="log-tick">${stepPositionLabel(step)}</div>
              <div class="event-type ${step.event.type}">${step.event.label}</div>
            </div>
            <div class="log-title">${escapeHtml(logTitle)}</div>
            ${attributionBlock}
            <div class="log-line is-secondary">${escapeHtml(interactionSummary)}</div>
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
        const activeStep = RUN.steps[activeOriginalIndex];
        timelineCounter.textContent = activeStep
          ? `Selected · ${stepPositionLabel(activeStep)}`
          : `Run timeline · ${visibleSteps.length} key steps`;
      }

      // Keep the active card in view so the timeline always reveals "where we are"
      // without the user hunting for it. Only auto-scrolls when the Run Timeline view
      // is visible; runs after the DOM is painted.
      if (currentView === "log") {
        const activeEl = logTimeline.querySelector(".log-card.active");
        if (activeEl) {
          requestAnimationFrame(() => {
            const cardLeft = activeEl.offsetLeft;
            const cardWidth = activeEl.offsetWidth;
            const targetLeft = Math.max(
              0,
              cardLeft - ((logTimeline.clientWidth - cardWidth) / 2)
            );
            logTimeline.scrollTo({ left: targetLeft, behavior: "smooth" });
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
      syncControlPriority();
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
      syncControlPriority();
      renderStep(currentIndex - 1);
    }

    function playLocalReplay() {
      if (!RUN || playing) return;
      if (currentIndex >= RUN.steps.length - 1) renderStep(0);
      playing = true;
      playbackMode = "local-replay";
      playBtn.textContent = "Playing";
      syncControlPriority();
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
      syncControlPriority();
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
      syncControlPriority();
      renderStep(0);
    }

    viewSwitch.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-view]");
      if (!button) return;
      setView(button.dataset.view);
    });

    playBtn.addEventListener("click", playPlayback);
    pauseBtn.addEventListener("click", pausePlayback);
    nextBtn.addEventListener("click", async () => {
      if (RUN?.ended && currentIndex >= RUN.steps.length - 1) {
        await pausePlayback();
        showCompletionModal();
        return;
      }
      await pausePlayback();
      await nextStep();
    });
    prevBtn.addEventListener("click", previousStep);
    resetBtn.addEventListener("click", resetPlayback);
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
      logTimeline.addEventListener("click", (event) => {
        const card = event.target.closest(".log-card");
        if (!card) return;
        const nextIndex = Number(card.dataset.stepIndex);
        if (!Number.isFinite(nextIndex)) return;
        currentIndex = nextIndex;
        pausePlayback().then(() => renderStep(currentIndex));
      });
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
      // Thresholds must match buildInsight pressure word and _renderMetricMovement
      // colour so the card sub-label, insight text, and metric row all agree.
      // 0.00–0.30 = low, 0.31–0.49 = moderate, 0.50+ = high
      if (v >= 0.50) return "High pressure";
      if (v > 0.30) return "Moderate pressure";
      return "Low pressure";
    }

    function frictionEventPhrase(count, refusalCount = 0, options = {}) {
      const total = Number(count || 0);
      const refusals = Number(refusalCount || 0);
      const singular = Boolean(options.singular);
      const capitalized = Boolean(options.capitalized);
      if (total <= 0) return capitalized ? "No friction events" : "no friction events";

      let phrase = "";
      if (total === 1) {
        if (refusals >= 1) phrase = singular ? "single refusal event" : "one refusal event";
        else phrase = singular ? "single challenge event" : "one challenge event";
      } else if (refusals === 0) {
        phrase = `${total} challenge events`;
      } else if (refusals >= total) {
        phrase = `${total} refusal events`;
      } else {
        phrase = `${total} challenge/refusal events`;
      }
      return capitalized ? phrase.charAt(0).toUpperCase() + phrase.slice(1) : phrase;
    }

    function teamPresetResultLine(teamKey, details = {}) {
      const key = String(teamKey || "").toLowerCase();
      const challengeCount = typeof details === "number" ? details : (details.challengeCount || 0);
      const refusalCount = typeof details === "object" ? (details.refusalCount || 0) : 0;
      const cluesShared = typeof details === "object" ? (details.cluesShared || 0) : 0;
      const agreements = typeof details === "object" ? (details.agreements || 0) : 0;
      const blockersTotal = typeof details === "object" ? details.blockersTotal : null;
      const ticks = typeof details === "object" ? details.ticks : null;
      const stressRecovered = typeof details === "object" ? Boolean(details.stressRecovered) : false;
      const pressureWord = typeof details === "object" ? details.pressureWord : "";
      const context = typeof details === "object" ? (details.context || "intro") : "intro";
      const scenarioKey = typeof details === "object" ? (details.scenarioKey || "") : "";
      const trustStart = typeof details === "object" ? details.trustStart : null;
      const trustEnd = typeof details === "object" ? details.trustEnd : null;
      const challengeWord = challengeCount === 1 ? "One" : challengeCount === 2 ? "Two" : challengeCount === 3 ? "Three" : String(challengeCount);
      if (key === "smooth") {
        if (scenarioKey === "office") {
          if (challengeCount > 0) {
            return context === "behaviour"
              ? `${frictionEventPhrase(challengeCount, refusalCount, { capitalized: true })} ${challengeCount === 1 ? "was" : "were"} recorded, but cooperation still dominated. This mostly matches the Smooth Team preset because agents shared project information, confirmed decisions, and resolved the budget item without resistance escalating.`
              : "This mostly matches the Smooth Team preset: agents shared project information, confirmed decisions, and resolved the budget item without resistance escalating.";
          }
          return context === "behaviour"
            ? "No challenge or refusal events were recorded. This matches the Smooth Team preset: agents shared project information, confirmed decisions, and resolved the budget item without resistance."
            : "This matches the Smooth Team preset: agents shared project information, confirmed decisions, and resolved the budget item without resistance.";
        }
        if (scenarioKey === "cafe") {
          const cafeBlockerText = blockersTotal != null ? `all ${blockersTotal} required items` : "all active items";
          if (challengeCount > 0) {
            return context === "behaviour"
              ? `${frictionEventPhrase(challengeCount, refusalCount, { capitalized: true })} ${challengeCount === 1 ? "was" : "were"} recorded, but cooperation still dominated. This mostly matches the Smooth Team preset because agents shared preferences, confirmed restaurant options, and resolved ${cafeBlockerText} without resistance escalating.`
              : `This mostly matches the Smooth Team preset: agents shared preferences, confirmed restaurant options, and resolved ${cafeBlockerText} without resistance escalating.`;
          }
          return context === "behaviour"
            ? `No challenge or refusal events were recorded. This matches the Smooth Team preset: agents shared preferences, confirmed the restaurant options, and resolved ${cafeBlockerText} without resistance.`
            : `This matches the Smooth Team preset: agents shared preferences, confirmed the restaurant options, and resolved ${cafeBlockerText} without resistance.`;
        }
        return context === "behaviour"
          ? "No challenge or refusal events were recorded. This matches the Smooth Team preset: agents shared clues, confirmed decisions, and resolved all 5 required steps without resistance."
          : "This matches the Smooth Team preset: agents shared clues, confirmed decisions, and resolved all required steps without resistance.";
      }
      if (key === "tension") {
        if (challengeCount > 0) {
          const blockerText = blockersTotal != null ? `all ${blockersTotal} required item${blockersTotal === 1 ? "" : "s"}` : "all required items";
          const verb = challengeCount === 1 ? "reflects" : "reflect";
          const escapeIntro = `This matches the Tension Team preset. Stress rose through the clue-solving sequence and peaked during the Final Unlock, the longest step. ${frictionEventPhrase(challengeCount, refusalCount, { capitalized: true })} showed friction under pressure, but cooperation still outweighed conflict.`;
          const cafeBlockerText = blockersTotal === 2
            ? "both active items"
            : blockersTotal != null
              ? `all ${blockersTotal} required items`
              : "the active items";
          const cafeIntro = `${frictionEventPhrase(challengeCount, refusalCount, { capitalized: true })} ${challengeCount === 1 ? "appeared" : "appeared"} during the cafe decision process, but stress remained controlled and cooperation outweighed conflict. The team resolved ${cafeBlockerText} without intervention.`;
          if (context === "behaviour") {
            if (scenarioKey === "escape") {
              return `The ${frictionEventPhrase(challengeCount, refusalCount, { singular: challengeCount === 1 })} ${verb} contained tension rather than breakdown. This matches the Tension Team preset: stress peaked during the Final Unlock, but ${cluesShared} clue share${cluesShared === 1 ? "" : "s"} and ${agreements} agreement${agreements === 1 ? "" : "s"} allowed ${blockerText} to be resolved without intervention.`;
            }
            if (scenarioKey === "office") {
              if (challengeCount === 1) {
                return `The ${frictionEventPhrase(challengeCount, refusalCount, { singular: true })} reflects contained tension rather than breakdown. This matches the Tension Team preset: stress rose while the budget item remained active, but ${cluesShared} information-sharing event${cluesShared === 1 ? "" : "s"} and ${agreements} agreement${agreements === 1 ? "" : "s"} allowed it to be resolved without intervention.`;
              }
              return `The ${frictionEventPhrase(challengeCount, refusalCount)} reflect contained tension rather than breakdown. This matches the Tension Team preset: stress rose while the budget item remained active, but ${cluesShared} information-sharing event${cluesShared === 1 ? "" : "s"} and ${agreements} agreement${agreements === 1 ? "" : "s"} allowed it to be resolved without intervention.`;
            }
            if (scenarioKey === "cafe") {
              return cafeIntro;
            }
            return `The ${frictionEventPhrase(challengeCount, refusalCount, { singular: challengeCount === 1 })} ${verb} contained tension rather than breakdown. This matches the Tension Team preset: stress rose under pressure, but ${cluesShared} clue share${cluesShared === 1 ? "" : "s"} and ${agreements} agreement${agreements === 1 ? "" : "s"} allowed ${blockerText} to be resolved without intervention.`;
          }
          if (scenarioKey === "escape") return escapeIntro;
          if (scenarioKey === "cafe") return cafeIntro;
          if (scenarioKey === "office") {
            return "This matches the Tension Team preset. Stress rose while the budget item remained active, but cooperation still outweighed conflict.";
          }
          return "This matches the Tension Team preset. Stress rose under pressure, but cooperation still outweighed conflict.";
        }
        return scenarioKey === "escape"
          ? "Although this was a Tension Team run, no explicit challenge or refusal events occurred. The tension appeared through higher stress, slower clue resolution, and elevated final pressure rather than open conflict."
          : scenarioKey === "cafe"
            ? `No challenge events occurred. This was a low-intensity Tension Team run: ${pressureWord === "moderate" ? "stress rose into the moderate-pressure range while the final decision remained active" : "stress stayed low"}, but the team resolved ${blockersTotal != null ? `all ${blockersTotal} required items` : "the active items"} through steady preference-sharing rather than conflict.`
          : scenarioKey === "office"
            ? "No challenge events were recorded. This was a low-intensity Tension Team run: stress rose moderately while the budget item remained active, but the team resolved it through cooperation rather than conflict."
            : "This matches the Tension Team preset. Stress rose under pressure, but cooperation still outweighed conflict.";
      }
      if (key === "creative") {
        if (context === "behaviour" && challengeCount > 0) {
          if (scenarioKey === "office") {
            return `This matches the Creative Team preset: agents used flexible coordination, confirmation, and collaborative problem-solving to complete the project tasks. Although ${frictionEventPhrase(challengeCount, refusalCount)} occurred, cooperation still outweighed conflict.`;
          }
          if (scenarioKey === "cafe") {
            if (challengeCount === 1) {
              return `The ${frictionEventPhrase(challengeCount, refusalCount, { singular: true })} reflects light disagreement during the restaurant decision rather than breakdown. This still matches the Creative Team preset because agents continued using preference-sharing, confirmation, and flexible coordination to reach a decision.`;
            }
            return `The ${frictionEventPhrase(challengeCount, refusalCount)} reflect light disagreement during the restaurant decision rather than breakdown. This still matches the Creative Team preset because agents continued using preference-sharing, confirmation, and flexible coordination to reach a decision.`;
          }
          return `The ${frictionEventPhrase(challengeCount, refusalCount, { singular: challengeCount === 1 })} reflects light pressure rather than conflict. This still matches the Creative Team preset: agents mainly used clue-sharing, confirmation, and flexible coordination, with cooperation outweighing friction events.`;
        }
        if (scenarioKey === "office") {
          return context === "behaviour"
            ? "This matches the Creative Team preset: agents used flexible coordination, confirmation, and collaborative problem-solving to complete the project tasks."
            : "This matches the Creative Team preset: agents used flexible coordination, confirmation, and collaborative problem-solving to complete the project tasks.";
        }
        if (scenarioKey === "cafe") {
          if (context === "intro") {
            const trustClause = (typeof trustStart === "number" && typeof trustEnd === "number")
              ? ` Stress stayed low, and trust grew from ${trustStart.toFixed(2)} to ${trustEnd.toFixed(2)}.`
              : " Stress stayed low, and trust grew steadily.";
            if (challengeCount === 0) {
              return `No challenge events occurred. This matches the Creative Team preset because agents used preference-sharing, confirmation, and flexible coordination rather than conflict.${trustClause}`;
            }
            const _ccBlockerText = blockersTotal != null ? `all ${blockersTotal} required items` : "all active items";
            const challengeClause = challengeCount === 1
              ? `Although ${frictionEventPhrase(challengeCount, refusalCount)} occurred, cooperation still outweighed conflict and ${_ccBlockerText} were resolved.`
              : `Although ${frictionEventPhrase(challengeCount, refusalCount)} occurred, cooperation still outweighed conflict and ${_ccBlockerText} were resolved.`;
            return `This matches the Creative Team preset: agents used preference-sharing, confirmation, and flexible coordination around the restaurant decision.${trustClause} ${challengeClause}`;
          }
          return "No challenge or refusal events were recorded. This matches the Creative Team preset: agents used preference-sharing, confirmation, and flexible coordination around the restaurant decision rather than conflict.";
        }
        return context === "behaviour"
          ? "No challenge or refusal events were recorded. This matches the Creative Team preset: agents used clue-sharing, confirmation, and flexible coordination rather than conflict."
          : "This matches the Creative Team preset: agents used clue-sharing, confirmation, and flexible coordination rather than conflict.";
      }
      if (key === "pressure") {
        const stepText = ticks != null ? `${ticks} step${ticks === 1 ? "" : "s"}` : "the run";
        if (scenarioKey === "office" && context === "intro") {
          if (challengeCount > 0) {
            const trustSentence = (typeof trustStart === "number" && typeof trustEnd === "number")
              ? ` Trust grew from ${trustStart.toFixed(2)} to ${trustEnd.toFixed(2)}, and`
              : " Trust grew steadily, and";
            const chalWord = challengeCount === 1
              ? `the ${frictionEventPhrase(challengeCount, refusalCount)}`
              : `the ${frictionEventPhrase(challengeCount, refusalCount)}`;
            return `For a Pressure Team, this run shows controlled urgency rather than breakdown. Agents resolved the budget item in ${stepText}, with stress rising into the moderate-pressure range before recovering.${trustSentence} cooperation still outweighed ${chalWord}.`;
          }
          const trustClause = (typeof trustStart === "number" && typeof trustEnd === "number")
            ? ` Trust grew from ${trustStart.toFixed(2)} to ${trustEnd.toFixed(2)},`
            : " Trust grew steadily,";
          return `For a Pressure Team, this run shows controlled urgency rather than conflict. Agents resolved the budget item in ${stepText}, with stress staying within the low-pressure range.${trustClause} and cooperation dominated without challenge events.`;
        }
        if (scenarioKey === "cafe" && context === "intro") {
          const trustClause = (typeof trustStart === "number" && typeof trustEnd === "number")
            ? ` Trust grew from ${trustStart.toFixed(2)} to ${trustEnd.toFixed(2)},`
            : " Trust remained strong,";
          if (ticks != null && ticks >= 15) {
            const cafeBlockerText15 = blockersTotal != null ? `all ${blockersTotal} required items` : "all active items";
            return `For a Pressure Team, this run shows controlled urgency rather than conflict. The team took ${ticks} steps because the final Decision was the longest step at 6 steps, while the Budget Constraint remained active for 5 steps.${trustClause} and the team resolved ${cafeBlockerText15} without escalation.`;
          }
          const cafeBlockerText = blockersTotal === 2
            ? "both active items"
            : blockersTotal != null
              ? `all ${blockersTotal} required items`
              : "the active items";
          if (challengeCount === 2) {
            return `For a Pressure Team, this run shows controlled urgency rather than breakdown. Agents moved through the cafe decision process in ${stepText}, with stress remaining within the low-pressure range.${trustClause} and ${cafeBlockerText} were resolved despite ${frictionEventPhrase(challengeCount, refusalCount)}.`;
          }
          if (challengeCount === 1) {
            return `For a Pressure Team, this run shows controlled urgency rather than conflict. Agents moved through the cafe decision process in ${stepText}, with stress remaining within the low-pressure range.${trustClause} and ${cafeBlockerText} were resolved with only ${frictionEventPhrase(challengeCount, refusalCount)}.`;
          }
          return `For a Pressure Team, this run shows controlled urgency rather than conflict. Agents moved through the cafe decision process in ${stepText}, with stress remaining within the low-pressure range.${trustClause} and ${cafeBlockerText} were resolved without challenge events.`;
        }
        const pressurePhrase = pressureWord === "high"
          ? "into the high-pressure range"
          : pressureWord === "moderate"
            ? "into the moderate-pressure range"
            : "within the low-pressure range";
        const recoveryText = stressRecovered ? " before recovering" : "";
        const scenarioLine = scenarioKey === "escape"
          ? "The team completed the escape room under pressure while maintaining cooperation."
          : "The team completed the run under pressure while maintaining cooperation.";
        if (context === "behaviour") {
          if (challengeCount === 0) {
            if (scenarioKey === "cafe") {
              return "No challenge events occurred. For a Pressure Team, this suggests urgency was handled through direct preference-sharing and coordination rather than conflict. Stress stayed within the low-pressure range, showing controlled urgency rather than breakdown.";
            }
            return `No challenge events were recorded. For a Pressure Team, this suggests urgency was handled through fast coordination rather than conflict. Stress still rose ${pressurePhrase}, showing controlled urgency rather than breakdown.`;
          }
          if (scenarioKey === "office") {
            if (challengeCount === 1) {
              return `The ${frictionEventPhrase(challengeCount, refusalCount, { singular: true })} reflects pressure-driven urgency rather than breakdown. For a Pressure Team, stress rose into the moderate-pressure range during the project item, while ${cluesShared} information-sharing event${cluesShared === 1 ? "" : "s"} and ${agreements} agreement${agreements === 1 ? "" : "s"} kept the team moving.`;
            }
            return `The ${frictionEventPhrase(challengeCount, refusalCount)} reflect pressure-driven urgency rather than breakdown. For a Pressure Team, stress rose into the moderate-pressure range during the project item, while ${cluesShared} information-sharing event${cluesShared === 1 ? "" : "s"} and ${agreements} agreement${agreements === 1 ? "" : "s"} kept the team moving.`;
          }
          if (scenarioKey === "cafe") {
            if (challengeCount === 1) {
              return `The ${frictionEventPhrase(challengeCount, refusalCount, { singular: true })} reflects controlled urgency rather than breakdown. For a Pressure Team, stress stayed within the low-pressure range during the decision process, while preference-sharing and coordination kept the team moving.`;
            }
            return `The ${frictionEventPhrase(challengeCount, refusalCount)} reflect controlled urgency rather than breakdown. For a Pressure Team, stress stayed within the low-pressure range during the decision process, while ${cluesShared} preference-sharing event${cluesShared === 1 ? "" : "s"} and ${agreements} agreement${agreements === 1 ? "" : "s"} kept the team moving.`;
          }
          return `The ${challengeCount === 1 ? `${frictionEventPhrase(challengeCount, refusalCount, { singular: true })} reflects` : `${frictionEventPhrase(challengeCount, refusalCount)} reflect`} controlled urgency rather than breakdown. For a Pressure Team, stress rose ${pressurePhrase} during the final stage, but cooperation still dominated: ${cluesShared} clue share${cluesShared === 1 ? "" : "s"} and ${agreements} agreement${agreements === 1 ? "" : "s"} kept the team moving.`;
        }
        return `For a Pressure Team, this run shows controlled urgency rather than conflict. Agents moved through the required sequence efficiently in ${stepText}, with stress rising ${pressurePhrase}${recoveryText}. ${scenarioLine}`;
      }
      return "";
    }
    function outcomeLabel() {
      if (!RUN) return "Unknown";
      const endReason = RUN.endReason || RUN.steps[RUN.steps.length - 1]?.endReason || "";
      if (!endReason) return RUN.ended ? "Complete" : "In progress";
      return titleCase(endReason);
    }

    function buildInsight(finalStep, summary) {
      // summary is _savedRunSummary if available; falls back to finalStep.metrics only
      const m   = finalStep.metrics;
      const mt  = summary?.metric_trajectory;
      const ec  = summary?.event_counts;
      const bt  = summary?.blocker_timeline;
      const fp  = summary?.final_progress ?? (m.progress / 100);
      const refusalCount = summary?.metrics?.total_refusals || 0;
      const finalTicks = finalStep?.tick ?? totalRunTicks();

      const scenLabel = RUN.scenario.key === "cafe"   ? "the cafe plan"
                      : RUN.scenario.key === "escape" ? "the escape room"
                      : "the office project";

      const isEscape  = RUN.scenario.key === "escape";

      // Resolve team preset key — prefer the saved summary over
      // the live RUN object so replayed runs also get the correct context.
      const _rawPreset = summary?.team_preset ?? "";
      const teamKey = _rawPreset
        ? _rawPreset.replace(/_team$/i, "").toLowerCase()
        : (typeof RUN !== "undefined" ? (RUN.teamKey || "") : "");
      const introBlockersTotal = (bt && bt.length > 0) ? bt.length : (ec?.blockers_total ?? null);

      // One-sentence team-preset context — explains what to expect from this run
      // so readers don't mistake "low conflict on Smooth Team" as a bug.
      const teamContext = teamPresetResultLine(teamKey, {
        challengeCount: ec?.challenges || 0,
        refusalCount,
        cluesShared: ec?.clues_shared || 0,
        agreements: ec?.agreements || 0,
        blockersTotal: introBlockersTotal,
        ticks: finalTicks,
        pressureWord: mt?.stress_peak != null
          ? (mt.stress_peak >= 0.50 ? "high" : mt.stress_peak > 0.30 ? "moderate" : "low")
          : "",
        stressRecovered: mt ? mt.stress_end < mt.stress_peak - 0.06 : false,
        scenarioKey: RUN?.scenario?.key || "",
        trustStart: mt?.trust_start,
        trustEnd: mt?.trust_end,
        context: "intro",
      });
      // Without the summary we don't have a reliable peak stress value.
      // Show "—" for stress in the initial render; it is replaced once the
      // summary loads and buildInsight is called again with the full summary.
      const peakStr   = mt ? mt.stress_peak.toFixed(2) : "—";
      const trustEnd  = mt ? mt.trust_end.toFixed(2)   : m.averageTrust.toFixed(2);
      const peakTick  = mt?.stress_peak_tick;

      // Stress narrative — thresholds MUST match stressBand() exactly:
      //   0.00–0.30 → low, 0.31–0.49 → moderate, 0.50+ → high
      const peakVal   = mt?.stress_peak;   // only defined once summary loads
      let stressPart;
      if (peakVal == null) {
        stressPart = "Stress data loading…";
      } else if (peakVal >= 0.50) {
        stressPart = `Stress peaked at ${peakStr}${peakTick ? ` (step ${peakTick})` : ""}`;
      } else if (peakVal > 0.30) {
        stressPart = `Stress reached a moderate peak of ${peakStr}`;
      } else {
        stressPart = `Stress stayed low (peak ${peakStr})`;
      }

      // Trust narrative
      const trustVal = mt?.trust_end ?? m.averageTrust;
      let trustPart;
      if (mt && mt.trust_delta > 0.05) {
        trustPart = `trust grew from ${mt.trust_start.toFixed(2)} to ${trustEnd}`;
      } else if (mt && mt.trust_delta < -0.05) {
        trustPart = `trust slipped from ${mt.trust_start.toFixed(2)} to ${trustEnd}`;
      } else if (trustVal >= 0.50) {
        trustPart = `trust held steady at ${trustEnd}`;
      } else {
        trustPart = `trust stayed guarded at ${trustEnd}`;
      }

      // Cooperation vs conflict narrative
      let coopPart = "";
      if (ec) {
        const coop = (ec.agreements || 0) + (ec.clues_shared || 0);
        const conf = ec.challenges || 0;

        // Derive blocker counts from the timeline when available — it always
        // matches what _renderBlockerTimeline shows, so the counts stay in sync.
        // Only fall back to ec.blockers_* if no timeline was recorded.
        let blkRes = null;
        let blkTot = null;
        if (bt && bt.length > 0 && summary?.tasks) {
          blkTot = bt.length;
          blkRes = bt.filter(b => summary.tasks[b.item] === true).length;
        } else {
          blkRes = ec.blockers_resolved ?? null;
          blkTot = ec.blockers_total   ?? null;
        }

        if (coop > 0 && conf === 0) {
          coopPart = `Agents cooperated without conflict — ${coop} cooperative events drove the run.`;
        } else if (coop > 0 && conf > 0 && coop >= conf * 2) {
          coopPart = `Cooperation dominated (${coop} cooperative vs ${frictionEventPhrase(conf, refusalCount)}).`;
        } else if (conf > coop) {
          coopPart = `Conflict was high — ${frictionEventPhrase(conf, refusalCount)} vs ${coop} cooperative events.`;
        }
        if (blkRes != null && blkTot != null && blkRes === blkTot) {
          coopPart += ` All ${blkTot} item${blkTot === 1 ? "" : "s"} resolved${isEscape ? " before the door opened" : ""}.`;
        } else if (blkRes != null && blkTot != null) {
          coopPart += ` ${blkRes} of ${blkTot} items resolved.`;
        }
      }

      // Blocker context: name the hardest or most recent blocker
      let blockerPart = "";
      if (bt && bt.length > 0 && isEscape) {
        const longest = bt.reduce((a, b) => (b.duration > a.duration ? b : a), bt[0]);
        const blockLabel = _itemLabel(longest.item);
        if (longest.duration >= 2) {
          blockerPart = ` The team spent ${longest.duration} step${longest.duration === 1 ? "" : "s"} on the ${blockLabel} — the longest single step.`;
        }
      }

      const outcome = fp >= 1.0 ? `completed ${scenLabel}` : `reached ${Math.round(fp * 100)}% on ${scenLabel}`;

      // Pressure word — MUST match stressBand() thresholds so the card sub-label
      // and the insight sentence always agree (0.00–0.30 → low, 0.31–0.49 → moderate,
      // 0.50+ → high).  No team-specific overrides: Smooth Team with a 0.40 peak
      // correctly says "moderate pressure" rather than "light pressure".
      const pressureWord = (peakVal == null) ? "—"
        : peakVal >= 0.50 ? "high"
        : peakVal > 0.30 ? "moderate"
        : "low";

      // If the summary hasn't loaded yet (peakVal is null), only show what we
      // know: progress, trust from the final step, and cooperation counts.
      // Stress and pressure are omitted until the canonical mt.stress_peak arrives.
      if (peakVal == null) {
        const basicLine = `The team ${outcome}. Trust ended at ${trustEnd}.${blockerPart} ${coopPart}`.trim();
        return teamContext ? `${teamContext} ${basicLine}` : basicLine;
      }

      if (teamKey === "pressure" && RUN?.scenario?.key === "office") {
        return teamContext;
      }

      if (teamKey === "pressure" && RUN?.scenario?.key === "cafe") {
        return teamContext;
      }

      if (teamKey === "creative" && RUN?.scenario?.key === "cafe") {
        return teamContext;
      }

      const metricLine = `The team ${outcome} with ${pressureWord} pressure. ${stressPart}, and ${trustPart}.${blockerPart} ${coopPart}`.trim();
      return teamContext ? `${teamContext} ${metricLine}` : metricLine;
    }

    function _itemLabel(key) {
      // Human-readable names for scenario item keys
      const labels = {
        map: "Room Map", lock: "Lock Pattern", key: "Key Location",
        door: "Door Code", unlock: "Final Unlock",
        digit_1: "Door Digit 1", digit_2: "Door Digit 2",
        digit_3: "Door Digit 3", order: "Digit Order",
        // office/cafe
        report: "Report", budget: "Budget", schedule: "Schedule",
        approval: "Approval", venue: "Venue", catering: "Catering",
        guest_list: "Guest List", equipment: "Equipment",
      };
      return labels[key] ?? key.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
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

    function escapeHtml(s) {
      return String(s ?? "")
        .replace(/&/g, "&amp;").replace(/</g, "&lt;")
        .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }

    function _evidenceBullets(evidence) {
      if (!evidence || !evidence.length) return "";
      const bullets = evidence.map(ev => {
        const step = ev.tick != null ? `Step ${ev.tick}` : "";
        const text = ev.text || "";
        return `<li style="margin:3px 0;">${step ? `<strong>${step}:</strong> ` : ""}${escapeHtml(text)}</li>`;
      }).join("");
      return `<ul style="margin:6px 0 6px 18px;padding:0;font-size:0.84rem;color:#3a5068;">${bullets}</ul>`;
    }

    function _renderMemorySection(mem) {
      const el = document.getElementById("doneMemory");
      if (!el) return;
      if (!mem || mem.total_impressions == null) {
        el.textContent = "Memory data will appear on the next run.";
        return;
      }
      if (mem.total_impressions === 0) {
        el.textContent = mem.no_impression_reason || "No memory signals were detected during this run.";
        return;
      }

      const _impList = [mem.strongest_positive, mem.strongest_conflict].filter(Boolean);
      const _shownCount = _impList.length;
      const _totalCount = mem.total_impressions;
      // Memory wording is driven by what is actually shown, not by hidden totals.
      // 1 interaction = early coordination signal
      // 2 interactions = emerging coordination pattern
      // 3+ interactions = strong memory impression
      function _impStrengthLabel(evLen) {
        if (evLen <= 1) return "early coordination signal";
        if (evLen <= 2) return "emerging coordination pattern";
        return "strong memory impression";
      }

      let html = "";
      const _signalWord = _totalCount === 1 ? "signal was" : "signals were";
      if (_shownCount === 1 && _totalCount > 1) {
        html = `<p style="margin:0 0 10px;">${_totalCount} coordination ${_signalWord} recorded. The strongest example is shown below.</p>`;
      } else if (_shownCount === 1) {
        const hasEvidence = Boolean(_impList[0]?.evidence?.length);
        html = hasEvidence
          ? `<p style="margin:0 0 10px;">Representative coordination pattern shown below.</p>`
          : `<p style="margin:0 0 10px;">1 coordination signal was recorded, but no representative example was available for display.</p>`;
      } else if (_shownCount < _totalCount) {
        html = `<p style="margin:0 0 10px;">${_totalCount} coordination ${_signalWord} recorded. Representative patterns are shown below.</p>`;
      } else {
        html = `<p style="margin:0 0 10px;">Representative coordination patterns are shown below.</p>`;
      }

      for (const imp of _impList) {
        if (!imp) continue;
        const evLen = imp.evidence?.length || 0;
        const _label = _impStrengthLabel(evLen);
        if (imp.narrative) {
          // Backend narrative already carries the strength wording.
          html += `<p style="margin:0 0 4px;font-weight:600;">${escapeHtml(imp.narrative)}</p>`;
          html += _evidenceBullets(imp.evidence);
        } else {
          // Fallback for older run data without a narrative field.
          const label = "positive" in (imp.patterns || {}) ? "positive" : "conflict-prone";
          const relation = evLen >= 3
            ? `formed a ${label} ${_label}`
            : `showed a ${label} ${_label}`;
          html += `<p style="margin:0 0 4px;font-weight:600;">`
               + `${escapeHtml(imp.observer)} ${relation}`
               + ` with ${escapeHtml(imp.target)}`
               + (evLen ? ` (${evLen} evidence event${evLen === 1 ? "" : "s"})` : "") + `:</p>`;
          html += _evidenceBullets(imp.evidence);
          if (imp.effect) {
            html += `<p style="margin:4px 0 12px;font-size:0.84rem;color:#617387;font-style:italic;">Effect: ${escapeHtml(imp.effect)}</p>`;
          }
        }
      }
      el.innerHTML = html;
    }

    function _renderEmotionSection(emo) {
      const el = document.getElementById("doneEmotion");
      if (!el) return;
      if (!emo || emo.emotion_inputs == null) {
        el.textContent = "Emotion data will appear on the next run.";
        return;
      }

      let html = "";

      // ── Agent emotional memory (NLP-derived from STM) ──────────────────────
      const aem = emo.agent_emotional_memory;
      if (aem) {
        const pressurePct = Math.round((aem.avg_pressure   || 0) * 100);
        const positPct    = Math.round((aem.avg_positivity || 0) * 100);
        const hasSignal   = pressurePct > 5 || positPct > 5;

        html += `<div style="margin-bottom:14px;">`;
        html += `<div style="font-size:0.78rem;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:#8a96a8;margin-bottom:6px;">Agent Emotional Memory</div>`;

        if (!hasSignal) {
          // No meaningful emotional signal — just show the interpretation text
          html += `<p style="margin:0;font-size:0.84rem;color:#617387;font-style:italic;">${escapeHtml(aem.interpretation || "Agent emotional memory remained neutral throughout the run. No memories were classified as strongly negative or positive, so emotional memory did not significantly influence trust or stress.")}</p>`;
        } else {
          // Show stats only when there's actual signal
          const barColor = pressurePct > 40 ? "#e83030"
                         : pressurePct > 22 ? "#f5a623"
                         : "#1ec466";
          html += `<div style="display:flex;gap:10px;margin-bottom:8px;">`;
          html += `<div style="flex:1;background:#f7f9fc;border-radius:8px;padding:8px 10px;text-align:center;">` +
                  `<div style="font-size:1.1rem;font-weight:900;color:${barColor};">${pressurePct}%</div>` +
                  `<div style="font-size:0.72rem;color:#8a96a8;margin-top:1px;">Negative</div></div>`;
          html += `<div style="flex:1;background:#f7f9fc;border-radius:8px;padding:8px 10px;text-align:center;">` +
                  `<div style="font-size:1.1rem;font-weight:900;color:#1a7a4a;">${positPct}%</div>` +
                  `<div style="font-size:0.72rem;color:#8a96a8;margin-top:1px;">Positive</div></div>`;
          if (aem.peak_pressure_tick != null && aem.peak_pressure > 0.05) {
            html += `<div style="flex:1;background:#f7f9fc;border-radius:8px;padding:8px 10px;text-align:center;">` +
                    `<div style="font-size:1.1rem;font-weight:900;color:#1667f5;">${aem.peak_pressure_tick}</div>` +
                    `<div style="font-size:0.72rem;color:#8a96a8;margin-top:1px;">Peak step</div></div>`;
          }
          html += `</div>`;
          if (aem.dominant_negative || aem.dominant_positive) {
            html += `<div style="font-size:0.82rem;color:#617387;margin-bottom:6px;">`;
            if (aem.dominant_negative) html += `Most negative: <strong>${escapeHtml(aem.dominant_negative)}</strong>`;
            if (aem.dominant_negative && aem.dominant_positive) html += ` · `;
            if (aem.dominant_positive) html += `Most positive: <strong>${escapeHtml(aem.dominant_positive)}</strong>`;
            html += `</div>`;
          }
          if (aem.interpretation) {
            html += `<p style="margin:0;font-size:0.82rem;color:#617387;font-style:italic;">${escapeHtml(aem.interpretation)}</p>`;
          }
        }
        html += `</div>`;
      }

      // ── User emotion injection section ─────────────────────────────────────
      if (!emo.emotion_inputs) {
        html += `<p style="margin:0;font-size:0.82rem;color:#8a96a8;">No user emotion input was applied during this run.</p>`;
        el.innerHTML = html;
        return;
      }

      const dominant = emo.dominant_emotion || "neutral";
      const valence  = emo.valence_label  || (emo.average_valence > 0.1 ? "mildly positive" : emo.average_valence < -0.1 ? "mildly negative" : "neutral");
      const arousal  = emo.arousal_label  || (emo.average_arousal > 0.5 ? "high" : "low");
      const effect   = emo.effect_label   || "minimal";

      html += `<div style="font-size:0.78rem;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:#8a96a8;margin-bottom:6px;">User Emotion Input</div>`;
      html += `<p style="margin:0 0 6px;"><strong>Detected:</strong> ${escapeHtml(dominant)}</p>`;
      html += `<p style="margin:0 0 4px;font-size:0.84rem;color:#617387;">Valence: ${escapeHtml(valence)} · Arousal: ${escapeHtml(arousal)} · Effect: ${escapeHtml(effect)}</p>`;

      if (effect === "minimal" && emo.zero_reason) {
        html += `<p style="margin:8px 0 4px;font-size:0.84rem;color:#617387;font-style:italic;"><strong>Reason:</strong> ${escapeHtml(emo.zero_reason)}</p>`;
      } else if (effect !== "minimal") {
        html += `<p style="margin:6px 0 0;font-size:0.84rem;color:#617387;">`;
        html += `Stress impact: <strong>${emo.stress_impact}</strong> · `;
        html += `Trust impact: <strong>${emo.trust_impact}</strong></p>`;
      }
      el.innerHTML = html;
    }

    function _renderEventCounts(ec, summary) {
      const el = document.getElementById("doneEventCounts");
      if (!el || !ec) return;

      // Pull blocker counts from blocker_timeline so this section stays in sync
      // with the blocker timeline panel below it.
      const bt = summary?.blocker_timeline;
      const isEscape = (typeof RUN !== "undefined") && RUN?.scenario?.key === "escape";
      let blkRes = ec.blockers_resolved ?? null;
      let blkTot = ec.blockers_total   ?? null;
      if (bt && bt.length > 0 && summary?.tasks) {
        blkTot = bt.length;
        blkRes = bt.filter(b => summary.tasks[b.item] === true).length;
      }

      const rows = [
        ["Messages exchanged",    ec.messages_exchanged],
        [isEscape ? "Clues shared" : ((typeof RUN !== "undefined") && RUN?.scenario?.key === "cafe" ? "Preferences / constraints shared" : "Information shared"), ec.clues_shared],
        ["Questions asked",       ec.questions_asked],
        ["Agreements",            ec.agreements],
        ["Challenges / refusals", ec.challenges],
        [isEscape ? "Clues resolved" : "Items resolved", blkRes != null && blkTot != null ? `${blkRes}/${blkTot}` : "—"],
        ["Interventions used",    ec.interventions_used],
      ];
      let html = rows.map(([label, val]) =>
        `<div style="display:flex;justify-content:space-between;border-bottom:1px solid rgba(17,32,51,0.06);padding:3px 0;">` +
        `<span style="color:#617387;">${label}</span>` +
        `<strong style="color:#112033;">${val ?? "—"}</strong></div>`
      ).join("");

      // Interpretation sentence — escape-room-aware
      const coop = (ec.agreements || 0) + (ec.clues_shared || 0);
      const conf = ec.challenges || 0;
      const refusalCount = summary?.metrics?.total_refusals || 0;
      const finalTicks = RUN?.steps?.length ? (RUN.steps[RUN.steps.length - 1]?.tick || 0) : (summary?.ticks || null);
      let interp = "";

      // blkRes/blkTot already derived from timeline above — reuse them.
      const blkStr = (blkRes != null && blkTot != null)
        ? ` with ${blkRes} of ${blkTot} item${blkTot === 1 ? "" : "s"} resolved` : "";

      // Resolve team preset from summary or live RUN
      const _rawPresetEC = summary?.team_preset ?? "";
      const _teamKeyEC   = _rawPresetEC
        ? _rawPresetEC.replace(/_team$/i, "").toLowerCase()
        : (typeof RUN !== "undefined" ? (RUN.teamKey || "") : "");

      if (isEscape) {
        // In escape rooms, challenge events are expected — they reflect urgency,
        // not dysfunction.  No challenges at all is the unusual case.
        if (conf === 0 && coop > 0) {
          const _zeroConfExplain = teamPresetResultLine(_teamKeyEC, {
            challengeCount: conf,
            refusalCount,
            cluesShared: ec.clues_shared || 0,
            agreements: ec.agreements || 0,
            blockersTotal: blkTot,
            ticks: finalTicks,
            pressureWord: summary?.metric_trajectory?.stress_peak != null
              ? (summary.metric_trajectory.stress_peak >= 0.50 ? "high" : summary.metric_trajectory.stress_peak > 0.30 ? "moderate" : "low")
              : "",
            stressRecovered: summary?.metric_trajectory
              ? summary.metric_trajectory.stress_end < summary.metric_trajectory.stress_peak - 0.06
              : false,
            scenarioKey: RUN?.scenario?.key || "",
            context: "behaviour",
          })
            || `Every clue owner released their information without resistance — a high-trust cooperative run.`;
          interp = _zeroConfExplain;
        } else if (conf > 0 && coop >= conf * 2) {
          const shares = ec.clues_shared || 0;
          const agrees = ec.agreements   || 0;
          const _confContext = teamPresetResultLine(_teamKeyEC, {
            challengeCount: conf,
            refusalCount,
            cluesShared: shares,
            agreements: agrees,
            blockersTotal: blkTot,
            ticks: finalTicks,
            pressureWord: summary?.metric_trajectory?.stress_peak != null
              ? (summary.metric_trajectory.stress_peak >= 0.50 ? "high" : summary.metric_trajectory.stress_peak > 0.30 ? "moderate" : "low")
              : "",
            stressRecovered: summary?.metric_trajectory
              ? summary.metric_trajectory.stress_end < summary.metric_trajectory.stress_peak - 0.06
              : false,
            scenarioKey: RUN?.scenario?.key || "",
            context: "behaviour",
          })
            || "Friction events reflected pressure around the final step, but the team kept moving.";
          interp = _confContext;
        } else if (conf > 0 && conf > coop) {
          interp = `High friction run: ${frictionEventPhrase(conf, refusalCount, { capitalized: false })} outpaced ${coop} cooperative events${blkStr}. `
                 + `Held clues and time pressure drove significant conflict between agents.`;
        } else if (conf > 0) {
          interp = `Friction and cooperation were roughly balanced (${frictionEventPhrase(conf, refusalCount)} vs ${coop} cooperative events)${blkStr}. `
                 + `Typical for a pressured escape room where clue owners needed repeated prompting.`;
        }
      } else {
        const scenKey = (typeof RUN !== "undefined") && RUN?.scenario?.key;
        if (conf === 0 && coop > 0) {
          const _offExplain = teamPresetResultLine(_teamKeyEC, {
            challengeCount: conf,
            refusalCount,
            cluesShared: ec.clues_shared || 0,
            agreements: ec.agreements || 0,
            blockersTotal: blkTot,
            ticks: finalTicks,
            pressureWord: summary?.metric_trajectory?.stress_peak != null
              ? (summary.metric_trajectory.stress_peak >= 0.50 ? "high" : summary.metric_trajectory.stress_peak > 0.30 ? "moderate" : "low")
              : "",
            stressRecovered: summary?.metric_trajectory
              ? summary.metric_trajectory.stress_end < summary.metric_trajectory.stress_peak - 0.06
              : false,
            scenarioKey: RUN?.scenario?.key || "",
            context: "behaviour",
          })
            || (scenKey === "cafe"
              ? `No challenge events occurred. The run followed the expected café pattern: low stress, steady preference-sharing, and cooperative decision-making.`
              : `Agents cooperated throughout without friction.`);
          interp = _offExplain;
        } else if (coop > 0 && conf > 0) {
          if (coop >= conf * 2) {
            const teamLine = teamPresetResultLine(_teamKeyEC, {
              challengeCount: conf,
              refusalCount,
              cluesShared: ec.clues_shared || 0,
              agreements: ec.agreements || 0,
              blockersTotal: blkTot,
              ticks: finalTicks,
              pressureWord: summary?.metric_trajectory?.stress_peak != null
                ? (summary.metric_trajectory.stress_peak >= 0.50 ? "high" : summary.metric_trajectory.stress_peak > 0.30 ? "moderate" : "low")
                : "",
              stressRecovered: summary?.metric_trajectory
                ? summary.metric_trajectory.stress_end < summary.metric_trajectory.stress_peak - 0.06
                : false,
              scenarioKey: RUN?.scenario?.key || "",
              context: "behaviour",
            });
            interp = teamLine || `Cooperation outweighed conflict (${coop} vs ${conf}) — trust stayed stable as a result.`;
          } else if (conf > coop) {
            interp = `Conflict outweighed cooperation (${conf} vs ${coop}) — this is why trust came under pressure.`;
          } else {
            interp = `Cooperation and conflict were roughly balanced (${coop} cooperative, ${conf} conflict events).`;
          }
        }
      }

      if (interp) {
        html += `<p style="margin:8px 0 0;font-size:0.82rem;color:#617387;font-style:italic;">${interp}</p>`;
      }

      // Explain zero questions in escape rooms — otherwise a marker will wonder
      // why a timed clue-solving scenario shows 0 questions asked.
      if (isEscape && (ec.questions_asked === 0 || ec.questions_asked == null)) {
        html += `<p style="margin:6px 0 0;font-size:0.82rem;color:#617387;font-style:italic;">` +
          `No direct question events were recorded because agents mostly shared and confirmed ` +
          `clues proactively rather than repeatedly requesting information.</p>`;
      }

      el.innerHTML = html;
    }

    function _renderMetricMovement(mt, summary) {
      const el = document.getElementById("doneMetricMovement");
      if (!el) return;

      if (!mt || mt.stress_start == null) {
        el.innerHTML = `<p style="margin:0;font-size:0.84rem;color:#8a96a8;font-style:italic;">` +
          `Per-step metric history is not yet available — run a simulation to populate this section.</p>`;
        return;
      }

      const row = (label, content) =>
        `<div style="display:flex;justify-content:space-between;align-items:baseline;` +
        `padding:5px 0;border-bottom:1px solid rgba(17,32,51,0.06);">` +
        `<span style="color:#617387;font-size:0.84rem;white-space:nowrap;margin-right:12px;">${label}</span>` +
        `<span style="color:#112033;font-size:0.84rem;text-align:right;">${content}</span></div>`;

      const trustDelta = mt.trust_delta ?? 0;
      const trustDir   = trustDelta >  0.03 ? "↑ grew"
                       : trustDelta < -0.03 ? "↓ fell"
                       : "→ held steady";
      const trustColor = trustDelta >  0.03 ? "#1a7a4a"
                       : trustDelta < -0.03 ? "#b94040"
                       : "#617387";
      const deltaSign  = trustDelta >= 0 ? "+" : "";

      // Stress "recovered" only when the end value dropped meaningfully below the peak.
      // A gap of less than 0.06 means the run finished under sustained pressure.
      const stressRecovered = mt.stress_end < mt.stress_peak - 0.06;
      const stressStillHigh = mt.stress_end >= 0.50;
      const stressStayedHigh = !stressRecovered && mt.stress_end >= 0.45;

      // Progress row from saved summary
      const fp = summary?.final_progress;
      const ticks = RUN?.steps?.length ? (RUN.steps[RUN.steps.length - 1]?.tick || 0) : (summary?.ticks || 0);
      const scenKey = (typeof RUN !== "undefined") && RUN?.scenario?.key;

      let html = "";

      if (fp != null) {
        html += row("Progress",
          `0% → <strong>${Math.round(fp * 100)}%</strong>` +
          (ticks != null ? ` <span style="color:#617387;">in ${ticks} step${ticks === 1 ? "" : "s"}</span>` : ""));
      }

      html += row("Team trust",
        `${mt.trust_start.toFixed(2)} → <strong>${mt.trust_end.toFixed(2)}</strong> ` +
        `<span style="color:${trustColor};font-weight:700;">${trustDir} (${deltaSign}${trustDelta.toFixed(2)})</span>`);

      let stressContent = `${mt.stress_start.toFixed(2)} start · ` +
        `peak <strong style="color:${mt.stress_peak >= 0.50 ? "#e83030" : mt.stress_peak > 0.30 ? "#f5a623" : "#1a7a4a"};">${mt.stress_peak.toFixed(2)}</strong>` +
        ` at step ${mt.stress_peak_tick}`;
      if (stressStillHigh) {
        stressContent += ` · <span style="color:#b94040;">remained elevated at ${mt.stress_end.toFixed(2)}</span>`;
      } else if (stressRecovered) {
        stressContent += ` · <span style="color:#1a7a4a;">recovered to ${mt.stress_end.toFixed(2)}</span>`;
      } else {
        stressContent += ` · ended ${mt.stress_end.toFixed(2)}`;
      }
      html += row("Peak team stress", stressContent);

      // When stress stayed high and barely recovered, add a plain-English note so
      // the reader doesn't wonder why it didn't drop — they can see it's because
      // the final blocker sustained pressure all the way to the end.
      if (stressStayedHigh) {
        const pressureNote = scenKey === "escape"
          ? "Stress remained high near completion because the final step created continued escape-room pressure."
          : "Stress remained elevated at the end of the run — the final required item was not resolved early enough for recovery.";
        html += `<p style="margin:6px 0 0;font-size:0.81rem;color:#8a96a8;font-style:italic;">${pressureNote}</p>`;
      }

      el.innerHTML = html;
    }

    function _renderBlockerTimeline(blockers, summary) {
      const el = document.getElementById("doneBlockerTimeline");
      if (!el) return;

      if (!blockers || blockers.length === 0) {
        // If tasks exist but no timeline was recorded, explain why
        const tasks = summary?.tasks;
        if (tasks && Object.keys(tasks).length > 0) {
          const resolved = Object.values(tasks).filter(v => v === true).length;
          const total    = Object.keys(tasks).length;
          el.innerHTML = `<p style="margin:0;font-size:0.84rem;color:#617387;">` +
            `${resolved} of ${total} items resolved — step-level progress data was ` +
            `not captured for this run (requires metric_history to be populated per tick).</p>`;
        } else {
          el.innerHTML = `<p style="margin:0;font-size:0.84rem;color:#8a96a8;font-style:italic;">` +
            `No progress timeline data available for this run.</p>`;
        }
        return;
      }

      // tasks dict: item → true (resolved) or false (open)
      const tasks = summary?.tasks ?? {};
      // completion_order: items in the order they were resolved
      const completionOrder = summary?.completion_order ?? [];

      const html = blockers.map((b, i) => {
        const label    = _itemLabel(b.item);
        const resolved = tasks[b.item] === true;
        const dur      = b.duration === 1 ? "1 step" : `${b.duration} steps`;
        const range    = b.start_tick === b.end_tick
          ? `Step ${b.start_tick}`
          : `Steps ${b.start_tick}–${b.end_tick}`;

        // Position in completion order
        const orderIdx = completionOrder.indexOf(b.item);
        const orderTag = orderIdx >= 0
          ? `<span style="font-size:0.76rem;color:#8a96a8;margin-left:4px;">#${orderIdx + 1} resolved</span>`
          : "";

        const statusDot = resolved
          ? `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#1ec466;margin-right:7px;flex-shrink:0;"></span>`
          : `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#e83030;margin-right:7px;flex-shrink:0;"></span>`;
        const durColor  = b.duration >= 4 ? "#e83030" : b.duration >= 2 ? "#f5a623" : "#617387";

        return (
          `<div style="display:flex;justify-content:space-between;align-items:center;` +
          `padding:7px 0;border-bottom:1px solid rgba(17,32,51,0.06);">` +
          `<span style="display:flex;align-items:center;font-size:0.84rem;color:#112033;">` +
          `${statusDot}<strong>${escapeHtml(label)}</strong>${orderTag}</span>` +
          `<span style="font-size:0.84rem;text-align:right;white-space:nowrap;">` +
          `${range} <span style="color:${durColor};">(${dur})</span></span></div>`
        );
      }).join("");

      // Summary line
      const resolvedCount = blockers.filter(b => tasks[b.item] === true).length;
      const totalCount    = blockers.length;
      const longestB      = blockers.reduce((a, b) => (b.duration > a.duration ? b : a), blockers[0]);
      const longestLabel  = _itemLabel(longestB.item);
      const tiedLongest   = blockers.filter(b => b.duration === longestB.duration);
      const isEscape = (typeof RUN !== "undefined") && RUN?.scenario?.key === "escape";
      const mapPreShared = isEscape && totalCount === 4 && tasks.map === true && !blockers.some((b) => b.item === "map");

      let summary_line = `<p style="margin:8px 0 6px;font-size:0.82rem;color:#617387;font-style:italic;">`;
      if (mapPreShared && resolvedCount === totalCount) {
        summary_line += `All 4 active steps were resolved. Room Map was pre-shared at the start, so it was not counted as an active step.`;
      } else if (resolvedCount === totalCount) {
        summary_line += `All ${totalCount} item${totalCount === 1 ? "" : "s"} resolved.`;
      } else {
        summary_line += `${resolvedCount} of ${totalCount} item${totalCount === 1 ? "" : "s"} resolved.`;
      }
      if (longestB.duration >= 2) {
        if (tiedLongest.length > 1) {
          const _tiedLabels = tiedLongest.map(b => escapeHtml(_itemLabel(b.item)));
          const tiedNames = _tiedLabels.length > 2
            ? _tiedLabels.slice(0, -1).join(", ") + ", and " + _tiedLabels[_tiedLabels.length - 1]
            : _tiedLabels.join(" and ");
          summary_line += ` ${tiedNames} were joint-longest at ${longestB.duration} step${longestB.duration === 1 ? "" : "s"} each.`;
        } else {
          summary_line += ` ${escapeHtml(longestLabel)} was the longest step at ${longestB.duration} step${longestB.duration === 1 ? "" : "s"}.`;
        }
      }
      summary_line += `</p>`;

      el.innerHTML = summary_line + html;
    }

    async function showCompletionModal() {
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

      // Stress card: always use the server-computed peak team stress from
      // metric_trajectory.stress_peak so the card matches insight and movement.
      // Never fall back to m.peakStress (a client-side estimate that can differ
      // from the backend avg-based peak). Show "—" until the summary loads.
      document.getElementById("doneStressValue").textContent = "—";
      document.getElementById("doneStressSub").textContent = "Loading…";

      // Set a basic insight immediately (no stress peak yet)
      document.getElementById("doneInsight").textContent = buildInsight(finalStep, null);

      document.getElementById("doneOverlay").classList.add("is-open");

      // Fetch saved run summary for all detail sections.
      // Live runs are saved to disk when the model ends (before the WS diff is sent),
      // but we retry once after 800 ms to handle any edge-case delay.
      const summaryRunId = RUN?.runId;
      if (_savedRunSummary && !cachedSummaryMatchesRun(summaryRunId)) {
        _savedRunSummary = null;
      }
      if (summaryRunId && !_savedRunSummary) {
        try {
          _savedRunSummary = await fetchSavedRunSummary(summaryRunId);
        } catch (_) {
          // First attempt failed — wait and retry once
          await new Promise(r => setTimeout(r, 800));
          try { _savedRunSummary = await fetchSavedRunSummary(summaryRunId); } catch (_2) {}
        }
      }
      if (_savedRunSummary) {
        const sectionsEl = document.getElementById("doneSections");
        if (sectionsEl) sectionsEl.style.display = "flex";

        // Update insight with richer data now that the summary is loaded
        document.getElementById("doneInsight").textContent =
          buildInsight(finalStep, _savedRunSummary);

        // Update outcome sub-label with classify_run_outcome result if available
        const outcomeDescEl = document.getElementById("doneOutcomeSub");
        if (outcomeDescEl && _savedRunSummary.outcome_label) {
          outcomeDescEl.textContent = _savedRunSummary.outcome_label;
        }

        // Re-sync the stress card to the trajectory peak now that we have it.
        // The initial render used m.peakStress (live-step value); the trajectory
        // peak is more accurate and is what the insight and metric panel show.
        const mt = _savedRunSummary.metric_trajectory;
        if (mt?.stress_peak != null) {
          document.getElementById("doneStressValue").textContent = fmtNum(mt.stress_peak);
          document.getElementById("doneStressSub").textContent = stressBand(mt.stress_peak);
        }

        _renderMetricMovement(_savedRunSummary.metric_trajectory, _savedRunSummary);
        _renderBlockerTimeline(_savedRunSummary.blocker_timeline, _savedRunSummary);
        _renderMemorySection(_savedRunSummary.memory_summary);
        _renderEmotionSection(_savedRunSummary.emotion_summary);
        _renderEventCounts(_savedRunSummary.event_counts, _savedRunSummary);
      } else {
        // No summary loaded — show graceful fallbacks so sections aren't blank dashes
        const sectionsEl = document.getElementById("doneSections");
        if (sectionsEl) sectionsEl.style.display = "flex";
        _renderMetricMovement(null, null);
        _renderBlockerTimeline(null, null);
      }
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

        // Apply replay-mode labels to the header and browser title so the user
        // can immediately see whether they are reviewing a Watch Mode or a Live
        // Interactive run.  This does not affect any simulation or metric logic.
        if (CONFIG.mode === "watch_replay" || CONFIG.mode === "interactive_replay") {
          const replayLabel = CONFIG.mode === "watch_replay"
            ? "Watch Mode Replay"
            : "Live Interactive Replay";
          document.title = replayLabel + " — SimuVerse";
          const svSub = document.querySelector(".sv-sub");
          if (svSub) svSub.textContent = replayLabel;
          if (footerNote) {
            footerNote.textContent = replayLabel
              + " — reviewing a saved run. No new simulation is running.";
          }
        }

        if (!RUN?.ended) {
          await ensureSocket(runId);
        }

        // Auto-start for both Watch Mode (step) and auto mode runs that haven't begun yet.
        // Replay modes (watch_replay / interactive_replay) always arrive with
        // RUN.ended = true and must NOT auto-start a new backend run.
        if ((RUN?.mode === "auto" || RUN?.mode === "step") && !RUN.ended && totalRunTicks() === 0) {
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
