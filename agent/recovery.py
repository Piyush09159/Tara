from dataclasses import dataclass


@dataclass
class RecoveryDecision:
    """
    Describes how Tara should respond to an action failure.
    """

    error_type: str

    strategy: str

    blacklist_action: bool = True

    wait_seconds: float = 0.0

    retry_same_action: bool = False

    reason: str = ""


class RecoveryManager:

    """
    Converts low-level action failures into
    agent-level recovery strategies.
    """

    def decide(
        self,
        error_type: str,
        retry_count: int = 1,
    ) -> RecoveryDecision:

        normalized = (
            error_type
            or "UNKNOWN_ERROR"
        ).upper()

        # =====================================================
        # ELEMENT NOT FOUND
        # =====================================================

        if normalized == "ELEMENT_NOT_FOUND":

            return RecoveryDecision(
                error_type=normalized,
                strategy="reobserve",
                blacklist_action=True,
                retry_same_action=False,
                reason=(
                    "The element no longer exists. "
                    "Treat its current reference as stale "
                    "and regenerate the page state."
                ),
            )

        # =====================================================
        # ELEMENT NOT VISIBLE
        # =====================================================

        if normalized == "ELEMENT_NOT_VISIBLE":

            # First occurrence may be transient.
            if retry_count <= 1:

                return RecoveryDecision(
                    error_type=normalized,
                    strategy="wait_and_reobserve",
                    blacklist_action=False,
                    wait_seconds=0.75,
                    retry_same_action=False,
                    reason=(
                        "The element may be temporarily "
                        "hidden. Wait briefly and observe again."
                    ),
                )

            # Repeated visibility failure means it is
            # probably not a useful candidate.
            return RecoveryDecision(
                error_type=normalized,
                strategy="blacklist_and_replan",
                blacklist_action=True,
                retry_same_action=False,
                reason=(
                    "The element remained invisible after "
                    "a retry. Avoid it and select another "
                    "candidate."
                ),
            )

        # =====================================================
        # ELEMENT DISABLED
        # =====================================================

        if normalized == "ELEMENT_DISABLED":

            if retry_count <= 1:
                return RecoveryDecision(
                    error_type=normalized, strategy="wait_and_reobserve",
                    blacklist_action=False, wait_seconds=0.35,
                    reason="The control may become enabled after a bounded readiness wait.",
                )

            return RecoveryDecision(
                error_type=normalized,
                strategy="blacklist_and_replan",
                blacklist_action=True,
                retry_same_action=False,
                reason=(
                    "The element is disabled. Avoid it "
                    "and find another compatible candidate."
                ),
            )

        # =====================================================
        # CLICK ERROR
        # =====================================================

        if normalized == "CLICK_ERROR":

            if retry_count <= 1:

                return RecoveryDecision(
                    error_type=normalized,
                    strategy="wait_and_reobserve",
                    blacklist_action=False,
                    wait_seconds=0.5,
                    retry_same_action=False,
                    reason=(
                        "The click may have failed because "
                        "the page is still changing. "
                        "Wait and re-observe."
                    ),
                )

            return RecoveryDecision(
                error_type=normalized,
                strategy="blacklist_and_replan",
                blacklist_action=True,
                retry_same_action=False,
                reason=(
                    "Repeated click failure suggests the "
                    "candidate is unreliable. Avoid it."
                ),
            )

        # =====================================================
        # TYPE ERROR
        # =====================================================

        if normalized in {"TYPE_ERROR", "SELECT_ERROR", "CHECK_ERROR", "UNCHECK_ERROR"}:

            return RecoveryDecision(
                error_type=normalized,
                strategy="blacklist_and_replan",
                blacklist_action=True,
                retry_same_action=False,
                reason=(
                    "The field rejected the typing action. "
                    "Try another compatible input."
                ),
            )

        # =====================================================
        # KEY PRESS ERROR
        # =====================================================

        if normalized == "KEY_PRESS_ERROR":

            return RecoveryDecision(
                error_type=normalized,
                strategy="reobserve",
                blacklist_action=False,
                retry_same_action=False,
                reason=(
                    "Keyboard interaction failed. "
                    "Re-observe the page before continuing."
                ),
            )

        # =====================================================
        # NAVIGATION ERROR
        # =====================================================

        if normalized == "NAVIGATION_ERROR":

            if retry_count <= 1:

                return RecoveryDecision(
                    error_type=normalized,
                    strategy="retry_navigation",
                    blacklist_action=False,
                    wait_seconds=0.5,
                    retry_same_action=True,
                    reason=(
                        "Navigation may have failed "
                        "temporarily. Retry the same URL once."
                    ),
                )

            return RecoveryDecision(
                error_type=normalized,
                strategy="blacklist_and_replan",
                blacklist_action=True,
                retry_same_action=False,
                reason=(
                    "Navigation failed repeatedly. "
                    "Do not repeatedly attempt the same target."
                ),
            )

        # =====================================================
        # PAGE READ ERROR
        # =====================================================

        if normalized == "PAGE_READ_ERROR":

            return RecoveryDecision(
                error_type=normalized,
                strategy="wait_and_reobserve",
                blacklist_action=False,
                wait_seconds=0.5,
                retry_same_action=False,
                reason=(
                    "The page state could not be read. "
                    "Wait briefly and observe again."
                ),
            )

        if normalized in {"PAGE_NOT_READY", "DOM_CHANGED", "POPUP_OPENED", "REDIRECT_IN_PROGRESS"}:
            return RecoveryDecision(
                error_type=normalized, strategy="wait_and_reobserve",
                blacklist_action=False, wait_seconds=0.25,
                reason="Browser runtime state is transient; wait briefly then re-observe current page.",
            )

        # =====================================================
        # PLANNER ERROR
        # =====================================================

        if normalized == "PLANNER_ERROR":

            return RecoveryDecision(
                error_type=normalized,
                strategy="replan",
                blacklist_action=False,
                retry_same_action=False,
                reason=(
                    "The planner failed. "
                    "Rebuild candidates and ask the planner again."
                ),
            )

        # =====================================================
        # GOAL NOT SATISFIED
        # =====================================================

        if normalized == "GOAL_NOT_SATISFIED":

            return RecoveryDecision(
                error_type=normalized,
                strategy="blacklist_and_replan",
                blacklist_action=True,
                retry_same_action=False,
                reason=(
                    "The action executed but did not satisfy "
                    "the goal. Avoid repeating the same action."
                ),
            )

        # =====================================================
        # UNKNOWN ERROR
        # =====================================================

        return RecoveryDecision(
            error_type=normalized,
            strategy="reobserve",
            blacklist_action=True,
            retry_same_action=False,
            reason=(
                "Unknown failure. Avoid the failed action "
                "and re-observe the environment."
            ),
        )
