"""Finite, point-in-time session evidence classifier; metadata only."""


def classify(*, snapshot_complete, broker_owner_pid=None, broker_comm_pid=None,
             shared_helper_pids=(), active_session_pids=(), recovery_active=False,
             ownership_marker=None):
    """Return BROKER, ACTIVE_SESSION, CLEAR_SNAPSHOT, or UNKNOWN.

    A broker classification requires the socket owner PID to match an
    independently identified broker PID. Markers never establish a role.
    active_session_pids must come from positive session-state metadata tied to
    a PID; a process name or marker alone is not sufficient. CLEAR_SNAPSHOT
    only means the enumerated indicators were absent in this
    bounded snapshot; it makes no claim about unobserved processes or future
    races.
    """
    if not snapshot_complete or recovery_active:
        return 'UNKNOWN'
    if active_session_pids:
        return 'ACTIVE_SESSION'
    if ownership_marker is True:
        return 'UNKNOWN'
    if shared_helper_pids:
        if (broker_owner_pid is not None and
                broker_owner_pid == broker_comm_pid and
                set(shared_helper_pids) == {broker_owner_pid} and
                ownership_marker is False):
            return 'BROKER'
        return 'UNKNOWN'
    if broker_owner_pid is not None:
        if broker_owner_pid == broker_comm_pid and ownership_marker is False:
            return 'BROKER'
        return 'UNKNOWN'
    if ownership_marker is not False:
        return 'UNKNOWN'
    return 'CLEAR_SNAPSHOT'
