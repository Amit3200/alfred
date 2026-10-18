from backend.routing.schedule_intent import looks_like_schedule_request


def test_create_schedule_is_management():
    assert looks_like_schedule_request("Create a schedule at 8 AM IST")
    assert looks_like_schedule_request("list schedules")


def test_run_scheduled_job_is_not_management():
    assert not looks_like_schedule_request("Run scheduled job daily_metrics_oneshot")
    assert not looks_like_schedule_request("run scheduled_daily_metrics_oneshot")
    assert not looks_like_schedule_request("Manually triggered job daily_metrics_oneshot")
