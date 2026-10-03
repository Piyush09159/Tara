from agent.evaluator import TaskEvaluator
from agent.goals import GoalDecomposer
from agent.recovery import RecoveryManager
from agent.memory import WorkingMemory
from agent.execution import ActionProgress, TaskExecutionState


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

    # =========================================================
    # RUN
    # =========================================================

    def run(self, task):

        # -----------------------------------------------------
        # CREATE GOAL PLAN
        # -----------------------------------------------------

        goal_plan = self.decomposer.decompose(
            task
        )

        if not goal_plan.goals:

            print(
                "\n❌ Tara could not decompose "
                "the task."
            )

            return False

        # -----------------------------------------------------
        # WORKING MEMORY
        # -----------------------------------------------------

        memory = WorkingMemory(
            task=task
        )

        self.last_memory = memory
        execution = TaskExecutionState(
            task=task,
            goal_statuses={goal.id: "pending" for goal in goal_plan.goals},
        )
        memory.execution = execution
        self.last_execution_state = execution

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

            memory.add_observation(
                page_state,
            )

            memory.add_browser_snapshot(
                page_state,
            )
            snapshot = memory.browser.recent_snapshot()
            current_fingerprint = snapshot.fingerprint if snapshot else ""

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

            current_goal = (
                goal_plan.current_goal()
            )

            if current_goal is None:

                print(
                    "\n✅ ALL GOALS COMPLETED"
                )

                self._print_memory_summary(
                    memory
                )

                return True

            memory.current_goal_id = (
                current_goal.id
            )
            execution.activate_goal(current_goal.id)
            execution.last_url = page_state.url
            execution.last_fingerprint = current_fingerprint

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

                return False

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

                return False

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

                if self.planner.last_decision_type == "deterministic":
                    execution.deterministic_decisions += 1
                else:
                    execution.planner_calls += 1

            except Exception as error:

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
                        "PLANNER_ERROR",
                        retry_number,
                    )
                )

                failed_record = {
                    "goal_id": current_goal.id,
                    "stage": "planning",
                    "success": False,
                    "error_type": (
                        "PLANNER_ERROR"
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
                        "error_type": "PLANNER_ERROR",
                        "strategy": decision.strategy,
                        "reason": decision.reason,
                    }
                )
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

            memory.add_browser_transition(
                from_url=previous_url,
                to_url=transition_url,
                action=transition_action,
                success=transition_success,
                navigated=transition_navigated,
            )

            # =================================================
            # VERIFY
            # =================================================

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
                return False

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

            return True

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

        return False

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
