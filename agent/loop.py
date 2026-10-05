from agent.evaluator import TaskEvaluator
from agent.goals import GoalDecomposer
from agent.recovery import RecoveryManager
from agent.memory import WorkingMemory
from agent.execution import ActionProgress, TaskExecutionState
from agent.checkpoint import CheckpointManager, TaskCheckpoint
from agent.trace import AgentTrace, FailureRecord, RunSummary
from time import perf_counter


class AgentLoop:

    def __init__(
        self,
        reader,
        planner,
        actions,
        max_steps=8,
        max_retries_per_goal=2,
        max_no_progress_cycles=3,
        max_identical_action_repetitions=3,
        max_recovery_cycles=6,
        deterministic_selection=False,
    ):

        self.reader = reader
        self.planner = planner
        self.actions = actions

        self.max_steps = max_steps

        self.max_retries_per_goal = (
            max_retries_per_goal
        )
        self.max_no_progress_cycles = max_no_progress_cycles
        self.max_identical_action_repetitions = max_identical_action_repetitions
        self.max_recovery_cycles = max_recovery_cycles
        self.deterministic_selection = deterministic_selection

        self.evaluator = TaskEvaluator()
        self.decomposer = GoalDecomposer()
        self.recovery = RecoveryManager()

        # Expose the most recent run memory
        # for debugging and inspection.
        self.last_memory = None
        self.last_execution_state = None
        self.last_goal_plan = None
        self.checkpoints = CheckpointManager()
        self.last_trace = None
        self.last_trace_path = None
        self.last_run_summary = None
        self._trace_checkpoints_created = 0
        self._trace_checkpoints_restored = 0

    # =========================================================
    # RUN
    # =========================================================

    def run(self, task, resume_from=None):

        started_at = perf_counter()
        trace = AgentTrace(task=task)
        self.last_trace = trace
        self.last_trace_path = None
        self._trace_checkpoints_created = 0
        self._trace_checkpoints_restored = 0
        trace.record("task_started", task=task, resumed=bool(resume_from))

        # -----------------------------------------------------
        # CREATE GOAL PLAN
        # -----------------------------------------------------

        checkpoint = self.checkpoints.load(resume_from) if isinstance(resume_from, str) else resume_from
        goal_plan = checkpoint.goal_plan if checkpoint else self.decomposer.decompose(task)
        if checkpoint:
            self._trace_checkpoints_restored += 1
            trace.record("checkpoint_restored", checkpoint_id=checkpoint.checkpoint_id,
                         url=checkpoint.current_url, reason=checkpoint.checkpoint_reason)

        if not goal_plan.goals:

            print(
                "\n❌ Tara could not decompose "
                "the task."
            )

            return self._finish_run(False, task, started_at, trace, None, None)

        # -----------------------------------------------------
        # WORKING MEMORY
        # -----------------------------------------------------

        memory = checkpoint.working_memory if checkpoint else WorkingMemory(task=task)
        if checkpoint:
            # Failure history is useful diagnostic context, but a previous
            # session's element ID cannot blacklist a freshly observed target.
            for failed_action in memory.failed_actions:
                failed_action["blacklist"] = False

        self.last_memory = memory
        execution = checkpoint.execution_state if checkpoint else TaskExecutionState(
            task=task, goal_statuses={goal.id: "pending" for goal in goal_plan.goals})
        memory.execution = execution
        self.last_execution_state = execution
        self.last_goal_plan = goal_plan

        retry_counts = {}
        pending_retry_action = None

        print("\n" + "=" * 60)
        print("TARA GOAL PLAN")
        print("=" * 60)

        for goal in goal_plan.goals:

            print(
                f"  {goal.id}. "
                f"[{goal.goal_type}] "
                f"{goal.description}"
            )

        # =====================================================
        # AGENT LOOP
        # =====================================================

        for step in range(
            1,
            self.max_steps + 1,
        ):

            memory.current_step = step
            execution.total_steps = step

            print(
                f"\n{'-' * 60}"
            )

            print(
                f"STEP {step}/{self.max_steps}"
            )

            print(
                f"{'-' * 60}"
            )

            # =================================================
            # OBSERVE
            # =================================================

            # BrowserActions may have promoted a popup/new tab to the active
            # page during the previous settle cycle.  Reader remains a thin
            # current-page view and is updated without serializing page refs.
            if hasattr(self.reader, "page") and hasattr(self.actions, "page"):
                self.reader.page = self.actions.page

            # A short bounded settle captures delayed/SPA mutations before
            # planning without turning observation into fixed sleep logic.
            if hasattr(self.actions, "wait_for_settle"):
                self.actions.wait_for_settle(timeout=0.6, stable_for=0.15)

            try:

                page_state = (
                    self.reader.read_page()
                )

            except Exception as error:

                print(
                    "[Observe] ❌ "
                    f"Failed to read page: "
                    f"{error}"
                )

                retry_number = retry_counts.get(
                    -1,
                    0,
                ) + 1

                retry_counts[-1] = (
                    retry_number
                )

                decision = (
                    self.recovery.decide(
                        "PAGE_READ_ERROR",
                        retry_number,
                    )
                )

                memory.add_recovery_event(
                    {
                        "step": step,
                        "goal_id": None,
                        "error_type": "PAGE_READ_ERROR",
                        "strategy": decision.strategy,
                        "reason": decision.reason,
                    }
                )

                print(
                    "[Recovery] "
                    f"{decision.strategy}"
                )

                print(
                    "[Recovery] "
                    f"{decision.reason}"
                )

                if (
                    decision.wait_seconds
                    > 0
                ):

                    self.actions.wait(
                        decision.wait_seconds
                    )

                continue

            # =================================================
            # STORE OBSERVATION
            # =================================================

            # Facts are semantic TaskFacts only; this event deliberately
            # excludes selectors, element IDs and DOM paths.
            known_before = {(fact.key, fact.value) for fact in memory.task_context.facts}
            memory.add_observation(
                page_state,
            )

            memory.add_browser_snapshot(
                page_state,
            )
            readiness = getattr(self.actions, "readiness", None)
            action_runtime = getattr(self.actions, "runtime_telemetry", {})
            memory.runtime_telemetry = {
                **getattr(readiness, "telemetry", {}),
                **action_runtime,
                "active_page_count": len(getattr(getattr(self.actions, "browser", None), "pages", []) or [self.actions.page]),
                "reobservations": step,
            }
            snapshot = memory.browser.recent_snapshot()
            current_fingerprint = snapshot.fingerprint if snapshot else ""
            trace.record("observation", step=step, url=page_state.url,
                         title=page_state.title, page_fingerprint=current_fingerprint,
                         page_identity=str(id(getattr(self.actions, "page", None))),
                         runtime=memory.runtime_telemetry)
            for fact in memory.task_context.facts:
                if (fact.key, fact.value) not in known_before:
                    trace.record("fact_discovered", step=step, fact_key=fact.key,
                                 source_url=fact.source_url, source_step=fact.source_step,
                                 confidence=fact.confidence)

            print(
                f"[Observe] "
                f"{page_state.title}"
            )

            print(
                f"[Observe] "
                f"{page_state.url}"
            )

            # =================================================
            # CURRENT GOAL
            # =================================================

            current_goal = goal_plan.current_goal(memory)

            for goal in goal_plan.goals:
                ready, reason = goal_plan.readiness(goal, memory)
                if not ready and not goal.completed:
                    execution.dependency_blockers[goal.id] = reason
            execution.blocked_goal_ids = [goal.id for goal in goal_plan.goals if goal.status == "BLOCKED"]

            if current_goal is None:

                print(
                    "\n✅ ALL GOALS COMPLETED"
                )

                self._print_memory_summary(
                    memory
                )

                return self._finish_run(True, task, started_at, trace, memory, execution)

            memory.current_goal_id = (
                current_goal.id
            )
            execution.activate_goal(current_goal.id)
            execution.last_url = page_state.url
            execution.last_fingerprint = current_fingerprint
            trace.record("goal_activated", step=step, goal_id=current_goal.id,
                         description=current_goal.description,
                         prerequisites=current_goal.prerequisites,
                         required_fact=current_goal.required_fact,
                         blockers=execution.dependency_blockers.get(current_goal.id, ""))

            print(
                f"[Goal] "
                f"{current_goal.id}/"
                f"{goal_plan.total_count}: "
                f"{current_goal.description}"
            )

            # =================================================
            # INITIAL GOAL CHECK
            # =================================================

            goal_status = (
                self.evaluator.evaluate_goal(
                    page_state,
                    current_goal,
                )
            )

            print(
                f"[Goal Check] "
                f"{goal_status.status}"
            )

            print(
                f"[Goal Check] "
                f"{goal_status.reason}"
            )

            if goal_status.status == "done":

                current_goal.completed = True
                execution.complete_goal(current_goal.id)

                memory.add_goal_event(
                    {
                        "step": step,
                        "goal_id": current_goal.id,
                        "description": current_goal.description,
                        "status": "done",
                    }
                )

                print(
                    f"[Goal] ✅ "
                    f"Goal {current_goal.id} "
                    f"already satisfied."
                )

                continue

            if goal_status.status == "failed":

                memory.add_goal_event(
                    {
                        "step": step,
                        "goal_id": current_goal.id,
                        "description": current_goal.description,
                        "status": "failed",
                    }
                )

                print(
                    f"[Goal] ❌ "
                    f"Goal {current_goal.id} "
                    f"failed."
                )

                trace.record("goal_failed", step=step, goal_id=current_goal.id,
                             reason=goal_status.reason)
                return self._finish_run(False, task, started_at, trace, memory, execution)

            # =================================================
            # RETRY LIMIT
            # =================================================

            goal_retry_count = retry_counts.get(
                current_goal.id,
                0,
            )

            if (
                goal_retry_count
                >= self.max_retries_per_goal
            ):

                print(
                    f"[Goal] ❌ "
                    f"Goal {current_goal.id} "
                    f"exceeded retry limit."
                )

                trace.record("goal_failed", step=step, goal_id=current_goal.id,
                             reason="retry_limit")
                return self._finish_run(False, task, started_at, trace, memory, execution)

            # =================================================
            # THINK
            # =================================================

            print(
                "[Think] Asking Qwen..."
            )

            try:

                if (
                    pending_retry_action is not None
                    and self._action_is_current(
                        pending_retry_action,
                        page_state,
                    )
                ):

                    action = pending_retry_action
                    pending_retry_action = None

                    print(
                        "[Recovery] Retrying the current "
                        "safe action."
                    )

                else:

                    # A pending element target that is no longer present is
                    # stale. Re-plan from the freshly observed PageState.
                    pending_retry_action = None

                    action = self.planner.plan(
                        page_state=page_state,
                        task=current_goal.description,
                        memory=memory,
                        allow_deterministic=self.deterministic_selection,
                    )

                diagnostics = dict(getattr(self.planner, "diagnostics", {}))
                trace.record("planner_called", step=step, goal_id=current_goal.id,
                             decision_type=getattr(self.planner, "last_decision_type", None),
                             diagnostics=diagnostics)
                trace.record("candidate_generated", step=step, goal_id=current_goal.id,
                             candidate_count_before_filter=diagnostics.get("candidate_count_before_filter", 0),
                             candidate_count_after_filter=diagnostics.get("candidate_count_after_filter", 0),
                             top_k=diagnostics.get("top_k_count", 0))

                if self.planner.last_decision_type == "deterministic":
                    execution.deterministic_decisions += 1
                else:
                    execution.planner_calls += 1

            except Exception as error:

                planning_error_type = (
                    "PAGE_NOT_READY"
                    if "No valid action candidates remain" in str(error)
                    else "PLANNER_ERROR"
                )

                print(
                    "[Think] ❌ "
                    f"Planner failed: "
                    f"{error}"
                )

                retry_counts[
                    current_goal.id
                ] = (
                    retry_counts.get(
                        current_goal.id,
                        0,
                    )
                    + 1
                )

                retry_number = (
                    retry_counts[
                        current_goal.id
                    ]
                )

                decision = (
                    self.recovery.decide(
                        planning_error_type,
                        retry_number,
                    )
                )

                failed_record = {
                    "goal_id": current_goal.id,
                    "stage": "planning",
                    "success": False,
                    "error_type": (
                        planning_error_type
                    ),
                    "error": str(error),
                    "blacklist": (
                        decision.blacklist_action
                    ),
                }

                memory.add_failed_action(
                    failed_record
                )

                memory.add_recovery_event(
                    {
                        "step": step,
                        "goal_id": current_goal.id,
                        "error_type": planning_error_type,
                        "strategy": decision.strategy,
                        "reason": decision.reason,
                    }
                )
                trace.record("action_failed", step=step, goal_id=current_goal.id,
                             failure=self._failure("planner_failure", planning_error_type, step, current_goal.id,
                                                   {}, decision.strategy).model_dump())
                trace.record("recovery_started", step=step, goal_id=current_goal.id,
                             strategy=decision.strategy, reason=decision.reason)
                execution.recovery_count += 1
                execution.recovery_replans += 1

                print(
                    "[Recovery] "
                    f"{decision.strategy}"
                )

                print(
                    "[Recovery] "
                    f"{decision.reason}"
                )

                if (
                    decision.wait_seconds
                    > 0
                ):

                    self.actions.wait(
                        decision.wait_seconds
                    )

                continue

            # =================================================
            # ACTION DICT
            # =================================================

            action_dict = (
                action.model_dump()
            )
            trace_action, sensitive = self._trace_action(action_dict, page_state)
            trace.record("action_selected", step=step, goal_id=current_goal.id,
                         action=trace_action, sensitive=sensitive, url=page_state.url,
                         page_fingerprint=current_fingerprint)

            # -------------------------------------------------
            # ADD CLICK TARGET TEXT
            # -------------------------------------------------

            if action.action == "click":

                for link in page_state.links:

                    if (
                        link.id
                        == action.element_id
                    ):

                        action_dict[
                            "target_text"
                        ] = link.text

                        break

                if not action_dict.get(
                    "target_text"
                ):

                    for button in page_state.buttons:

                        if (
                            button.id
                            == action.element_id
                        ):

                            action_dict[
                                "target_text"
                            ] = button.text

                            break

            print(
                "[Think] Validated action:"
            )

            print(
                action_dict
            )

            # =================================================
            # ACT
            # =================================================

            previous_url = (
                page_state.url
            )

            print(
                "[Act] Executing..."
            )

            try:

                result = (
                    self.actions.execute(
                        action
                    )
                )

                print(
                    f"[Act] Result: {result}"
                )
                trace.record("action_executed", step=step, goal_id=current_goal.id,
                             action=trace_action, result=result, old_url=previous_url,
                             new_url=result.get("new_url", previous_url),
                             navigation_detected=result.get("navigated", False),
                             runtime=getattr(self.actions, "runtime_telemetry", {}))

            except Exception as error:

                print(
                    "[Act] ❌ "
                    f"Unexpected action failure: "
                    f"{error}"
                )

                retry_counts[
                    current_goal.id
                ] = (
                    retry_counts.get(
                        current_goal.id,
                        0,
                    )
                    + 1
                )

                retry_number = (
                    retry_counts[
                        current_goal.id
                    ]
                )

                decision = (
                    self.recovery.decide(
                        "UNEXPECTED_ERROR",
                        retry_number,
                    )
                )

                failed_record = {
                    **action_dict,
                    "goal_id": current_goal.id,
                    "stage": "execution",
                    "success": False,
                    "error_type": (
                        "UNEXPECTED_ERROR"
                    ),
                    "error": str(error),
                    "blacklist": (
                        decision.blacklist_action
                    ),
                }

                memory.add_failed_action(
                    failed_record
                )

                memory.add_recovery_event(
                    {
                        "step": step,
                        "goal_id": current_goal.id,
                        "error_type": "UNEXPECTED_ERROR",
                        "strategy": decision.strategy,
                        "reason": decision.reason,
                    }
                )
                trace.record("action_failed", step=step, goal_id=current_goal.id,
                             failure=self._failure("task_failure", "UNEXPECTED_ERROR", step, current_goal.id,
                                                   trace_action, decision.strategy).model_dump())
                trace.record("recovery_started", step=step, goal_id=current_goal.id,
                             strategy=decision.strategy, reason=decision.reason)

                print(
                    "[Recovery] "
                    f"{decision.strategy}"
                )

                print(
                    "[Recovery] "
                    f"{decision.reason}"
                )

                if (
                    decision.wait_seconds
                    > 0
                ):

                    self.actions.wait(
                        decision.wait_seconds
                    )

                continue

            # =================================================
            # STRUCTURED ACTION FAILURE
            # =================================================

            if not result.get(
                "success",
                False,
            ):

                error_type = result.get(
                    "error_type",
                    "UNKNOWN_ERROR",
                )

                error_message = result.get(
                    "error",
                    "Unknown action failure.",
                )

                print(
                    "[Act] ❌ "
                    f"{error_type}"
                )

                print(
                    "[Act] "
                    f"{error_message}"
                )

                retry_counts[
                    current_goal.id
                ] = (
                    retry_counts.get(
                        current_goal.id,
                        0,
                    )
                    + 1
                )

                retry_number = (
                    retry_counts[
                        current_goal.id
                    ]
                )

                decision = (
                    self.recovery.decide(
                        error_type,
                        retry_number,
                    )
                )

                if decision.retry_same_action:
                    pending_retry_action = action

                failed_record = {
                    **action_dict,
                    "goal_id": current_goal.id,
                    "stage": "execution",
                    "success": False,
                    "error_type": error_type,
                    "error": error_message,
                    "blacklist": (
                        decision.blacklist_action
                    ),
                    "recovery_strategy": (
                        decision.strategy
                    ),
                }

                memory.add_failed_action(
                    failed_record
                )

                memory.add_recovery_event(
                    {
                        "step": step,
                        "goal_id": current_goal.id,
                        "error_type": error_type,
                        "strategy": decision.strategy,
                        "reason": decision.reason,
                    }
                )
                trace.record("action_failed", step=step, goal_id=current_goal.id,
                             failure=self._failure(self._failure_category(error_type), error_type, step,
                                                   current_goal.id, trace_action, decision.strategy).model_dump())
                trace.record("recovery_started", step=step, goal_id=current_goal.id,
                             strategy=decision.strategy, reason=decision.reason,
                             retry_same_action=decision.retry_same_action,
                             blacklist_action=decision.blacklist_action)
                execution.recovery_count += 1
                execution.recovery_replans += 1

                print(
                    "[Recovery] "
                    f"Strategy: "
                    f"{decision.strategy}"
                )

                print(
                    "[Recovery] "
                    f"{decision.reason}"
                )

                print(
                    "[Recovery] "
                    f"Blacklist action: "
                    f"{decision.blacklist_action}"
                )

                if (
                    decision.wait_seconds
                    > 0
                ):

                    print(
                        "[Recovery] "
                        f"Waiting "
                        f"{decision.wait_seconds}s..."
                    )

                    self.actions.wait(
                        decision.wait_seconds
                    )

                print(
                    "[Recovery] "
                    f"Retry "
                    f"{retry_number}/"
                    f"{self.max_retries_per_goal}"
                )

                continue

            # =================================================
            # SUCCESSFUL ACTION
            # =================================================

            memory.add_completed_action(
                action_dict
            )
            execution.record_action(action_dict, result)

            # -------------------------------------------------
            # BROWSER TRANSITION
            # -------------------------------------------------

            transition_url = result.get(
                "new_url",
                page_state.url,
            )

            transition_action = result.get(
                "action",
                action.action,
            )

            transition_success = result.get(
                "success",
                False,
            )

            transition_navigated = result.get(
                "navigated",
                False,
            )
            settle = result.get("settle", {})
            transition_state_changed = bool(
                transition_navigated
                or settle.get("fingerprint")
                and settle.get("fingerprint") != current_fingerprint
            )

            memory.add_browser_transition(
                from_url=previous_url,
                to_url=transition_url,
                action=transition_action,
                success=transition_success,
                navigated=transition_navigated,
                state_changed=transition_state_changed,
                page_identity=str(id(getattr(self.actions, "page", None))),
            )

            # =================================================
            # VERIFY
            # =================================================

            if hasattr(self.reader, "page") and hasattr(self.actions, "page"):
                self.reader.page = self.actions.page

            try:

                updated_state = (
                    self.reader.read_page()
                )

            except Exception as error:

                print(
                    "[Verify] ❌ "
                    f"Could not refresh page: "
                    f"{error}"
                )

                retry_counts[
                    current_goal.id
                ] = (
                    retry_counts.get(
                        current_goal.id,
                        0,
                    )
                    + 1
                )

                retry_number = (
                    retry_counts[
                        current_goal.id
                    ]
                )

                decision = (
                    self.recovery.decide(
                        "PAGE_READ_ERROR",
                        retry_number,
                    )
                )

                failed_record = {
                    **action_dict,
                    "goal_id": current_goal.id,
                    "stage": "verification",
                    "success": False,
                    "error_type": (
                        "PAGE_READ_ERROR"
                    ),
                    "error": str(error),
                    "blacklist": (
                        decision.blacklist_action
                    ),
                }

                memory.add_failed_action(
                    failed_record
                )

                memory.add_recovery_event(
                    {
                        "step": step,
                        "goal_id": current_goal.id,
                        "error_type": "PAGE_READ_ERROR",
                        "strategy": decision.strategy,
                        "reason": decision.reason,
                    }
                )

                print(
                    "[Recovery] "
                    f"{decision.strategy}"
                )

                continue

            # -------------------------------------------------
            # STORE UPDATED PAGE
            # -------------------------------------------------

            memory.add_browser_snapshot(
                updated_state,
            )

            updated_snapshot = memory.browser.recent_snapshot()
            progress = self._evaluate_progress(
                page_state,
                updated_state,
                current_fingerprint,
                updated_snapshot.fingerprint if updated_snapshot else "",
                len(memory.task_context.facts),
                action_dict,
                result,
            )
            execution.record_progress(progress)

            # A verified state change means previous transient failures for
            # this goal no longer describe the current situation.
            if progress.meaningful:
                retry_counts[current_goal.id] = 0

            print(
                "[Verify] "
                "Checking current goal..."
            )

            post_status = (
                self.evaluator.evaluate_goal(
                    updated_state,
                    current_goal,
                    last_action=action_dict,
                    action_result=result,
                )
            )

            print(
                f"[Verify] "
                f"{post_status.status}"
            )

            print(
                f"[Verify] "
                f"{post_status.reason}"
            )

            # =================================================
            # GOAL SUCCESS
            # =================================================

            if post_status.status == "done":

                current_goal.completed = True
                execution.complete_goal(current_goal.id)
                execution.record_progress(ActionProgress(meaningful=True, signals=["goal_completed"]))

                memory.add_goal_event(
                    {
                        "step": step,
                        "goal_id": current_goal.id,
                        "description": current_goal.description,
                        "status": "done",
                    }
                )

                print(
                    f"[Goal] ✅ "
                    f"Goal {current_goal.id} "
                    f"completed."
                )
                trace.record("goal_completed", step=step, goal_id=current_goal.id,
                             verification_result=post_status.status, reason=post_status.reason,
                             progress_signals=progress.signals)

                continue

            # =================================================
            # GOAL NOT SATISFIED
            # =================================================

            if post_status.status == "failed":

                retry_counts[
                    current_goal.id
                ] = (
                    retry_counts.get(
                        current_goal.id,
                        0,
                    )
                    + 1
                )

                retry_number = (
                    retry_counts[
                        current_goal.id
                    ]
                )

                decision = (
                    self.recovery.decide(
                        "GOAL_NOT_SATISFIED",
                        retry_number,
                    )
                )

                failed_record = {
                    **action_dict,
                    "goal_id": current_goal.id,
                    "stage": (
                        "goal_verification"
                    ),
                    "success": False,
                    "error_type": (
                        "GOAL_NOT_SATISFIED"
                    ),
                    "error": (
                        post_status.reason
                    ),
                    "blacklist": (
                        decision.blacklist_action
                    ),
                    "recovery_strategy": (
                        decision.strategy
                    ),
                }

                memory.add_failed_action(
                    failed_record
                )

                memory.add_recovery_event(
                    {
                        "step": step,
                        "goal_id": current_goal.id,
                        "error_type": "GOAL_NOT_SATISFIED",
                        "strategy": decision.strategy,
                        "reason": decision.reason,
                    }
                )

                print(
                    "[Recovery] "
                    f"Strategy: "
                    f"{decision.strategy}"
                )

                print(
                    "[Recovery] "
                    f"{decision.reason}"
                )

                continue

            # =================================================
            # CONTINUE
            # =================================================

            print(
                "[Recovery] "
                "Goal not complete yet; "
                "agent will re-plan."
            )

            if (
                execution.no_progress_count >= self.max_no_progress_cycles
                or execution.repeated_action_count >= self.max_identical_action_repetitions
                or execution.recovery_count >= self.max_recovery_cycles
            ):
                execution.fail_goal(current_goal.id)
                memory.add_goal_event({
                    "step": step,
                    "goal_id": current_goal.id,
                    "description": current_goal.description,
                    "status": "failed",
                    "reason": "Stuck: bounded no-progress/recovery budget exceeded.",
                })
                trace.record("goal_failed", step=step, goal_id=current_goal.id,
                             reason="bounded_no_progress_recovery_budget")
                return self._finish_run(False, task, started_at, trace, memory, execution)

        # =====================================================
        # FINAL RESULT
        # =====================================================

        if goal_plan.is_complete:

            print(
                "\n✅ ALL GOALS COMPLETED"
            )

            self._print_memory_summary(
                memory
            )

            return self._finish_run(True, task, started_at, trace, memory, execution)

        print(
            "\n⚠️ Maximum agent steps reached."
        )

        print(
            f"Completed goals: "
            f"{goal_plan.completed_count}/"
            f"{goal_plan.total_count}"
        )

        self._print_memory_summary(
            memory
        )

        return self._finish_run(False, task, started_at, trace, memory, execution)

    def _failure_category(self, error_type):
        mapping = {
            "ELEMENT_NOT_FOUND": "element_not_found", "ELEMENT_NOT_VISIBLE": "element_not_visible",
            "ELEMENT_DISABLED": "element_disabled", "STALE_TARGET": "stale_target",
            "NAVIGATION_ERROR": "navigation_failure", "PAGE_NOT_READY": "readiness_failure",
            "TIMEOUT": "timeout", "PLANNER_ERROR": "planner_failure",
        }
        return mapping.get(str(error_type).upper(), "task_failure")

    def _failure(self, category, error_type, step, goal_id, action, recovery_strategy):
        return FailureRecord(category=category, error_type=error_type, step=step,
                             goal_id=goal_id, action=action,
                             recovery_strategy=recovery_strategy)

    def _trace_action(self, action, page_state):
        """Redact text only when it targets a current password control."""
        copied = dict(action)
        sensitive = any(field.id == action.get("element_id") and
                        str(field.type or "").lower() == "password"
                        for field in page_state.inputs)
        if sensitive and "text" in copied:
            copied["text"] = "<REDACTED>"
        return copied, sensitive

    def _finish_run(self, passed, task, started_at, trace, memory, execution):
        """Finalize diagnostics while retaining AgentLoop's bool API."""
        if memory is None or execution is None:
            summary = RunSummary(run_id=trace.run_id, task=task, result="FAIL")
        else:
            diagnostics = getattr(self.planner, "diagnostics", {})
            failures = []
            for item in memory.failed_actions:
                failures.append(self._failure(self._failure_category(item.get("error_type", "")),
                    item.get("error_type", ""), item.get("step", memory.current_step),
                    item.get("goal_id"), item, item.get("recovery_strategy", "")))
            summary = RunSummary(run_id=trace.run_id, task=task, result="PASS" if passed else "FAIL",
                total_steps=execution.total_steps, completed_goals=len(execution.completed_goal_ids),
                failed_goals=len(execution.failed_goal_ids), planner_calls=execution.planner_calls,
                deterministic_decisions=execution.deterministic_decisions,
                fallbacks=diagnostics.get("fallback_selections", 0), recovery_count=execution.recovery_count,
                no_progress_count=execution.no_progress_count, repeated_action_count=execution.repeated_action_count,
                facts_discovered=len(memory.task_context.facts), checkpoints_created=self._trace_checkpoints_created,
                checkpoints_restored=self._trace_checkpoints_restored,
                duration_seconds=perf_counter() - started_at,
                active_page_count=len(getattr(getattr(self.actions, "browser", None), "pages", []) or [self.actions.page]),
                stale_target_events=getattr(self.actions, "runtime_telemetry", {}).get("stale_target_events", 0),
                failures=failures)
        self.last_run_summary = summary
        trace.record("task_completed" if passed else "task_failed", step=summary.total_steps,
                     result=summary.result, summary=summary.model_dump(mode="json"))
        # A trace is most useful when it survives the process that produced
        # it. Failure to write diagnostics must never alter task behaviour.
        try:
            self.last_trace_path = trace.save()
        except OSError:
            self.last_trace_path = None
        return passed

    def _action_is_current(
        self,
        action,
        page_state,
    ):
        """Ensure retry targets belong to the freshly observed page state."""

        if action.action == "navigate":
            return True

        if not action.element_id:
            return False

        current_elements = (
            list(page_state.links)
            + list(page_state.buttons)
            + list(page_state.inputs)
        )

        return any(
            element.id == action.element_id
            and element.visible
            and element.enabled
            for element in current_elements
        )

    def create_checkpoint(self, reason="manual"):
        """Persist semantic state only; live browser references are excluded."""
        if not self.last_memory or not self.last_goal_plan or not self.last_execution_state:
            raise RuntimeError("No active task state is available to checkpoint.")
        checkpoint = TaskCheckpoint(
            task=self.last_memory.task, goal_plan=self.last_goal_plan,
            working_memory=self.last_memory, execution_state=self.last_execution_state,
            current_url=getattr(getattr(self.actions, "page", None), "url", ""),
            active_page_identity=str(id(getattr(self.actions, "page", None))),
            checkpoint_reason=reason,
        )
        checkpoint_id = self.checkpoints.save(checkpoint)
        self._trace_checkpoints_created += 1
        if self.last_trace:
            self.last_trace.record("checkpoint_created", step=self.last_memory.current_step,
                                   checkpoint_id=checkpoint_id, reason=reason,
                                   url=checkpoint.current_url)
        return checkpoint_id

    def resume_from_checkpoint(self, checkpoint_id):
        checkpoint = self.checkpoints.load(checkpoint_id)
        # Retry/no-progress counters are session-scoped, so run() rebuilds its
        # transient retry map while restoring semantic execution state.
        return self.run(checkpoint.task, resume_from=checkpoint)

    def _evaluate_progress(
        self,
        before_state,
        after_state,
        before_fingerprint,
        after_fingerprint,
        fact_count,
        action,
        result,
    ):
        signals = []
        if before_state.url != after_state.url:
            signals.append("url_changed")
        if before_state.title != after_state.title:
            signals.append("title_changed")
        if before_fingerprint != after_fingerprint:
            signals.append("page_state_changed")
        if action.get("action") == "type" and result.get("success"):
            signals.append("field_updated")
        return ActionProgress(meaningful=bool(signals), signals=signals)

    # =========================================================
    # MEMORY SUMMARY
    # =========================================================

    def _print_memory_summary(
        self,
        memory: WorkingMemory,
    ):

        print(
            "\n[Memory] "
            f"Successful actions: "
            f"{len(memory.completed_actions)}"
        )

        print(
            "[Memory] "
            f"Failed actions: "
            f"{len(memory.failed_actions)}"
        )

        print(
            "[Memory] "
            f"Visited URLs: "
            f"{len(memory.browser.visited_urls)}"
        )

        if memory.browser.visited_urls:

            print(
                "[Memory] Visited URLs:"
            )

            for url in (
                memory.browser.visited_urls
            ):

                print(
                    f"  - {url}"
                )

        print(
            "[Memory] "
            f"Browser transitions: "
            f"{len(memory.browser.transitions)}"
        )

        if memory.browser.transitions:

            print(
                "[Memory] Browser transitions:"
            )

            for transition in (
                memory.browser.transitions
            ):

                print(
                    f"  - STEP "
                    f"{transition.step}: "
                    f"{transition.from_url} "
                    f"-> "
                    f"{transition.to_url} "
                    f"via "
                    f"{transition.action}"
                )

        # -----------------------------------------------------
        # SEMANTIC PAGE MEMORY
        # -----------------------------------------------------

        print(
            "[Memory] "
            f"Semantic page snapshots: "
            f"{len(memory.browser.snapshots)}"
        )

        for snapshot in (
            memory.browser.snapshots[-5:]
        ):

            print(
                f"\n[Memory] Page snapshot "
                f"STEP {snapshot.step}"
            )

            print(
                f"  URL: {snapshot.url}"
            )

            print(
                f"  Title: {snapshot.title}"
            )

            if snapshot.headings:

                print(
                    "  Headings:"
                )

                for heading in (
                    snapshot.headings[:5]
                ):

                    print(
                        f"    - {heading}"
                    )

            if snapshot.links:

                print(
                    "  Links:"
                )

                for link in (
                    snapshot.links[:5]
                ):

                    print(
                        f"    - "
                        f"{link.get('text', '')}"
                    )

            if snapshot.buttons:

                print(
                    "  Buttons:"
                )

                for button in (
                    snapshot.buttons[:5]
                ):

                    print(
                        f"    - "
                        f"{button.get('text', '')}"
                    )

            if snapshot.inputs:

                print(
                    "  Inputs:"
                )

                for field in (
                    snapshot.inputs[:5]
                ):

                    print(
                        f"    - "
                        f"{field.get('name')}"
                        f" / "
                        f"{field.get('label')}"
                    )
