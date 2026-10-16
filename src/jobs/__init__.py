"""Background job queue: enqueue, dispatch, and the shared job lifecycle.

Rows (``jobs``/``runs``/``run_events``) are the only job truth — the queue is a
dispatch mechanism, never state.
"""
